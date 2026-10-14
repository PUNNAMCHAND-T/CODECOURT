"""Test split dataset definitions for CodeCourt Phase 4 benchmarks.

T4.1: Contains 30 test cases:
- 21 injected bugs (7 security, 6 performance, 5 maintainability, 3 correctness)
- 9 clean PRs (5 Python, 4 TypeScript)
"""

from eval.schema import EvalCase, GroundTruthFinding

TEST_CASES: list[EvalCase] = [
    # 1. Test Sec: Command injection
    EvalCase(
        id="test_01_py_sec_command_injection",
        split="test",
        language="python",
        category="security",
        has_bug=True,
        pr_title="Add network ping diagnostic utility",
        pr_description="Utility to ping host IP or domain for connectivity check.",
        filename="app/network.py",
        diff_text="""diff --git a/app/network.py b/app/network.py
index 2000001..3000001 100644
--- a/app/network.py
+++ b/app/network.py
@@ -8,3 +8,5 @@ import os
+def ping_host(host_address: str) -> int:
+    return os.system(f"ping -c 1 {host_address}")
""",
        ground_truth=GroundTruthFinding(
            file="app/network.py",
            line_start=9,
            line_end=10,
            category="security",
            severity="critical",
            title="Command injection via os.system",
            description="Untrusted host_address passed directly into os.system shell command.",
            evidence_snippet='return os.system(f"ping -c 1 {host_address}")',
        ),
    ),
    # 2. Test Sec: Insecure deserialization via pickle
    EvalCase(
        id="test_02_py_sec_insecure_pickle",
        split="test",
        language="python",
        category="security",
        has_bug=True,
        pr_title="Add session state deserializer",
        pr_description="Deserializes base64 encoded user session state.",
        filename="app/session.py",
        diff_text="""diff --git a/app/session.py b/app/session.py
index 2000002..3000002 100644
--- a/app/session.py
+++ b/app/session.py
@@ -10,3 +10,6 @@ import base64, pickle
+def unpack_session(payload: str) -> dict:
+    raw_bytes = base64.b64decode(payload)
+    return pickle.loads(raw_bytes)
""",
        ground_truth=GroundTruthFinding(
            file="app/session.py",
            line_start=11,
            line_end=13,
            category="security",
            severity="critical",
            title="Insecure deserialization using pickle",
            description="pickle.loads on untrusted payload allows remote arbitrary code execution.",
            evidence_snippet="return pickle.loads(raw_bytes)",
        ),
    ),
    # 3. Test Sec: Weak PRNG for OTP
    EvalCase(
        id="test_03_py_sec_weak_prng",
        split="test",
        language="python",
        category="security",
        has_bug=True,
        pr_title="Generate 2FA one-time verification passcode",
        pr_description="Generates a 6-digit numeric OTP for SMS auth.",
        filename="app/tokens.py",
        diff_text="""diff --git a/app/tokens.py b/app/tokens.py
index 2000003..3000003 100644
--- a/app/tokens.py
+++ b/app/tokens.py
@@ -5,3 +5,5 @@ import random
+def generate_otp() -> str:
+    return str(random.randint(100000, 999999))
""",
        ground_truth=GroundTruthFinding(
            file="app/tokens.py",
            line_start=6,
            line_end=7,
            category="security",
            severity="high",
            title="Insecure PRNG used for security tokens",
            description="random.randint is pseudo-random and predictable; secrets module should be used.",
            evidence_snippet="return str(random.randint(100000, 999999))",
        ),
    ),
    # 4. Test Sec: Permissive CORS with credentials
    EvalCase(
        id="test_04_py_sec_permissive_cors",
        split="test",
        language="python",
        category="security",
        has_bug=True,
        pr_title="Enable CORS for local frontend testing",
        pr_description="Adds CORS middleware configuration to FastAPI app.",
        filename="app/cors.py",
        diff_text="""diff --git a/app/cors.py b/app/cors.py
index 2000004..3000004 100644
--- a/app/cors.py
+++ b/app/cors.py
@@ -10,3 +10,8 @@ def configure_cors(app):
+    app.add_middleware(
+        CORSMiddleware,
+        allow_origins=["*"],
+        allow_credentials=True,
+        allow_methods=["*"],
+    )
""",
        ground_truth=GroundTruthFinding(
            file="app/cors.py",
            line_start=11,
            line_end=15,
            category="security",
            severity="high",
            title="Permissive CORS with credentials enabled",
            description="Wildcard allow_origins with allow_credentials=True permits cross-origin data theft.",
            evidence_snippet='allow_origins=["*"],\n        allow_credentials=True,',
        ),
    ),
    # 5. Test Sec: Plaintext password storage
    EvalCase(
        id="test_05_py_sec_plaintext_password",
        split="test",
        language="python",
        category="security",
        has_bug=True,
        pr_title="Add user creation helper",
        pr_description="Creates a new User model instance from incoming registration data.",
        filename="app/users.py",
        diff_text="""diff --git a/app/users.py b/app/users.py
index 2000005..3000005 100644
--- a/app/users.py
+++ b/app/users.py
@@ -12,3 +12,6 @@ def get_user_by_email(email: str): pass
+def create_user(username: str, email: str, raw_password: str) -> User:
+    user = User(username=username, email=email, password=raw_password)
+    return user
""",
        ground_truth=GroundTruthFinding(
            file="app/users.py",
            line_start=13,
            line_end=14,
            category="security",
            severity="critical",
            title="Plaintext password assigned to User model",
            description="Storing unhashed raw_password directly in database entity.",
            evidence_snippet="user = User(username=username, email=email, password=raw_password)",
        ),
    ),
    # 6. Test Sec: Prototype pollution in TS
    EvalCase(
        id="test_06_ts_sec_prototype_pollution",
        split="test",
        language="typescript",
        category="security",
        has_bug=True,
        pr_title="Add deep object merge helper",
        pr_description="Recursive function to merge configuration objects.",
        filename="src/merge.ts",
        diff_text="""diff --git a/src/merge.ts b/src/merge.ts
index 2000006..3000006 100644
--- a/src/merge.ts
+++ b/src/merge.ts
@@ -6,3 +6,8 @@ export function isObject(item: any): boolean { return Boolean(item && typeof ite
+export function deepMerge(target: any, source: any): any {
+  for (const key of Object.keys(source)) {
+    target[key] = isObject(source[key]) ? deepMerge(target[key] || {}, source[key]) : source[key];
+  }
+  return target;
+}
""",
        ground_truth=GroundTruthFinding(
            file="src/merge.ts",
            line_start=7,
            line_end=10,
            category="security",
            severity="high",
            title="Prototype pollution in recursive object merge",
            description="Merging without filtering '__proto__' or 'constructor' allows prototype pollution.",
            evidence_snippet="target[key] = isObject(source[key]) ? deepMerge(target[key] || {}, source[key]) : source[key];",
        ),
    ),
    # 7. Test Sec: Plaintext equality timing attack
    EvalCase(
        id="test_07_py_sec_timing_attack",
        split="test",
        language="python",
        category="security",
        has_bug=True,
        pr_title="Add API key comparison check",
        pr_description="Validates client API token against expected secret.",
        filename="app/security.py",
        diff_text="""diff --git a/app/security.py b/app/security.py
index 2000007..3000007 100644
--- a/app/security.py
+++ b/app/security.py
@@ -8,3 +8,5 @@ def load_secret_key(): return "secret123"
+def verify_token(user_token: str, expected_token: str) -> bool:
+    return user_token == expected_token
""",
        ground_truth=GroundTruthFinding(
            file="app/security.py",
            line_start=9,
            line_end=10,
            category="security",
            severity="medium",
            title="Timing attack vulnerability in token equality comparison",
            description="Standard == string comparison leaks secret length/prefix via timing side-channel.",
            evidence_snippet="return user_token == expected_token",
        ),
    ),
    # 8. Test Perf: Unclosed file handle in loop
    EvalCase(
        id="test_08_py_perf_unclosed_file",
        split="test",
        language="python",
        category="performance",
        has_bug=True,
        pr_title="Export report batches to disk",
        pr_description="Writes each batch report to a separate log file.",
        filename="app/exporter.py",
        diff_text="""diff --git a/app/exporter.py b/app/exporter.py
index 2000008..3000008 100644
--- a/app/exporter.py
+++ b/app/exporter.py
@@ -10,3 +10,6 @@ def get_batch_data(): return []
+def export_batches(batches: list[dict]):
+    for i, b in enumerate(batches):
+        f = open(f"/tmp/batch_{i}.json", "w")
+        f.write(str(b))
""",
        ground_truth=GroundTruthFinding(
            file="app/exporter.py",
            line_start=11,
            line_end=14,
            category="performance",
            severity="medium",
            title="Unclosed file descriptor leak in loop",
            description="Files opened without with statement or .close() exhaust OS file descriptors.",
            evidence_snippet='f = open(f"/tmp/batch_{i}.json", "w")\n        f.write(str(b))',
        ),
    ),
    # 9. Test Perf: Unbounded file read into memory
    EvalCase(
        id="test_09_py_perf_unbounded_file_read",
        split="test",
        language="python",
        category="performance",
        has_bug=True,
        pr_title="Read uploaded log content",
        pr_description="Reads entire uploaded file into memory to count occurrences.",
        filename="app/uploads.py",
        diff_text="""diff --git a/app/uploads.py b/app/uploads.py
index 2000009..3000009 100644
--- a/app/uploads.py
+++ b/app/uploads.py
@@ -12,3 +12,6 @@ from fastapi import UploadFile
+def count_errors_in_upload(upload: UploadFile) -> int:
+    content = upload.file.read()
+    return content.count(b"ERROR")
""",
        ground_truth=GroundTruthFinding(
            file="app/uploads.py",
            line_start=13,
            line_end=14,
            category="performance",
            severity="high",
            title="Unbounded full-file read into memory",
            description="Calling .read() without chunking buffers multi-gigabyte uploads into RAM causing OOM.",
            evidence_snippet="content = upload.file.read()",
        ),
    ),
    # 10. Test Perf: Re-compile regex in loop
    EvalCase(
        id="test_10_py_perf_re_compile_loop",
        split="test",
        language="python",
        category="performance",
        has_bug=True,
        pr_title="Scan text items for pattern",
        pr_description="Filters items matching regex query.",
        filename="app/parser.py",
        diff_text="""diff --git a/app/parser.py b/app/parser.py
index 2000010..3000010 100644
--- a/app/parser.py
+++ b/app/parser.py
@@ -8,3 +8,6 @@ import re
+def filter_matching(lines: list[str], pattern_str: str) -> list[str]:
+    return [line for line in lines if re.compile(pattern_str).search(line)]
""",
        ground_truth=GroundTruthFinding(
            file="app/parser.py",
            line_start=9,
            line_end=9,
            category="performance",
            severity="medium",
            title="Redundant regex compilation inside loop comprehension",
            description="re.compile called on every iteration instead of once before loop.",
            evidence_snippet="[line for line in lines if re.compile(pattern_str).search(line)]",
        ),
    ),
    # 11. Test Perf: Global memory leak
    EvalCase(
        id="test_11_py_perf_global_memory_leak",
        split="test",
        language="python",
        category="performance",
        has_bug=True,
        pr_title="Add request latency tracking cache",
        pr_description="Stores request latencies in module list for analytics.",
        filename="app/cache.py",
        diff_text="""diff --git a/app/cache.py b/app/cache.py
index 2000011..3000011 100644
--- a/app/cache.py
+++ b/app/cache.py
@@ -5,3 +5,6 @@ LATENCY_BUFFER = []
+def record_latency(endpoint: str, ms: float):
+    LATENCY_BUFFER.append({"endpoint": endpoint, "ms": ms})
""",
        ground_truth=GroundTruthFinding(
            file="app/cache.py",
            line_start=6,
            line_end=7,
            category="performance",
            severity="high",
            title="Unbounded memory accumulation in global list",
            description="Appending to module-level list without size cap or TTL leaks memory indefinitely.",
            evidence_snippet='LATENCY_BUFFER.append({"endpoint": endpoint, "ms": ms})',
        ),
    ),
    # 12. Test Perf: Sync XMLHttpRequest in TS
    EvalCase(
        id="test_12_ts_perf_sync_xmlhttprequest",
        split="test",
        language="typescript",
        category="performance",
        has_bug=True,
        pr_title="Add synchronous configuration loader",
        pr_description="Fetches config before app initialization using sync request.",
        filename="src/sync_request.ts",
        diff_text="""diff --git a/src/sync_request.ts b/src/sync_request.ts
index 2000012..3000012 100644
--- a/src/sync_request.ts
+++ b/src/sync_request.ts
@@ -4,3 +4,8 @@ export function getBaseUrl(): string { return "/api"; }
+export function loadConfigSync(url: string): any {
+  const xhr = new XMLHttpRequest();
+  xhr.open("GET", url, false);
+  xhr.send(null);
+  return JSON.parse(xhr.responseText);
+}
""",
        ground_truth=GroundTruthFinding(
            file="src/sync_request.ts",
            line_start=6,
            line_end=8,
            category="performance",
            severity="high",
            title="Synchronous XMLHttpRequest blocks browser main thread",
            description="xhr.open with async=false freezes UI rendering and interaction until network returns.",
            evidence_snippet='xhr.open("GET", url, false);\n  xhr.send(null);',
        ),
    ),
    # 13. Test Perf: Inline object creation in React render loop
    EvalCase(
        id="test_13_ts_perf_inline_object_render",
        split="test",
        language="typescript",
        category="performance",
        has_bug=True,
        pr_title="Render user status badges in table",
        pr_description="Displays styled badge for each user in data grid.",
        filename="src/UserList.tsx",
        diff_text="""diff --git a/src/UserList.tsx b/src/UserList.tsx
index 2000013..3000013 100644
--- a/src/UserList.tsx
+++ b/src/UserList.tsx
@@ -10,3 +10,6 @@ export const UserList: React.FC<{ users: User[] }> = ({ users }) => {
+  return (
+    <div>{users.map(u => <span style={{ color: "red", padding: 8 }}>{u.name}</span>)}</div>
+  );
""",
        ground_truth=GroundTruthFinding(
            file="src/UserList.tsx",
            line_start=12,
            line_end=12,
            category="performance",
            severity="low",
            title="Inline object literal allocation inside high-frequency map loop",
            description="Re-allocates new style object for every item on every render.",
            evidence_snippet='<span style={{ color: "red", padding: 8 }}>{u.name}</span>',
        ),
    ),
    # 14. Test Maint: Deep nesting
    EvalCase(
        id="test_14_py_maint_deep_nesting",
        split="test",
        language="python",
        category="maintainability",
        has_bug=True,
        pr_title="Add nested order transition validation",
        pr_description="Validates state transitions through conditional branches.",
        filename="app/order_workflow.py",
        diff_text="""diff --git a/app/order_workflow.py b/app/order_workflow.py
index 2000014..3000014 100644
--- a/app/order_workflow.py
+++ b/app/order_workflow.py
@@ -10,3 +10,12 @@ def log_transition(o, s): pass
+def can_transition(order, target):
+    if order.is_active:
+        if order.payment_verified:
+            if not order.is_refunded:
+                if target == "SHIPPED":
+                    if order.inventory_reserved:
+                        return True
+    return False
""",
        ground_truth=GroundTruthFinding(
            file="app/order_workflow.py",
            line_start=11,
            line_end=17,
            category="maintainability",
            severity="medium",
            title="Excessive nested conditional statements",
            description="5 levels of nested if statements impairs readability and testability.",
            evidence_snippet="if order.is_active:\n        if order.payment_verified:",
        ),
    ),
    # 15. Test Maint: Cryptic single-letter variable names
    EvalCase(
        id="test_15_py_maint_cryptic_names",
        split="test",
        language="python",
        category="maintainability",
        has_bug=True,
        pr_title="Calculate pricing adjustments",
        pr_description="Applies adjustments to item prices.",
        filename="app/matrix.py",
        diff_text="""diff --git a/app/matrix.py b/app/matrix.py
index 2000015..3000015 100644
--- a/app/matrix.py
+++ b/app/matrix.py
@@ -5,3 +5,6 @@ def get_ratio(): return 1.0
+def compute_p(x, y, z, a, b):
+    t = x * y + z
+    return (t * a) - b
""",
        ground_truth=GroundTruthFinding(
            file="app/matrix.py",
            line_start=6,
            line_end=8,
            category="maintainability",
            severity="low",
            title="Cryptic uncommunicative single-letter variable names",
            description="Variables x, y, z, a, b, t convey no domain meaning.",
            evidence_snippet="def compute_p(x, y, z, a, b):\n    t = x * y + z",
        ),
    ),
    # 16. Test Maint: Magic numbers
    EvalCase(
        id="test_16_py_maint_magic_numbers",
        split="test",
        language="python",
        category="maintainability",
        has_bug=True,
        pr_title="Add shipping fee calculation",
        pr_description="Calculates shipping cost based on weight and destination.",
        filename="app/rates.py",
        diff_text="""diff --git a/app/rates.py b/app/rates.py
index 2000016..3000016 100644
--- a/app/rates.py
+++ b/app/rates.py
@@ -8,3 +8,5 @@ def get_origin(): return "NYC"
+def calc_shipping(weight: float) -> float:
+    return (weight * 1.0825) + 4.25 + (12.5 if weight > 50 else 0)
""",
        ground_truth=GroundTruthFinding(
            file="app/rates.py",
            line_start=9,
            line_end=10,
            category="maintainability",
            severity="low",
            title="Unexplained magic numbers in calculations",
            description="Magic numbers 1.0825, 4.25, and 12.5 should be defined as named constants.",
            evidence_snippet="return (weight * 1.0825) + 4.25 + (12.5 if weight > 50 else 0)",
        ),
    ),
    # 17. Test Maint: Dead unreachable code
    EvalCase(
        id="test_17_ts_maint_unreachable_code",
        split="test",
        language="typescript",
        category="maintainability",
        has_bug=True,
        pr_title="Add status redirect handler",
        pr_description="Routes users to login if unauthenticated.",
        filename="src/router.ts",
        diff_text="""diff --git a/src/router.ts b/src/router.ts
index 2000017..3000017 100644
--- a/src/router.ts
+++ b/src/router.ts
@@ -10,3 +10,7 @@ export function getPath(): string { return window.location.pathname; }
+export function checkRoute(token: string | null): string {
+  return token ? "/dashboard" : "/login";
+  const fallback = "/home";
+  console.log("routing check complete", fallback);
+}
""",
        ground_truth=GroundTruthFinding(
            file="src/router.ts",
            line_start=12,
            line_end=14,
            category="maintainability",
            severity="low",
            title="Dead unreachable code after return statement",
            description="Statements following unconditional return can never execute.",
            evidence_snippet='const fallback = "/home";\n  console.log("routing check complete", fallback);',
        ),
    ),
    # 18. Test Maint: Single responsibility violation
    EvalCase(
        id="test_18_ts_maint_srp_violation",
        split="test",
        language="typescript",
        category="maintainability",
        has_bug=True,
        pr_title="Add dashboard summary loader",
        pr_description="Fetches, transforms, and directly paints metrics onto DOM.",
        filename="src/dashboard.ts",
        diff_text="""diff --git a/src/dashboard.ts b/src/dashboard.ts
index 2000018..3000018 100644
--- a/src/dashboard.ts
+++ b/src/dashboard.ts
@@ -8,3 +8,9 @@ export function initDashboard() {}
+export async function updateStats() {
+  const res = await fetch("/api/stats");
+  const data = await res.json();
+  const total = data.sales.reduce((a: number, b: number) => a + b, 0);
+  document.getElementById("total-sales")!.innerText = `$${total.toFixed(2)}`;
+}
""",
        ground_truth=GroundTruthFinding(
            file="src/dashboard.ts",
            line_start=9,
            line_end=14,
            category="maintainability",
            severity="medium",
            title="Single Responsibility Principle violation",
            description="Function couples network fetching, financial aggregation, and DOM mutation.",
            evidence_snippet="export async function updateStats() {",
        ),
    ),
    # 19. Test Corr: Boolean operator precedence bug
    EvalCase(
        id="test_19_py_corr_boolean_precedence",
        split="test",
        language="python",
        category="correctness",
        has_bug=True,
        pr_title="Check administrative access permissions",
        pr_description="Determines whether user can access administrative settings.",
        filename="app/perms.py",
        diff_text="""diff --git a/app/perms.py b/app/perms.py
index 2000019..3000019 100644
--- a/app/perms.py
+++ b/app/perms.py
@@ -6,3 +6,5 @@ class User: is_admin: bool; is_banned: bool; is_super: bool
+def can_admin(user: User) -> bool:
+    return user.is_admin and not user.is_banned or user.is_super
""",
        ground_truth=GroundTruthFinding(
            file="app/perms.py",
            line_start=7,
            line_end=8,
            category="correctness",
            severity="high",
            title="Ambiguous boolean operator precedence flaw",
            description="'and' binds tighter than 'or', allowing banned superusers access unexpectedly.",
            evidence_snippet="return user.is_admin and not user.is_banned or user.is_super",
        ),
    ),
    # 20. Test Corr: Floating point equality check
    EvalCase(
        id="test_20_py_corr_float_equality",
        split="test",
        language="python",
        category="correctness",
        has_bug=True,
        pr_title="Check exact balance threshold",
        pr_description="Verifies if total interest reaches exact target threshold.",
        filename="app/ledger.py",
        diff_text="""diff --git a/app/ledger.py b/app/ledger.py
index 2000020..3000020 100644
--- a/app/ledger.py
+++ b/app/ledger.py
@@ -10,3 +10,5 @@ def get_base_balance(): return 100.0
+def is_exact_interest_met(principal: float, rate: float) -> bool:
+    return (principal * rate) == 10.55
""",
        ground_truth=GroundTruthFinding(
            file="app/ledger.py",
            line_start=11,
            line_end=12,
            category="correctness",
            severity="medium",
            title="Exact floating-point equality comparison",
            description="Comparing floats with == fails due to IEEE 754 precision representation errors.",
            evidence_snippet="return (principal * rate) == 10.55",
        ),
    ),
    # 21. Test Corr: Lexicographical sorting bug in TS
    EvalCase(
        id="test_21_ts_corr_lexical_sort",
        split="test",
        language="typescript",
        category="correctness",
        has_bug=True,
        pr_title="Add numeric score sorter",
        pr_description="Sorts high scores array in ascending numerical order.",
        filename="src/sorter.ts",
        diff_text="""diff --git a/src/sorter.ts b/src/sorter.ts
index 2000021..3000021 100644
--- a/src/sorter.ts
+++ b/src/sorter.ts
@@ -5,3 +5,5 @@ export interface ScoreRecord { id: string; }
+export function sortScores(scores: number[]): number[] {
+  return [...scores].sort();
+}
""",
        ground_truth=GroundTruthFinding(
            file="src/sorter.ts",
            line_start=6,
            line_end=8,
            category="correctness",
            severity="medium",
            title="Default Array.sort() sorts numbers lexicographically",
            description="Calling .sort() without compare function sorts numbers as strings (e.g. 100 before 25).",
            evidence_snippet="return [...scores].sort();",
        ),
    ),
    # 22. Test Clean 1: Python clean FastAPI dependency
    EvalCase(
        id="test_22_py_clean_fastapi_dependency",
        split="test",
        language="python",
        category="clean",
        has_bug=False,
        pr_title="Add database session dependency generator",
        pr_description="Async generator yielding session with automatic closure.",
        filename="app/deps.py",
        diff_text="""diff --git a/app/deps.py b/app/deps.py
index 2000022..3000022 100644
--- a/app/deps.py
+++ b/app/deps.py
@@ -10,3 +10,9 @@ from collections.abc import AsyncIterator
+async def get_db() -> AsyncIterator[AsyncSession]:
+    async with async_session_factory() as session:
+        try:
+            yield session
+        finally:
+            await session.close()
""",
    ),
    # 23. Test Clean 2: Python clean dataclass
    EvalCase(
        id="test_23_py_clean_audit_dataclass",
        split="test",
        language="python",
        category="clean",
        has_bug=False,
        pr_title="Add AuditEvent data transfer record",
        pr_description="Immutable dataclass representing security audit logs.",
        filename="app/events.py",
        diff_text="""diff --git a/app/events.py b/app/events.py
index 2000023..3000023 100644
--- a/app/events.py
+++ b/app/events.py
@@ -4,3 +4,8 @@ from dataclasses import dataclass
+@dataclass(frozen=True)
+class AuditEvent:
+    user_id: int
+    action: str
+    resource_id: str
+    timestamp: str
""",
    ),
    # 24. Test Clean 3: Python clean custom HTTPException
    EvalCase(
        id="test_24_py_clean_custom_http_exception",
        split="test",
        language="python",
        category="clean",
        has_bug=False,
        pr_title="Add ResourceNotFound custom exception",
        pr_description="Standard 404 exception with structured error detail.",
        filename="app/exceptions.py",
        diff_text="""diff --git a/app/exceptions.py b/app/exceptions.py
index 2000024..3000024 100644
--- a/app/exceptions.py
+++ b/app/exceptions.py
@@ -6,3 +6,8 @@ from fastapi import HTTPException, status
+class ResourceNotFoundException(HTTPException):
+    def __init__(self, resource_type: str, resource_id: str):
+        super().__init__(
+            status_code=status.HTTP_404_NOT_FOUND,
+            detail=f"{resource_type} with id '{resource_id}' was not found.",
+        )
""",
    ),
    # 25. Test Clean 4: Python clean cache invalidation helper
    EvalCase(
        id="test_25_py_clean_cache_invalidation",
        split="test",
        language="python",
        category="clean",
        has_bug=False,
        pr_title="Add cache key invalidation utility",
        pr_description="Clean utility function to purge Redis cache by key pattern.",
        filename="app/cache_util.py",
        diff_text="""diff --git a/app/cache_util.py b/app/cache_util.py
index 2000025..3000025 100644
--- a/app/cache_util.py
+++ b/app/cache_util.py
@@ -8,3 +8,6 @@ from typing import Sequence
+async def invalidate_cache_keys(redis_client, keys: Sequence[str]) -> int:
+    if not keys:
+        return 0
+    return await redis_client.delete(*keys)
""",
    ),
    # 26. Test Clean 5: TS clean useDebounce hook
    EvalCase(
        id="test_26_ts_clean_debounce_hook",
        split="test",
        language="typescript",
        category="clean",
        has_bug=False,
        pr_title="Add useDebounce custom React hook",
        pr_description="Debounces value updates with proper useEffect timer cleanup.",
        filename="src/hooks/useDebounce.ts",
        diff_text="""diff --git a/src/hooks/useDebounce.ts b/src/hooks/useDebounce.ts
index 2000026..3000026 100644
--- a/src/hooks/useDebounce.ts
+++ b/src/hooks/useDebounce.ts
@@ -4,3 +4,11 @@ import { useState, useEffect } from "react";
+export function useDebounce<T>(value: T, delayMs: number): T {
+  const [debounced, setDebounced] = useState<T>(value);
+  useEffect(() => {
+    const timer = setTimeout(() => setDebounced(value), delayMs);
+    return () => clearTimeout(timer);
+  }, [value, delayMs]);
+  return debounced;
+}
""",
    ),
    # 27. Test Clean 6: TS clean Zustand state slice
    EvalCase(
        id="test_27_ts_clean_zustand_slice",
        split="test",
        language="typescript",
        category="clean",
        has_bug=False,
        pr_title="Add user state management slice",
        pr_description="Immutable state updates for user preferences.",
        filename="src/store/userSlice.ts",
        diff_text="""diff --git a/src/store/userSlice.ts b/src/store/userSlice.ts
index 2000027..3000027 100644
--- a/src/store/userSlice.ts
+++ b/src/store/userSlice.ts
@@ -6,3 +6,8 @@ export interface UserState { theme: "light" | "dark"; setTheme: (t: "light" | "
+export const createUserSlice = (set: any): UserState => ({
+  theme: "light",
+  setTheme: (theme) => set((state: any) => ({ ...state, theme })),
+});
""",
    ),
    # 28. Test Clean 7: TS clean Zod auth schema
    EvalCase(
        id="test_28_ts_clean_zod_schema",
        split="test",
        language="typescript",
        category="clean",
        has_bug=False,
        pr_title="Add Zod schema for signup form validation",
        pr_description="Validates signup inputs with length and email constraints.",
        filename="src/schemas/auth.ts",
        diff_text="""diff --git a/src/schemas/auth.ts b/src/schemas/auth.ts
index 2000028..3000028 100644
--- a/src/schemas/auth.ts
+++ b/src/schemas/auth.ts
@@ -2,3 +2,7 @@ import { z } from "zod";
+export const SignupSchema = z.object({
+  username: z.string().min(3).max(30),
+  email: z.string().email(),
+  password: z.string().min(8),
+});
""",
    ),
    # 29. Test Clean 8: TS clean currency formatter
    EvalCase(
        id="test_29_ts_clean_intl_currency",
        split="test",
        language="typescript",
        category="clean",
        has_bug=False,
        pr_title="Add currency formatting helper",
        pr_description="Formats amounts using Intl.NumberFormat.",
        filename="src/utils/format.ts",
        diff_text="""diff --git a/src/utils/format.ts b/src/utils/format.ts
index 2000029..3000029 100644
--- a/src/utils/format.ts
+++ b/src/utils/format.ts
@@ -4,3 +4,7 @@ export const DEFAULT_LOCALE = "en-US";
+export function formatUSD(amountCents: number): string {
+  return new Intl.NumberFormat("en-US", {
+    style: "currency",
+    currency: "USD",
+  }).format(amountCents / 100);
+}
""",
    ),
    # 30. Test Clean 9: Python clean JSON logger formatter
    EvalCase(
        id="test_30_py_clean_json_logger",
        split="test",
        language="python",
        category="clean",
        has_bug=False,
        pr_title="Add structured JSON log formatter",
        pr_description="Formats log records as single-line JSON objects.",
        filename="app/logging_formatter.py",
        diff_text="""diff --git a/app/logging_formatter.py b/app/logging_formatter.py
index 2000030..3000030 100644
--- a/app/logging_formatter.py
+++ b/app/logging_formatter.py
@@ -6,3 +6,9 @@ import json, logging
+class JsonLogFormatter(logging.Formatter):
+    def format(self, record: logging.LogRecord) -> str:
+        data = {
+            "level": record.levelname,
+            "message": record.getMessage(),
+            "logger": record.name,
+        }
+        return json.dumps(data)
""",
    ),
]
