"""
VULNERABLE CONFIG — FOR DEMO/TESTING PURPOSES ONLY
"""

import os

# VULN: Debug mode in production
DEBUG = True
TESTING = True

# VULN: Hardcoded database credentials
DATABASE_URL = "postgresql://admin:password123@localhost:5432/myapp"
REDIS_URL = "redis://:secretpassword@localhost:6379/0"

# VULN: Overly permissive CORS
CORS_ORIGINS = ["*"]
CORS_ALLOW_CREDENTIALS = True

# VULN: Hardcoded secret keys
SECRET_KEY = "this-is-a-very-secret-key-12345"
ENCRYPTION_KEY = "aes-256-key-do-not-commit"

# VULN: Insecure session config
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = None

# VULN: Exposed internal paths
LOG_FILE = "/var/log/myapp/debug.log"
UPLOAD_DIR = "/tmp/uploads"

# VULN: No rate limiting config
MAX_LOGIN_ATTEMPTS = 999999
RATE_LIMIT_ENABLED = False
