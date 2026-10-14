"""Dataset definitions and generator for CodeCourt Phase 4 benchmarks.

T4.1: Constructs 50 ground-truth labeled PR cases:
- 20 Dev split cases (14 injected bugs, 6 clean PRs)
- 30 Test split cases (21 injected bugs, 9 clean PRs)
Total: 35 injected bug cases, 15 clean cases across Python and TypeScript.
"""

import json
from pathlib import Path

from eval.schema import EvalCase, EvalDataset, GroundTruthFinding

# ---------------------------------------------------------------------------
# DEV CASES (20 cases: 14 bugs, 6 clean)
# ---------------------------------------------------------------------------

DEV_CASES: list[EvalCase] = [
    # 1. Dev Sec: SQL injection
    EvalCase(
        id="dev_01_py_sec_sqli",
        split="dev",
        language="python",
        category="security",
        has_bug=True,
        pr_title="Add user authentication query helper",
        pr_description="Helper function for querying user credentials from DB.",
        filename="app/auth.py",
        diff_text="""diff --git a/app/auth.py b/app/auth.py
index 1000001..2000001 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -10,3 +10,6 @@ def get_db_connection():
+def authenticate_user(db, username, password):
+    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
+    return db.execute(query).fetchone()
""",
        ground_truth=GroundTruthFinding(
            file="app/auth.py",
            line_start=11,
            line_end=12,
            category="security",
            severity="critical",
            title="SQL injection via formatted query string",
            description="Untrusted username and password formatted directly into SQL query.",
            evidence_snippet="query = f\"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'\"",
        ),
    ),
    # 2. Dev Sec: Path traversal
    EvalCase(
        id="dev_02_py_sec_path_traversal",
        split="dev",
        language="python",
        category="security",
        has_bug=True,
        pr_title="Add file retrieval utility",
        pr_description="Allows fetching uploaded documents by filename.",
        filename="app/storage.py",
        diff_text="""diff --git a/app/storage.py b/app/storage.py
index 1000002..2000002 100644
--- a/app/storage.py
+++ b/app/storage.py
@@ -10,3 +10,6 @@ UPLOAD_DIR = "/var/app/uploads"
+def get_user_file(filename: str) -> bytes:
+    file_path = os.path.join(UPLOAD_DIR, filename)
+    with open(file_path, "rb") as f:
+        return f.read()
""",
        ground_truth=GroundTruthFinding(
            file="app/storage.py",
            line_start=11,
            line_end=12,
            category="security",
            severity="high",
            title="Path traversal via unvalidated filename",
            description="os.path.join with untrusted filename permits escaping UPLOAD_DIR via '../'.",
            evidence_snippet="file_path = os.path.join(UPLOAD_DIR, filename)",
        ),
    ),
    # 3. Dev Sec: Hardcoded secret
    EvalCase(
        id="dev_03_py_sec_hardcoded_secret",
        split="dev",
        language="python",
        category="security",
        has_bug=True,
        pr_title="Configure cloud storage credentials",
        pr_description="Sets up S3 configuration for media uploads.",
        filename="app/config.py",
        diff_text="""diff --git a/app/config.py b/app/config.py
index 1000003..2000003 100644
--- a/app/config.py
+++ b/app/config.py
@@ -5,3 +5,6 @@ S3_BUCKET = "my-app-media"
+AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
+AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
+S3_REGION = "us-east-1"
""",
        ground_truth=GroundTruthFinding(
            file="app/config.py",
            line_start=5,
            line_end=6,
            category="security",
            severity="critical",
            title="Hardcoded AWS credentials in config",
            description="Static AWS access key and secret committed directly into code.",
            evidence_snippet='AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"',
        ),
    ),
    # 4. Dev Sec: SSRF
    EvalCase(
        id="dev_04_py_sec_ssrf",
        split="dev",
        language="python",
        category="security",
        has_bug=True,
        pr_title="Add webhook notification dispatcher",
        pr_description="Calls external URLs to notify subscribers of events.",
        filename="app/webhooks.py",
        diff_text="""diff --git a/app/webhooks.py b/app/webhooks.py
index 1000004..2000004 100644
--- a/app/webhooks.py
+++ b/app/webhooks.py
@@ -8,3 +8,5 @@ import requests
+def dispatch_webhook(target_url: str, payload: dict) -> int:
+    response = requests.post(target_url, json=payload, timeout=5)
+    return response.status_code
""",
        ground_truth=GroundTruthFinding(
            file="app/webhooks.py",
            line_start=9,
            line_end=10,
            category="security",
            severity="high",
            title="Server-Side Request Forgery (SSRF)",
            description="Posting to arbitrary user-supplied target_url without allowlist or IP check.",
            evidence_snippet="response = requests.post(target_url, json=payload, timeout=5)",
        ),
    ),
    # 5. Dev Sec: XSS
    EvalCase(
        id="dev_05_ts_sec_xss",
        split="dev",
        language="typescript",
        category="security",
        has_bug=True,
        pr_title="Render formatted user bio in profile",
        pr_description="Displays rich bio HTML on the user profile view.",
        filename="src/components/UserProfile.tsx",
        diff_text="""diff --git a/src/components/UserProfile.tsx b/src/components/UserProfile.tsx
index 1000005..2000005 100644
--- a/src/components/UserProfile.tsx
+++ b/src/components/UserProfile.tsx
@@ -10,3 +10,6 @@ interface Props { bioHtml: string; }
+export const UserBio: React.FC<Props> = ({ bioHtml }) => {
+  return <div id="user-bio" dangerouslySetInnerHTML={{ __html: bioHtml }} />;
+};
""",
        ground_truth=GroundTruthFinding(
            file="src/components/UserProfile.tsx",
            line_start=11,
            line_end=11,
            category="security",
            severity="high",
            title="Cross-Site Scripting via dangerouslySetInnerHTML",
            description="Unsanitized user bio rendered directly into DOM allows script injection.",
            evidence_snippet='return <div id="user-bio" dangerouslySetInnerHTML={{ __html: bioHtml }} />;',
        ),
    ),
    # 6. Dev Perf: N+1 queries
    EvalCase(
        id="dev_06_py_perf_n_plus_one",
        split="dev",
        language="python",
        category="performance",
        has_bug=True,
        pr_title="Fetch customer order counts for report",
        pr_description="Calculates total orders per customer for export.",
        filename="app/services/orders.py",
        diff_text="""diff --git a/app/services/orders.py b/app/services/orders.py
index 1000006..2000006 100644
--- a/app/services/orders.py
+++ b/app/services/orders.py
@@ -12,3 +12,7 @@ def get_active_customer_ids(db):
+def get_customer_orders_summary(db, customer_ids: list[int]):
+    summaries = []
+    for cid in customer_ids:
+        orders = db.query(Order).filter(Order.customer_id == cid).all()
+        summaries.append({"customer_id": cid, "count": len(orders)})
+    return summaries
""",
        ground_truth=GroundTruthFinding(
            file="app/services/orders.py",
            line_start=14,
            line_end=16,
            category="performance",
            severity="high",
            title="N+1 database query in loop",
            description="Executing individual DB query inside loop over customer_ids.",
            evidence_snippet="orders = db.query(Order).filter(Order.customer_id == cid).all()",
        ),
    ),
    # 7. Dev Perf: Async blocking sleep
    EvalCase(
        id="dev_07_py_perf_async_blocking",
        split="dev",
        language="python",
        category="performance",
        has_bug=True,
        pr_title="Add rate-limiting delay to export endpoint",
        pr_description="Adds delay to throttle heavy export processing.",
        filename="app/api/endpoints.py",
        diff_text="""diff --git a/app/api/endpoints.py b/app/api/endpoints.py
index 1000007..2000007 100644
--- a/app/api/endpoints.py
+++ b/app/api/endpoints.py
@@ -14,3 +14,6 @@ router = APIRouter()
+@router.get("/delayed-export")
+async def delayed_export():
+    time.sleep(3.0)
+    return {"status": "ready"}
""",
        ground_truth=GroundTruthFinding(
            file="app/api/endpoints.py",
            line_start=16,
            line_end=16,
            category="performance",
            severity="high",
            title="Blocking synchronous time.sleep in async endpoint",
            description="Calling time.sleep halts the entire asyncio event loop for 3 seconds.",
            evidence_snippet="time.sleep(3.0)",
        ),
    ),
    # 8. Dev Perf: Quadratic lookup in loop
    EvalCase(
        id="dev_08_py_perf_quadratic_lookup",
        split="dev",
        language="python",
        category="performance",
        has_bug=True,
        pr_title="Add filter for existing identifiers",
        pr_description="Excludes already processed IDs from batch import.",
        filename="app/utils/dedup.py",
        diff_text="""diff --git a/app/utils/dedup.py b/app/utils/dedup.py
index 1000008..2000008 100644
--- a/app/utils/dedup.py
+++ b/app/utils/dedup.py
@@ -8,3 +8,5 @@ def sanitize_id(identifier: str) -> str:
+def filter_new_ids(incoming: list[str], existing: list[str]) -> list[str]:
+    return [item for item in incoming if item not in existing]
""",
        ground_truth=GroundTruthFinding(
            file="app/utils/dedup.py",
            line_start=9,
            line_end=9,
            category="performance",
            severity="medium",
            title="O(N*M) list containment check in comprehension",
            description="Searching in list instead of set causes quadratic complexity.",
            evidence_snippet="return [item for item in incoming if item not in existing]",
        ),
    ),
    # 9. Dev Perf: Memory leak unremoved event listener
    EvalCase(
        id="dev_09_ts_perf_unremoved_listener",
        split="dev",
        language="typescript",
        category="performance",
        has_bug=True,
        pr_title="Track window resize in custom hook",
        pr_description="Hook exposing current window width.",
        filename="src/hooks/useWindowWidth.ts",
        diff_text="""diff --git a/src/hooks/useWindowWidth.ts b/src/hooks/useWindowWidth.ts
index 1000009..2000009 100644
--- a/src/hooks/useWindowWidth.ts
+++ b/src/hooks/useWindowWidth.ts
@@ -5,3 +5,8 @@ import { useState, useEffect } from "react";
+export function useWindowWidth(): number {
+  const [width, setWidth] = useState(window.innerWidth);
+  useEffect(() => {
+    window.addEventListener("resize", () => setWidth(window.innerWidth));
+  }, []);
+  return width;
+}
""",
        ground_truth=GroundTruthFinding(
            file="src/hooks/useWindowWidth.ts",
            line_start=8,
            line_end=9,
            category="performance",
            severity="medium",
            title="Uncleaned window event listener causes memory leak",
            description="useEffect adds resize listener without returning cleanup function.",
            evidence_snippet='window.addEventListener("resize", () => setWidth(window.innerWidth));',
        ),
    ),
    # 10. Dev Maint: Cyclomatic complexity
    EvalCase(
        id="dev_10_py_maint_cyclomatic_complexity",
        split="dev",
        language="python",
        category="maintainability",
        has_bug=True,
        pr_title="Implement tiered discount calculation",
        pr_description="Calculates customer discounts based on user tier and attributes.",
        filename="app/services/pricing.py",
        diff_text="""diff --git a/app/services/pricing.py b/app/services/pricing.py
index 1000010..2000010 100644
--- a/app/services/pricing.py
+++ b/app/services/pricing.py
@@ -10,3 +10,15 @@ BASE_TAX = 0.05
+def compute_discount(tier, country, promo, partner, student, total):
+    if tier == "GOLD":
+        if country == "US":
+            if promo == "VIP": return total * 0.3
+            elif promo == "SUMMER": return total * 0.2
+            else: return total * 0.1
+        elif country == "UK": return total * 0.15
+        else: return total * 0.05
+    elif tier == "SILVER":
+        if partner and not student: return total * 0.08
+        elif student: return total * 0.12
+        else: return 0.0
+    return 0.0
""",
        ground_truth=GroundTruthFinding(
            file="app/services/pricing.py",
            line_start=11,
            line_end=22,
            category="maintainability",
            severity="medium",
            title="High cyclomatic complexity and deeply nested conditionals",
            description="Deep nesting (McCabe > 10) violates single responsibility and impairs readability.",
            evidence_snippet="def compute_discount(tier, country, promo, partner, student, total):",
        ),
    ),
    # 11. Dev Maint: Duplicated calculation code
    EvalCase(
        id="dev_11_py_maint_code_duplication",
        split="dev",
        language="python",
        category="maintainability",
        has_bug=True,
        pr_title="Add billing calculation for domestic and international orders",
        pr_description="Separate calculations for domestic and international tax breakdown.",
        filename="app/services/billing.py",
        diff_text="""diff --git a/app/services/billing.py b/app/services/billing.py
index 1000011..2000011 100644
--- a/app/services/billing.py
+++ b/app/services/billing.py
@@ -15,3 +15,11 @@ def get_currency(): return "USD"
+def calc_domestic(subtotal):
+    fee = subtotal * 0.0825
+    service = subtotal * 0.02
+    surch = 1.5 if subtotal > 50 else 0.5
+    return round(subtotal + fee + service + surch, 2)
+def calc_intl(subtotal):
+    fee = subtotal * 0.0825
+    service = subtotal * 0.02
+    surch = 1.5 if subtotal > 50 else 0.5
+    return round(subtotal + fee + service + surch, 2)
""",
        ground_truth=GroundTruthFinding(
            file="app/services/billing.py",
            line_start=15,
            line_end=24,
            category="maintainability",
            severity="low",
            title="Identical calculation duplicated across functions",
            description="Duplicate fee and surcharge logic should be extracted into a shared helper.",
            evidence_snippet="def calc_intl(subtotal):",
        ),
    ),
    # 12. Dev Maint: Swallowed error in catch
    EvalCase(
        id="dev_12_ts_maint_swallowed_error",
        split="dev",
        language="typescript",
        category="maintainability",
        has_bug=True,
        pr_title="Add user profile fetch helper",
        pr_description="Fetches user profile data from backend API.",
        filename="src/api/client.ts",
        diff_text="""diff --git a/src/api/client.ts b/src/api/client.ts
index 1000012..2000012 100644
--- a/src/api/client.ts
+++ b/src/api/client.ts
@@ -10,3 +10,8 @@ export interface User { id: string; name: string; }
+export async function fetchUser(id: string): Promise<User | null> {
+  try {
+    const res = await fetch(`/api/users/${id}`);
+    return await res.json();
+  } catch (err) {
+    return null;
+  }
+}
""",
        ground_truth=GroundTruthFinding(
            file="src/api/client.ts",
            line_start=15,
            line_end=17,
            category="maintainability",
            severity="medium",
            title="Silently swallowed error in catch block",
            description="Empty catch block hides network and decoding failures without logging.",
            evidence_snippet="} catch (err) {\n    return null;\n  }",
        ),
    ),
    # 13. Dev Corr: Mutable default argument
    EvalCase(
        id="dev_13_py_corr_mutable_default",
        split="dev",
        language="python",
        category="correctness",
        has_bug=True,
        pr_title="Add user registration helper with default roles",
        pr_description="Helper creating user dictionary with default role list.",
        filename="app/models/user.py",
        diff_text="""diff --git a/app/models/user.py b/app/models/user.py
index 1000013..2000013 100644
--- a/app/models/user.py
+++ b/app/models/user.py
@@ -6,3 +6,5 @@ class UserRole(str, Enum): USER = "user"
+def create_user_profile(username: str, roles: list[str] = []) -> dict:
+    roles.append("basic")
+    return {"username": username, "roles": roles}
""",
        ground_truth=GroundTruthFinding(
            file="app/models/user.py",
            line_start=7,
            line_end=8,
            category="correctness",
            severity="high",
            title="Mutable default list argument causes shared state",
            description="Default argument roles=[] retains mutated elements across invocations.",
            evidence_snippet="def create_user_profile(username: str, roles: list[str] = []) -> dict:",
        ),
    ),
    # 14. Dev Corr: Off by one loop bound
    EvalCase(
        id="dev_14_ts_corr_off_by_one",
        split="dev",
        language="typescript",
        category="correctness",
        has_bug=True,
        pr_title="Calculate numerical sum helper",
        pr_description="Helper function to sum numbers in an array.",
        filename="src/utils/math.ts",
        diff_text="""diff --git a/src/utils/math.ts b/src/utils/math.ts
index 1000014..2000014 100644
--- a/src/utils/math.ts
+++ b/src/utils/math.ts
@@ -8,3 +8,7 @@ export const PI = 3.14159;
+export function sumNumbers(values: number[]): number {
+  let sum = 0;
+  for (let i = 0; i <= values.length; i++) {
+    sum += values[i];
+  }
+  return sum;
+}
""",
        ground_truth=GroundTruthFinding(
            file="src/utils/math.ts",
            line_start=11,
            line_end=12,
            category="correctness",
            severity="medium",
            title="Off-by-one loop condition causes out of bounds access",
            description="Loop condition i <= values.length accesses index values.length (undefined).",
            evidence_snippet="for (let i = 0; i <= values.length; i++) {",
        ),
    ),
    # 15. Dev Clean 1: Python clean email validator
    EvalCase(
        id="dev_15_py_clean_email_validator",
        split="dev",
        language="python",
        category="clean",
        has_bug=False,
        pr_title="Add robust email format validator",
        pr_description="Validates email format using regex with proper boundary rules.",
        filename="app/utils/validation.py",
        diff_text=r"""diff --git a/app/utils/validation.py b/app/utils/validation.py
index 1000015..2000015 100644
--- a/app/utils/validation.py
+++ b/app/utils/validation.py
@@ -10,3 +10,7 @@ import re
+EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
+
+def is_valid_email(email: str) -> bool:
+    if not email or len(email) > 254:
+        return False
+    return bool(EMAIL_PATTERN.match(email.strip()))
""",
    ),
    # 16. Dev Clean 2: Python clean Pydantic model
    EvalCase(
        id="dev_16_py_clean_pydantic_schema",
        split="dev",
        language="python",
        category="clean",
        has_bug=False,
        pr_title="Add UserProfileUpdate schema",
        pr_description="Pydantic v2 schema for updating user details with field constraints.",
        filename="app/schemas/profile.py",
        diff_text="""diff --git a/app/schemas/profile.py b/app/schemas/profile.py
index 1000016..2000016 100644
--- a/app/schemas/profile.py
+++ b/app/schemas/profile.py
@@ -5,3 +5,8 @@ from pydantic import BaseModel, Field
+class UserProfileUpdate(BaseModel):
+    display_name: str = Field(..., min_length=2, max_length=50)
+    bio: str | None = Field(default=None, max_length=500)
+    website: str | None = Field(default=None, max_length=200)
+    notifications_enabled: bool = True
""",
    ),
    # 17. Dev Clean 3: Python clean timezone helper
    EvalCase(
        id="dev_17_py_clean_timezone_helper",
        split="dev",
        language="python",
        category="clean",
        has_bug=False,
        pr_title="Add UTC timestamp formatting helper",
        pr_description="Converts naive datetimes to ISO 8601 UTC strings.",
        filename="app/utils/dates.py",
        diff_text="""diff --git a/app/utils/dates.py b/app/utils/dates.py
index 1000017..2000017 100644
--- a/app/utils/dates.py
+++ b/app/utils/dates.py
@@ -6,3 +6,6 @@ from datetime import datetime, timezone
+def format_utc_iso(dt: datetime) -> str:
+    if dt.tzinfo is None:
+        dt = dt.replace(tzinfo=timezone.utc)
+    return dt.astimezone(timezone.utc).isoformat()
""",
    ),
    # 18. Dev Clean 4: TS clean Button component
    EvalCase(
        id="dev_18_ts_clean_button_component",
        split="dev",
        language="typescript",
        category="clean",
        has_bug=False,
        pr_title="Add reusable Button UI component",
        pr_description="Standard button with variant styling and accessibility support.",
        filename="src/components/Button.tsx",
        diff_text="""diff --git a/src/components/Button.tsx b/src/components/Button.tsx
index 1000018..2000018 100644
--- a/src/components/Button.tsx
+++ b/src/components/Button.tsx
@@ -4,3 +4,9 @@ import React from "react";
+export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
+  variant?: "primary" | "secondary";
+}
+
+export const Button: React.FC<ButtonProps> = ({ variant = "primary", children, disabled, ...rest }) => {
+  const baseStyle = variant === "primary" ? "bg-blue-600 text-white" : "bg-gray-200 text-black";
+  return <button className={`px-4 py-2 rounded ${baseStyle}`} disabled={disabled} {...rest}>{children}</button>;
+};
""",
    ),
    # 19. Dev Clean 5: TS clean pagination types
    EvalCase(
        id="dev_19_ts_clean_pagination_types",
        split="dev",
        language="typescript",
        category="clean",
        has_bug=False,
        pr_title="Add pagination TypeScript interfaces",
        pr_description="Defines generic PaginatedResponse and query parameter types.",
        filename="src/types/pagination.ts",
        diff_text="""diff --git a/src/types/pagination.ts b/src/types/pagination.ts
index 1000019..2000019 100644
--- a/src/types/pagination.ts
+++ b/src/types/pagination.ts
@@ -1,3 +1,8 @@
+export interface PaginatedResult<T> {
+  items: T[];
+  total: number;
+  page: number;
+  pageSize: number;
+  hasNext: boolean;
+}
""",
    ),
    # 20. Dev Clean 6: Python clean health check
    EvalCase(
        id="dev_20_py_clean_health_check",
        split="dev",
        language="python",
        category="clean",
        has_bug=False,
        pr_title="Add health check ping route",
        pr_description="FastAPI endpoint returning healthy status and server time.",
        filename="app/api/health.py",
        diff_text="""diff --git a/app/api/health.py b/app/api/health.py
index 1000020..2000020 100644
--- a/app/api/health.py
+++ b/app/api/health.py
@@ -8,3 +8,6 @@ router = APIRouter()
+@router.get("/healthz")
+async def health_check():
+    return {"status": "ok", "service": "codecourt-eval"}
""",
    ),
]


def get_dev_dataset() -> EvalDataset:
    """Return the dev split dataset."""
    return EvalDataset(cases=DEV_CASES)


def export_dev_cases_json(output_path: Path) -> None:
    """Serialize the dev split cases to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([c.model_dump() for c in DEV_CASES], f, indent=2)
