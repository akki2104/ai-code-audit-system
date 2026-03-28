"""
VULNERABLE FLASK APP — FOR DEMO/TESTING PURPOSES ONLY

⚠️  WARNING: This application contains INTENTIONAL security vulnerabilities
for testing the AI Code Audit System. DO NOT deploy this in production.
"""

from flask import Flask, request, jsonify
import sqlite3
import os
import pickle
import subprocess

app = Flask(__name__)
app.config['DEBUG'] = True  # VULN: Debug mode enabled in production
app.config['SECRET_KEY'] = 'super-secret-key-123'  # VULN: Hardcoded secret

API_KEY = "sk-1234567890abcdef"  # VULN: Hardcoded API key
DB_PASSWORD = "admin123"         # VULN: Hardcoded credential
AWS_SECRET = "AKIAIOSFODNN7EXAMPLE"  # VULN: Hardcoded AWS key


def get_db():
    return sqlite3.connect("app.db")


@app.route("/user")
def get_user():
    # VULN: SQL Injection via string concatenation
    name = request.args.get("name")
    db = get_db()
    result = db.execute("SELECT * FROM users WHERE name = '" + name + "'")
    return jsonify(result.fetchall())


@app.route("/search")
def search():
    # VULN: XSS - unescaped user input in HTML response
    query = request.args.get("q")
    return f"<h1>Results for: {query}</h1>"


@app.route("/admin/delete", methods=["POST"])
def delete_user():
    # VULN: Broken authentication - no auth check on admin endpoint
    user_id = request.json.get("id")
    db = get_db()
    # VULN: SQL Injection via f-string
    db.execute(f"DELETE FROM users WHERE id = {user_id}")
    db.commit()
    return jsonify({"status": "deleted"})


@app.route("/admin/users")
def list_users():
    # VULN: No authentication, exposes all user data
    db = get_db()
    result = db.execute("SELECT * FROM users")
    return jsonify(result.fetchall())


@app.route("/file")
def read_file():
    # VULN: Directory traversal - no path sanitization
    filename = request.args.get("name")
    with open(os.path.join("/uploads", filename)) as f:
        return f.read()


@app.route("/execute")
def execute_command():
    # VULN: Command injection
    cmd = request.args.get("cmd")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout


@app.route("/deserialize", methods=["POST"])
def deserialize_data():
    # VULN: Insecure deserialization
    data = request.get_data()
    obj = pickle.loads(data)
    return str(obj)


@app.route("/login", methods=["POST"])
def login():
    # VULN: No rate limiting, no password hashing, SQL injection
    username = request.form.get("username")
    password = request.form.get("password")
    db = get_db()
    result = db.execute(
        f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    )
    user = result.fetchone()
    if user:
        return jsonify({"status": "logged in", "user": user})
    return jsonify({"status": "failed"}), 401


# VULN: CORS misconfiguration
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    return response


if __name__ == "__main__":
    # VULN: Binding to all interfaces
    app.run(host="0.0.0.0", port=5000, debug=True)
