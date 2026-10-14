"""Unit tests for the Git unified diff parser."""

from backend.app.services.diff_parser import parse_unified_diff

SAMPLE_MODIFIED_DIFF = """diff --git a/backend/routes.py b/backend/routes.py
index abc1234..def5678 100644
--- a/backend/routes.py
+++ b/backend/routes.py
@@ -10,4 +10,6 @@ def get_user():
     context = get_context()
-    return db.query("SELECT * FROM users")
+    user_id = request.args.get("id")
+    return db.query(f"SELECT * FROM users WHERE id = {user_id}")
     cleanup()
"""

SAMPLE_NEW_FILE_DIFF = """diff --git a/auth/jwt.py b/auth/jwt.py
new file mode 100644
index 0000000..89ab123
--- /dev/null
+++ b/auth/jwt.py
@@ -0,0 +1,4 @@
+import jwt
+
+def decode():
+    pass
"""

SAMPLE_DELETED_FILE_DIFF = """diff --git a/old_module.py b/old_module.py
deleted file mode 100644
index 1234567..0000000
--- a/old_module.py
+++ /dev/null
@@ -1,3 +0,0 @@
-def deprecated():
-    pass
-print("goodbye")
"""

SAMPLE_RENAME_DIFF = """diff --git a/old_utils.py b/new_utils.py
similarity index 95%
rename from old_utils.py
rename to new_utils.py
index 1111111..2222222 100644
--- a/old_utils.py
+++ b/new_utils.py
@@ -1,3 +1,3 @@
 def util():
-    return 1
+    return 2
"""

SAMPLE_BINARY_DIFF = """diff --git a/assets/logo.png b/assets/logo.png
index 1234567..89abcde 100644
Binary files a/assets/logo.png and b/assets/logo.png differ
"""

SAMPLE_MULTI_HUNK_DIFF = """diff --git a/app/main.py b/app/main.py
index 111..222 100644
--- a/app/main.py
+++ b/app/main.py
@@ -5,3 +5,4 @@ import os
 import sys
+import logging

@@ -50,3 +51,4 @@ def run():
     start()
+    finish()
"""


def test_parse_empty_diff() -> None:
    parsed = parse_unified_diff("")
    assert len(parsed.files) == 0
    assert parsed.total_additions == 0
    assert parsed.total_deletions == 0


def test_parse_modified_file() -> None:
    parsed = parse_unified_diff(SAMPLE_MODIFIED_DIFF)
    assert len(parsed.files) == 1
    f = parsed.files[0]
    assert f.old_path == "backend/routes.py"
    assert f.new_path == "backend/routes.py"
    assert f.status == "modified"
    assert not f.is_binary
    assert len(f.hunks) == 1

    hunk = f.hunks[0]
    assert hunk.old_start == 10
    assert hunk.old_lines == 4
    assert hunk.new_start == 10
    assert hunk.new_lines == 6
    assert hunk.heading == "def get_user():"

    # Line mapping checks
    assert f.additions == 2
    assert f.deletions == 1
    assert 10 in f.modified_line_numbers  # context
    assert 11 in f.modified_line_numbers  # added user_id
    assert 12 in f.modified_line_numbers  # added return
    assert 11 in f.added_line_numbers
    assert 12 in f.added_line_numbers
    assert 9 not in f.modified_line_numbers


def test_parse_new_file() -> None:
    parsed = parse_unified_diff(SAMPLE_NEW_FILE_DIFF)
    assert len(parsed.files) == 1
    f = parsed.files[0]
    assert f.old_path is None
    assert f.new_path == "auth/jwt.py"
    assert f.status == "added"
    assert not f.is_binary
    assert f.additions == 4
    assert f.deletions == 0
    assert f.added_line_numbers == {1, 2, 3, 4}


def test_parse_deleted_file() -> None:
    parsed = parse_unified_diff(SAMPLE_DELETED_FILE_DIFF)
    assert len(parsed.files) == 1
    f = parsed.files[0]
    assert f.old_path == "old_module.py"
    assert f.new_path is None
    assert f.status == "deleted"
    assert f.additions == 0
    assert f.deletions == 3


def test_parse_renamed_file() -> None:
    parsed = parse_unified_diff(SAMPLE_RENAME_DIFF)
    assert len(parsed.files) == 1
    f = parsed.files[0]
    assert f.old_path == "old_utils.py"
    assert f.new_path == "new_utils.py"
    assert f.status == "renamed"
    assert f.additions == 1
    assert f.deletions == 1


def test_parse_binary_file() -> None:
    parsed = parse_unified_diff(SAMPLE_BINARY_DIFF)
    assert len(parsed.files) == 1
    f = parsed.files[0]
    assert f.is_binary is True
    assert f.status == "binary"
    assert len(f.hunks) == 0


def test_parse_multiple_hunks() -> None:
    parsed = parse_unified_diff(SAMPLE_MULTI_HUNK_DIFF)
    assert len(parsed.files) == 1
    f = parsed.files[0]
    assert len(f.hunks) == 2

    hunk1 = f.hunks[0]
    assert hunk1.new_start == 5
    assert hunk1.new_lines == 4

    hunk2 = f.hunks[1]
    assert hunk2.new_start == 51
    assert hunk2.new_lines == 4


def test_is_line_in_diff_helper() -> None:
    parsed = parse_unified_diff(SAMPLE_MODIFIED_DIFF)
    # Line 11 is in modified hunks for backend/routes.py
    assert parsed.is_line_in_diff("backend/routes.py", 11) is True
    # Line 99 is outside
    assert parsed.is_line_in_diff("backend/routes.py", 99) is False
    # Unknown file is False
    assert parsed.is_line_in_diff("nonexistent.py", 11) is False


def test_hunk_header_without_count() -> None:
    diff_single = """diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-old
+new
"""
    parsed = parse_unified_diff(diff_single)
    assert len(parsed.files) == 1
    hunk = parsed.files[0].hunks[0]
    assert hunk.old_start == 1
    assert hunk.old_lines == 1
    assert hunk.new_start == 1
    assert hunk.new_lines == 1


def test_no_newline_marker_handled() -> None:
    diff_no_newline = """diff --git a/file.txt b/file.txt
--- a/file.txt
+++ b/file.txt
@@ -1,2 +1,2 @@
-one
+two
\\ No newline at end of file
"""
    parsed = parse_unified_diff(diff_no_newline)
    assert len(parsed.files) == 1
    assert parsed.files[0].additions == 1
    assert parsed.files[0].deletions == 1
