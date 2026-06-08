import glob
import os
from flask import Flask, request, render_template, jsonify, session, url_for, abort
from datetime import datetime, timedelta
import meilisearch
from meilisearch.errors import MeilisearchApiError
from databases.config import DevConfig
from databases.user_rdb import db, User, Post
from werkzeug.utils import redirect, secure_filename
from sqlalchemy.exc import IntegrityError
import json
import uuid

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__, template_folder="html_templates")
app.config.from_object(DevConfig)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or os.getenv('FLASK_SECRET_KEY') or os.urandom(24).hex()
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=5)

if os.getenv('DATABASE_URL'):
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')


db.init_app(app)

UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'static/uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


MEILISEARCH_URL = os.getenv("MEILISEARCH_URL")
DATA_DIR = os.getenv("DATA_DIR", "seller_homes")
INDEX_NAME = "real_estate_listings"

client = None
index = None

if MEILISEARCH_URL:
    client = meilisearch.Client(MEILISEARCH_URL)
    try:
        index = client.get_index(INDEX_NAME)
    except MeilisearchApiError:
        index = client.create_index(INDEX_NAME, {"primaryKey": "id"})



@app.route("/signup", methods=["GET"])
def signup_page():
    return render_template("log_in.html")


# @app.route('/home/<string:address_line1>/<string:post_id>', methods=['GET'])
# def view_home(address_line1, post_id):
#     # 1. FETCH THE DATA
#     home = Post.query.get_or_404(post_id)
    
#     # 2. TRACK THE VIEW (Behind the scenes)
#     if 'viewed_homes' not in session:
#         session['viewed_homes'] = []
        
#     if post_id not in session['viewed_homes']:
#         home.views += 1
#         db.session.commit()
#         session['viewed_homes'].append(post_id)
#         session.modified = True
    
#     # 3. DISPLAY THE POST
#     return render_template('post_page.html', home=home)



@app.route('/home/<string:address_line1>/<string:post_id>', methods=['GET'])
def view_home(address_line1, post_id):
    # 1. FETCH THE DATA FROM THE JSON FILE
    post_file_path = f"seller_homes/home_{post_id}.json"
    
    if not os.path.exists(post_file_path):
        abort(404) # Trigger 404 if the JSON file doesn't exist
        
    with open(post_file_path, "r") as f:
        home_data = json.load(f)

    # 2. TRACK THE VIEW (Behind the scenes via Session)
    if 'viewed_homes' not in session:
        session['viewed_homes'] = []
        
    if post_id not in session['viewed_homes']:
        # If tracking view counts in JSON, increment it here
        home_data['views'] = home_data.get('views', 0) + 1
        with open(post_file_path, "w") as f:
            json.dump(home_data, f, indent=4)
            
        session['viewed_homes'].append(post_id)
        session.modified = True
    
    # 3. DISPLAY THE POST
    # Passing home_data as an object-like wrapper so your HTML syntax 'home.property_type' still works seamlessly
    class ObjectView(object):
        def __init__(self, d):
            self.__dict__ = d

    home_object = ObjectView(home_data)
    return render_template('post_page.html', home=home_object)
                           
@app.route("/profile/<username>", methods=["GET"])
def profile_page(username):
    return render_template("profile.html", username=username)                   


