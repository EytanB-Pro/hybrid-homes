from flask import Flask, request, render_template, jsonify
from datetime import datetime 
from databases.config import DevConfig
from databases.user_rdb import db, User

app = Flask(__name__, template_folder="html_templates")
app.config.from_object(DevConfig)
db.init_app(app)

@app.route("/signup", methods=["GET"])
def signup_page():
    return render_template("log_in.html")

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

@app.route("/create_db", methods=["POST"])
def create_db():
    with app.app_context():
        db.create_all()
    return {"message": "Database tables created"}

if __name__ == "__main__":
    app.run(debug=True)
