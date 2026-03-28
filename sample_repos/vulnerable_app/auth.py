"""
VULNERABLE AUTH MODULE — FOR DEMO/TESTING PURPOSES ONLY
"""

import hashlib
import os


# VULN: Hardcoded JWT secret
JWT_SECRET = "my-jwt-secret-key-do-not-share"

# VULN: Using MD5 for password hashing
def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


# VULN: No token expiration, no signature verification
def create_token(user_id: int) -> str:
    import base64
    import json
    payload = {"user_id": user_id, "role": "admin"}
    return base64.b64encode(json.dumps(payload).encode()).decode()


def verify_token(token: str) -> dict:
    import base64
    import json
    # VULN: No actual verification, just decodes
    try:
        return json.loads(base64.b64decode(token))
    except Exception:
        return {}


# VULN: Storing passwords in plaintext
USERS_DB = {
    "admin": {"password": "admin123", "role": "admin"},
    "user": {"password": "password", "role": "user"},
}


def authenticate(username: str, password: str) -> bool:
    user = USERS_DB.get(username)
    if user and user["password"] == password:
        return True
    return False
