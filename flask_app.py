from flask import Flask, request, render_template
from datetime import datetime  # <-- 1. Import datetime
from databases.config import DevConfig
from databases.user_rdb import db, User

app = Flask(__name__, template_folder="html_templates")
app.config.from_object(DevConfig)
db.init_app(app)

@app.route("/signup", methods=["GET"])
def signup_page():
    return render_template("log_in.html")

@app.route("/signup", methods=["POST"])
def sign_up(username, first_name, last_name, password, email, dob):
    # If dob is a string (like "1990-01-01"), convert it to a Python date object
    if isinstance(dob, str):
        try:
            dob = datetime.strptime(dob, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "Invalid date format. Expected YYYY-MM-DD"}, 400

    user = User(username=username, first_name=first_name, last_name=last_name, password=password, email=email, dob=dob)
    db.session.add(user)
    db.session.commit()
    return user

if __name__ == "__main__":
    with app.app_context():
        # This will now work without raising a TypeError
        sign_up("eytanbentsvi", "Eytan", "Bentsvi", "password123", "eytanbentsvi@example.com", "1990-01-01")
    
    app.run(debug=True)