def load_home_listings():
    listings = []
    try:
        for path in glob.glob(os.path.join(DATA_DIR, "home_*.json")):
            with open(path, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("views", 0)
                data.setdefault("description", "")
                data.setdefault("images", [])
                listings.append(data)
    except Exception:
        listings = []

    return sorted(listings, key=lambda home: home.get("views", 0), reverse=True)

@app.route("/", methods=["GET"])
def home_page():
    popular_homes = load_home_listings()
    return render_template("home_page.html", popular_homes=popular_homes)

@app.route("/signin", methods=["GET"])
def signin_page():
    return render_template("sign_up.html")

@app.route("/create_post", methods=["GET"])
def create_post_page():
    if "user_id" not in session:
        return redirect(url_for("signup_page"))
    return render_template("create_post.html")

@app.route("/search")
def search_page():
    return render_template("search.html")



# ---DB API Endpoints---

@app.route("/api/auth-status", methods=["GET"])
def auth_status():
    if "user_id" in session:
        user = User.query.get(session["user_id"])
        if user:
            return jsonify({
                "logged_in": True,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name
            }), 200
            
    return jsonify({"logged_in": False}), 200

@app.route("/signup", methods=["POST"])
def add_user():
    # 1. Parse incoming data safely (JSON or Form Data)
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    
    username = data.get("username")
    first_name = data.get("first_name")
    last_name = data.get("last_name")
    password = data.get("password")
    email = data.get("email")
    dob = data.get("dob")

    # 2. Extract the 'next' redirect target if it was passed via query parameters
    next_page = request.args.get("next")

    # 3. Validate and parse Date of Birth string
    if isinstance(dob, str) and dob.strip() != "":
        try:
            dob = datetime.strptime(dob, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid date format. Expected YYYY-MM-DD"}), 400
    elif dob == "":
        dob = None

    # 4. Check for duplicate unique entities
    existing_user = User.query.filter(
        (User.username == username) | (User.email == email)
    ).first()

    if existing_user:
        return jsonify({"error": "A user with this username or email already exists."}), 409

    # 5. Commit new instance data to the database
    try:
        user = User(
            username=username, 
            first_name=first_name, 
            last_name=last_name, 
            password=password, 
            email=email, 
            dob=dob
        )
        db.session.add(user)
        db.session.commit()
        
        # 6. Establish session cookie instantly so they are logged in on redirect
        session["user_id"] = user.id
        
        # 7. Return payload including the exact redirect destination path
        return jsonify({
            "message": "User created successfully",
            "user_id": user.id,
            "username": user.username,
            "next": next_page if next_page else "/"  # Fallback to home if no next parameter
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    

@app.route("/signin", methods=["POST"])
def signin():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    username_or_email = data.get("username_or_email") or data.get("username") or data.get("email")
    password = data.get("password")

    if not username_or_email or not password:
        return jsonify({"error": "Missing identifier (username/email) or password"}), 400

    try:
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()

        # If user isn't found or password verification fails
        # Note: If you aren't hashing yet, use: user.password != password
        if not user or user.password != password:
            return jsonify({"error": "Invalid username, email, or password"}), 401
        
        session.clear()  
        session.permanent = True  
        session["user_id"] = user.id
        session["username"] = user.username
        
        dob_string = user.dob.strftime("%Y-%m-%d") if user.dob else None

        return jsonify({
            "message": "Sign-in successful",
            "user": {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "dob": dob_string
            }
        }), 200

    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 500


@app.route("/get_user/<username>", methods=["GET"])
def get_user(username):
    try:
        user = User.query.filter_by(username=username).first()

        if not user:
            return jsonify({"error": "User not found or doesn't exist"}), 404
        
        dob_string = user.dob.strftime("%Y-%m-%d") if user.dob else None
        
        return jsonify({
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "dob": dob_string
        }), 200

    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 500


@app.route("/delete_user/<username>", methods=["DELETE"])
def delete_user(username):
    try:
        user = User.query.filter_by(username=username).first()

        if not user:
            return jsonify({"error": f"User '{username}' not found or doesn't exist"}), 404
        
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({"message": f"User {username} deleted successfully"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Database error: {str(e)}"}), 500


@app.route("/update_user/<username>", methods=["PUT"])
def update_user(username):
    try:
        user = User.query.filter_by(username=username).first()

        if not user:
            return jsonify({"error": "User not found or doesn't exist"}), 404
        
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form

        allowed_updates = ["username", "first_name", "last_name", "email", "dob"]
        
        for key, value in data.items():
            if key in allowed_updates:
                if key == "dob" and value:
                    try:
                        value = datetime.strptime(value, "%Y-%m-%d").date()
                    except ValueError:
                        return jsonify({"error": "Invalid dob format. Expected YYYY-MM-DD"}), 400
                
                setattr(user, key, value)

        db.session.commit()
        return jsonify({"message": f"User '{username}' updated successfully"}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Database error: {str(e)}"}), 500


@app.route("/create_post", methods=["POST"])
def create_post():
    # 1. Security Check: Ensure the user is actually logged in
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized. Please log in."}), 401
    
    # 2. Look up the user's username via their stored session ID
    current_user = User.query.get(session["user_id"])
    if not current_user:
        return jsonify({"error": "User profile not found."}), 404
    
    username = current_user.username  # This guarantees a non-null username string!

    data = request.form
    address_line1 = data.get("address_line1")
    address_line2 = data.get("address_line2", "")
    city = data.get("city")
    state = data.get("state")
    zip_code = data.get("zip_code")
    property_type = data.get("property_type")
    listing_type = data.get("listing_type")
    description = data.get("description", "")
    
    # Parse numerical data safely
    try:
        price = float(data.get("price", 0))
        square_footage = int(data.get("square_footage", 0))
        num_bedrooms = int(data.get("num_bedrooms", 0))
        num_bathrooms = float(data.get("num_bathrooms", 0)) 
        year_built = int(data.get("year_built")) if data.get("year_built") else None
    except ValueError:
        return jsonify({"error": "Invalid numerical data provided"}), 400

    # 3. Handle image array uploads
    image_filenames = []
    if "images" in request.files:
        images = request.files.getlist("images")
        for file in images:
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                
                # Make sure upload directory exists before saving
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(file_path)
                image_filenames.append(unique_filename)

    post_id = str(uuid.uuid4())

    # 4. Save to SQLAlchemy Database
    # Note: Make sure your SQLAlchemy Post model has columns for all these fields!
    post = Post(
        username=username,  # Filled correctly now
        address_line1=address_line1,
        address_line2=address_line2,
        city=city,
        state=state,
        zip_code=zip_code,
        price=price,
        views=0
    )

    try:
        db.session.add(post)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Database error: missing required fields or address duplicate"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Database crash: {str(e)}"}), 500

    # 5. Save details backup into local JSON flat-file
    new_listing = {
        "username": username,
        "id": post_id,
        "address_line1": address_line1,
        "address_line2": address_line2,
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "price": price,
        "square_footage": square_footage,
        "num_bedrooms": num_bedrooms,
        "num_bathrooms": num_bathrooms,
        "year_built": year_built,
        "property_type": property_type,
        "listing_type": listing_type,
        "description": description,
        "images": image_filenames
    }
    
    try:
        os.makedirs("seller_homes", exist_ok=True) # Ensure folder exists
        post_file_path = f"seller_homes/home_{post_id}.json"
        with open(post_file_path, "w") as f:
            json.dump(new_listing, f, indent=4)
    except Exception as e:
        return jsonify({"error": f"Failed to write JSON backup file: {str(e)}"}), 500
    
    # 6. Success JSON return string to clear up frontend JS errors
    return jsonify({"message": "Listing created successfully!"}), 201

    
@app.route("/create_db", methods=["POST"])
def create_db():
    with app.app_context():
        db.create_all()
    return {"message": "Database tables created"}

@app.route("/drop_db", methods=["DELETE"])
def drop_db():
    with app.app_context():
        db.drop_all()
    return {"message": "Database tables dropped"}

@app.route("/get_user_posts/<username>", methods=["GET"])
def get_user_posts(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return {"error": "User not found"}, 404

    posts = Post.query.filter_by(username=username).all()
    post_data = [{
        "id": post.post_id,
        "address_line1": post.address_line1,
        "address_line2": post.address_line2,
        "city": post.city,
        "state": post.state,
        "zip_code": post.zip_code,
        "price": post.price
    } for post in posts]

    return {"posts": post_data}, 200


# --- Search API Endpoint ---
@app.route("/add_to_index", methods=["POST"])
def add_to_index():
    documents_to_add = []

    for filename in os.listdir(DATA_DIR):


        path = os.path.join(DATA_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        
        listing = {
            "id": data["id"],
            "address_line1": data["address_line1"],
            "address_line2": data["address_line2"],
            "city": data["city"],
            "state": data["state"],
            "zip_code": data["zip_code"],
            "price": data["price"],
            "square_footage": data["square_footage"],
            "num_bedrooms": data["num_bedrooms"],
            "num_bathrooms": data["num_bathrooms"],
            "year_built": data["year_built"],
            "property_type": data["property_type"],
            "listing_type": data["listing_type"],
            "description": data["description"],
            "images": data["images"]
        }

        documents_to_add.append(listing)
    index.add_documents(documents_to_add)


    return jsonify({
        "added_count": len(documents_to_add),
    })

@app.route("/multi_search/<parse_for>", methods=["GET"])
def multifaceted_search(parse_for):
    results = index.search(
        parse_for,
        {'limit': 1000,

            "attributesToSearchOn": [
                "address_line1",
                "address_line2",
                "city",
                "state",
                "zip_code",
                "price",
                "square_footage",
                "num_bedrooms",
                "num_bathrooms",
                "year_built",
                "property_type",
                "listing_type",
                "description"
            ],
            "attributesToRetrieve": [
                "id",
                "address_line1",
                "address_line2",
                "city",
                "state",
                "zip_code",
                "price",
                "square_footage",
                "num_bedrooms",
                "num_bathrooms",
                "year_built",
                "property_type",
                "listing_type",
                "description",
                "images"
            ]})
                

    return jsonify(results)

@app.route("/show_index", methods=["GET"])
def show_index():
    results = index.search("")
    return jsonify(results)

@app.route("/create_index", methods=["POST"])
def create_index():
    client.create_index(INDEX_NAME)
    return {"message": "Index created successfully"}


@app.route("/delete_index", methods=["DELETE"])
def delete_index():
    client.delete_index(INDEX_NAME)
    return {"message": "Index deleted successfully"}

@app.route("/api/calculate_mortgage", methods=["POST"])
def api_calculate_mortgage():
    data = request.get_json() or {}
    
    try:
        home_price = float(data.get("home_price", 0))
        credit_score = int(data.get("credit_score", 750))
        down_payment = float(data.get("down_payment", 0))
        term_years = int(data.get("term_years", 30))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid numerical types supplied."}), 400

    # 1. Enforce Minimum Down Payment Rule Based on Credit Score
    if credit_score >= 680:
        min_down_pct = 0.03
    elif 620 <= credit_score < 680:
        min_down_pct = 0.05
    else:
        min_down_pct = 0.10
        
    min_required_down = home_price * min_down_pct
    if down_payment < min_required_down:
        return jsonify({
            "validation_error": f"Down payment of ${down_payment:,.2f} is too low. "
                                f"For a credit score of {credit_score}, a minimum down payment of "
                                f"{min_down_pct*100:.0f}% (${min_required_down:,.2f}) is required."
        }), 400
        
    # 2. Determine Base Interest Rate Adjustments & PMI Rates
    if credit_score >= 760:
        base_rate = 0.0620
        pmi_factor = 0.0030
    elif 700 <= credit_score < 760:
        base_rate = 0.0650
        pmi_factor = 0.0050
    elif 640 <= credit_score < 700:
        base_rate = 0.0700
        pmi_factor = 0.0085
    else:
        base_rate = 0.0780
        pmi_factor = 0.0110

    if term_years == 15:
        base_rate -= 0.0075  
    elif term_years != 30:
        return jsonify({"error": "Term must be either 15 or 30 years."}), 400

    # 3. Calculate Loan Details
    principal = home_price - down_payment
    down_payment_pct = down_payment / home_price
    
    monthly_rate = base_rate / 12
    total_months = term_years * 12
    
    # Amortization Formula Execution
    if monthly_rate > 0:
        p_and_i = principal * (monthly_rate * (1 + monthly_rate) ** total_months) / ((1 + monthly_rate) ** total_months - 1)
    else:
        p_and_i = principal / total_months
    
    # 4. Calculate Private Mortgage Insurance (PMI)
    if down_payment_pct < 0.20:
        monthly_pmi = (principal * pmi_factor) / 12
    else:
        monthly_pmi = 0.0
        
    total_monthly_payment = p_and_i + monthly_pmi

    # Return structured calculations back to the layout
    return jsonify({
        "interest_rate_percentage": round(base_rate * 100, 3),
        "monthly_principal_and_interest": round(p_and_i, 2),
        "monthly_pmi": round(monthly_pmi, 2),
        "total_estimated_initial_monthly": round(total_monthly_payment, 2)
    }), 200

if __name__ == "__main__":
    app.run(debug=True)
