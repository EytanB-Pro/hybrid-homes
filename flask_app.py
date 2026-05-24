import os

from flask import Flask, request, render_template, jsonify
from datetime import datetime 
from databases.config import DevConfig
from databases.user_rdb import db, User
from werkzeug.utils import secure_filename
import json
import uuid

app = Flask(__name__, template_folder="html_templates")
app.config.from_object(DevConfig)
db.init_app(app)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route("/signup", methods=["GET"])
def signup_page():
    return render_template("log_in.html")

@app.route("/", methods=["GET"])
def home_page():
    return render_template("home_page.html")

@app.route("/signin", methods=["GET"])
def signin_page():
    return render_template("sign_up.html")

@app.route("/create_post", methods=["GET"])
def create_post_page():
    return render_template("create_post.html")


@app.route("/signup", methods=["POST"])
def add_user():
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

    if isinstance(dob, str) and dob.strip() != "":
        try:
            dob = datetime.strptime(dob, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid date format. Expected YYYY-MM-DD"}), 400
    elif dob == "":
        dob = None

    existing_user = User.query.filter(
        (User.username == username) | (User.email == email)
    ).first()

    if existing_user:
        return jsonify({"error": "A user with this username or email already exists."}), 409

    try:
        user = User(username=username, first_name=first_name, last_name=last_name, password=password, email=email, dob=dob)
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            "message": "User created successfully",
            "user_id": user.id,
            "username": user.username
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
    data = request.form
    
    address_line1 = data.get("address_line1")
    address_line2 = data.get("address_line2", "")
    city = data.get("city")
    state = data.get("state")
    zip_code = data.get("zip_code")
    
    try:
        price = float(data.get("price", 0))
        square_footage = int(data.get("square_footage", 0))
        num_bedrooms = int(data.get("num_bedrooms", 0))
        num_bathrooms = float(data.get("num_bathrooms", 0)) 
        year_built = int(data.get("year_built")) if data.get("year_built") else None
    except ValueError:
        return {"error": "Invalid numerical data provided"}, 400

    property_type = data.get("property_type") # e.g., "Condo", "House"
    listing_type = data.get("listing_type")   # e.g., "For Sale", "For Rent"
    description = data.get("description", "")
    
    # --- Amenities (Checkboxes usually submit "on" if checked, or aren't in the dict if unchecked) ---
    # has_ac = data.get("has_ac") == "on"
    # pets_allowed = data.get("pets_allowed") == "on"
    # has_parking = data.get("has_parking") == "on"


    image_filenames = []

    if "images" in request.files:
        images = request.files.getlist("images")
        
        for file in images:
            if file and file.filename != '':
                # Clean the filename
                filename = secure_filename(file.filename)
                
                # 2. Generate a unique filename to prevent overwriting files with the same name
                unique_filename = f"{uuid.uuid4()}_{filename}"
                
                # 3. Create the full path destination
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                
                # 4. Save the actual file data to your disk
                file.save(file_path)
                
                # Save the unique filename to your JSON database instead of the raw name
                image_filenames.append(unique_filename)

    post_id = str(uuid.uuid4())


    new_listing = {
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
            # "has_ac": has_ac,
            # "pets_allowed": pets_allowed,
            # "has_parking": has_parking,
            "images": image_filenames
        }
    
    post_file_path = f"seller_homes/home_{post_id}.json"

    with open(post_file_path, "w") as f:
        json.dump(new_listing, f, indent=4)
    
    return {"message": "Listing created successfully!"}, 201

    

@app.route("/create_db", methods=["POST"])
def create_db():
    with app.app_context():
        db.create_all()
    return {"message": "Database tables created"}

if __name__ == "__main__":
    app.run(debug=True)
