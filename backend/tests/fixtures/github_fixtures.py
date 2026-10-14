"""Test fixtures containing realistic GitHub API responses."""

from typing import Any

SAMPLE_PR_RESPONSE: dict[str, Any] = {
    "id": 8492019,
    "number": 101,
    "state": "open",
    "locked": False,
    "title": "feat(auth): implement JWT token verification with expiration",
    "user": {
        "login": "octocat",
        "id": 583231,
        "type": "User",
        "site_admin": False,
    },
    "body": "This PR implements JWT verification with expiration check and unit tests.",
    "created_at": "2026-10-08T08:00:00Z",
    "updated_at": "2026-10-08T08:30:00Z",
    "closed_at": None,
    "merged_at": None,
    "html_url": "https://github.com/octocat/Hello-World/pull/101",
    "diff_url": "https://github.com/octocat/Hello-World/pull/101.diff",
    "head": {
        "label": "octocat:feat/jwt-auth",
        "ref": "feat/jwt-auth",
        "sha": "7d9b9a6d89283f3e1b01c34a2c9182390234abcd",
        "user": {"login": "octocat"},
        "repo": {"id": 1296269, "name": "Hello-World"},
    },
    "base": {
        "label": "octocat:main",
        "ref": "main",
        "sha": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
        "user": {"login": "octocat"},
        "repo": {"id": 1296269, "name": "Hello-World"},
    },
    "changed_files": 2,
    "additions": 45,
    "deletions": 5,
}

SAMPLE_DIFF: str = """diff --git a/auth/jwt.py b/auth/jwt.py
new file mode 100644
index 0000000..89ab123
--- /dev/null
+++ b/auth/jwt.py
@@ -0,0 +1,15 @@
+import jwt
+from datetime import datetime, timezone
+
+SECRET = "insecure-hardcoded-secret"
+
+def decode_token(token: str) -> dict:
+    # Potential security flaw: verify_exp=False
+    return jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_exp": False})
diff --git a/backend/routes.py b/backend/routes.py
index abc1234..def5678 100644
--- a/backend/routes.py
+++ b/backend/routes.py
@@ -10,3 +10,5 @@ def get_user():
-    return db.query("SELECT * FROM users")
+    user_id = request.args.get("id")
+    return db.query(f"SELECT * FROM users WHERE id = {user_id}")
"""

SAMPLE_FILE_CONTENT: str = """import jwt
from datetime import datetime, timezone

SECRET = "insecure-hardcoded-secret"

def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_exp": False})
"""
