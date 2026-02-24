# Security Fixes Report

**Date:** 2026-02-07
**Author:** Security Audit (Automated)
**Scope:** SQL Injection vulnerabilities and hardcoded secrets

---

## 1. SQL Injection Vulnerabilities Found and Fixed

### 1.1 CRITICAL: `api/init_db.py` lines 110-133 (FIXED)

**Risk Level:** HIGH
**Risk Type:** SQL Injection in DDL operations

**Vulnerable Code (BEFORE):**
```python
# Line 110-113: String interpolation in WHERE clause
result = conn.execute(text(f"""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = '{table}' AND column_name = '{column}'
"""))

# Line 116: Unvalidated identifiers in DDL
conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))

# Lines 126-129: Same pattern for alterations
result = conn.execute(text(f"""
    SELECT data_type FROM information_schema.columns
    WHERE table_name = '{table}' AND column_name = '{column}'
"""))

# Line 133: Unvalidated ALTER TABLE
conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {new_type}"))
```

**Problem:** Table names, column names, and column types were interpolated into SQL without any validation. Although the values come from a hardcoded list in the same file (not from user input), this pattern is dangerous because:
- Future developers might add user-controlled values to the migrations list
- It violates defense-in-depth principles
- Any code injection into the module could exploit these queries

**Fix Applied:**
1. Added three strict whitelists: `ALLOWED_MIGRATION_TABLES`, `ALLOWED_MIGRATION_COLUMNS`, `ALLOWED_COLUMN_TYPES`
2. Added validation functions: `_validate_migration_table()`, `_validate_migration_column()`, `_validate_migration_col_type()`
3. Changed information_schema queries to use parameterized `:table` and `:column` bind parameters
4. Added double-quote identifier quoting for DDL statements: `ALTER TABLE "{table}" ADD COLUMN "{column}"`

---

### 1.2 MEDIUM: `core/embeddings.py` lines 186-191 (FIXED)

**Risk Level:** MEDIUM
**Risk Type:** SQL Injection via vector string interpolation

**Vulnerable Code (BEFORE):**
```python
embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
db.execute(text(f"""
    INSERT INTO content_embeddings (chunk_id, creator_id, content_preview, embedding)
    VALUES (:chunk_id, :creator_id, :content_preview, '{embedding_str}'::vector)
    ON CONFLICT (chunk_id) DO UPDATE SET
        embedding = '{embedding_str}'::vector,
        updated_at = NOW()
"""), {...})
```

**Problem:** The `embedding_str` was built from a `List[float]` parameter and directly interpolated into SQL with single quotes. If a caller passed crafted non-float values in the embedding list (e.g., strings containing SQL), they could break out of the string context. The comment in the code incorrectly stated that psycopg2 could not handle `::vector` cast with parameters.

**Fix Applied:**
1. Added explicit `float()` validation for every value in the embedding list before string conversion
2. Changed from f-string interpolation to parameterized query: `:embedding::vector`
3. The `embedding_str` is now passed as a bind parameter

**Note:** The `search_similar()` function (line 244) was already correctly parameterized using `:query::vector`.

---

### 1.3 LOW: `api/routers/admin/dangerous.py` line 264 (HARDENED)

**Risk Level:** LOW (already had whitelist validation)
**Risk Type:** SQL Injection in DELETE statement

**Code (BEFORE):**
```python
validate_table_name(table)  # Line 263 - already validates
result = session.execute(text(f"DELETE FROM {table}"))  # Line 264
```

**Fix Applied:** Added double-quote identifier quoting as defense in depth:
```python
result = session.execute(text(f'DELETE FROM "{table}"'))
```

The `validate_table_name()` function in `api/routers/admin/shared.py` already validated against a strict `ALLOWED_TABLES` frozenset, and the table list is hardcoded. The identifier quoting adds an additional layer of protection.

---

### 1.4 LOW: `api/routers/admin/dangerous.py` lines 1032-1037 (HARDENED)

**Risk Level:** LOW (already had whitelist validation)
**Risk Type:** SQL Injection in DELETE with FK subquery

**Code (BEFORE):**
```python
validate_table_name(table)   # Line 1026
validate_fk_column(fk_col)   # Line 1027
sql = text(f"DELETE FROM {table} WHERE {fk_col} IN ...")
sql = text(f"DELETE FROM {table} WHERE {fk_col} = :creator_id")
```

**Fix Applied:** Added double-quote identifier quoting:
```python
sql = text(f'DELETE FROM "{table}" WHERE "{fk_col}" IN ...')
sql = text(f'DELETE FROM "{table}" WHERE "{fk_col}" = :creator_id')
```

---

### 1.5 LOW: `scripts/backup_db.py` line 81 (HARDENED)

**Risk Level:** LOW (already had whitelist validation)
**Risk Type:** SQL Injection in SELECT statement

**Code (BEFORE):**
```python
_validate_table_name(table_name)  # Line 79 - already validates
query = f"SELECT * FROM {table_name}"  # Line 81
```

**Fix Applied:** Added double-quote identifier quoting:
```python
query = f'SELECT * FROM "{table_name}"'
```

---

## 2. Hardcoded Secrets and API Keys (DOCUMENTED - Not Modified)

These items need future refactoring to remove hardcoded values. They were NOT modified in this security fix pass.

### 2.1 Hardcoded Admin Key Fallbacks

| File | Line | Finding |
|------|------|---------|
| `scripts/api_test_suite.py` | 18 | `ADMIN_KEY = os.getenv("CLONNECT_ADMIN_KEY", "clonnect_admin_secret_2024")` |
| `scripts/generate_visual_report.py` | 17 | `ADMIN_KEY = os.getenv("CLONNECT_ADMIN_KEY", "clonnect_admin_secret_2024")` |
| `scripts/e2e_full_scenario_test.py` | 25 | `ADMIN_KEY = os.getenv("CLONNECT_ADMIN_KEY", "clonnect_admin_secret_2024")` |

**Risk:** The fallback value `"clonnect_admin_secret_2024"` exposes the admin key if the environment variable is not set. An attacker who knows this default could access admin endpoints.

**Recommendation:** Remove fallback values. Scripts should fail explicitly if env var is missing:
```python
ADMIN_KEY = os.environ["CLONNECT_ADMIN_KEY"]  # Fail fast if missing
```

### 2.2 Hardcoded Webhook Verify Tokens

| File | Line | Finding |
|------|------|---------|
| `api/config.py` | 30 | `INSTAGRAM_VERIFY_TOKEN: str = os.getenv("INSTAGRAM_VERIFY_TOKEN", "clonnect_verify_2024")` |
| `core/instagram.py` | 93 | `os.getenv("INSTAGRAM_VERIFY_TOKEN", "clonnect_verify_2024")` |
| `core/instagram_handler.py` | 76 | `os.getenv("INSTAGRAM_VERIFY_TOKEN", "clonnect_verify_2024")` |
| `api/routers/instagram.py` | 245 | `VERIFY_TOKEN = os.getenv("INSTAGRAM_VERIFY_TOKEN", "clonnect_verify_2024")` |
| `core/whatsapp.py` | 103 | `os.getenv("WHATSAPP_VERIFY_TOKEN", "clonnect_wa_verify_2024")` |
| `core/whatsapp.py` | 464 | `os.getenv("WHATSAPP_VERIFY_TOKEN", "clonnect_wa_verify_2024")` |
| `api/routers/messaging_webhooks.py` | 208 | `os.getenv("WHATSAPP_VERIFY_TOKEN", "clonnect_whatsapp_verify_2024")` |

**Risk:** Verify tokens with known default values. If env vars are not set, the default token is publicly known.

**Recommendation:** Remove fallback values and require env vars in production.

### 2.3 Hardcoded API Keys for Default Creators

| File | Line | Finding |
|------|------|---------|
| `api/init_db.py` | 203 | `api_key="clonnect_manel_key"` |
| `api/init_db.py` | 219 | `api_key="clonnect_stefano_key"` |

**Risk:** Default creator API keys are hardcoded in the database seed function.

**Recommendation:** Generate random API keys at creation time:
```python
import secrets
api_key = f"clk_{secrets.token_urlsafe(32)}"
```

### 2.4 Hardcoded Demo Password

| File | Line | Finding |
|------|------|---------|
| `api/init_db.py` | 254 | `password = "demo2024"` |

**Risk:** Demo user password is hardcoded. While it is bcrypt-hashed before storage, the plaintext is visible in source code.

**Recommendation:** Use environment variable or generate random password and log it once.

### 2.5 Empty String Fallbacks for Secrets

| File | Line | Finding |
|------|------|---------|
| `api/auth.py` | 38 | `JWT_SECRET = os.getenv("JWT_SECRET", "")` |
| `core/token_refresh_service.py` | 22 | `META_APP_SECRET = os.getenv("META_APP_SECRET", "")` |
| `core/payments.py` | 107 | `self.stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")` |
| `core/payments.py` | 111 | `self.paypal_client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "")` |

**Risk:** Empty string fallbacks mean the application starts without proper secrets, potentially allowing bypass of signature verification if the code does not explicitly check for empty values.

**Recommendation:** Validate that critical secrets are non-empty at startup.

### 2.6 Hardcoded Creator UUIDs

| File | Line | Finding |
|------|------|---------|
| `models/creator_dm_style.py` | 79 | `creator_id="5e5c2364-c99a-4484-b986-741bb84a11cf"` |
| `models/writing_patterns.py` | 70, 182 | Same UUID as Stefan's creator ID |
| `services/creator_dm_style_service.py` | 22 | Same UUID in service mapping |
| `services/creator_style_loader.py` | 130 | Same UUID in style loader |
| `scripts/restore_messages_from_json.py` | 26 | Same UUID as constant |

**Risk:** Low. These are configuration mappings for a specific creator. However, hardcoding UUIDs makes the code less portable.

**Recommendation:** Move creator-specific configurations to database or config files.

### 2.7 Test-Only Secrets

| File | Line | Finding |
|------|------|---------|
| `tests/contracts/test_meta_webhook_contract.py` | 25 | `"hub_verify_token": "clonnect_verify_token_123"` |
| `tests/conftest.py` | 16 | `os.environ["META_APP_SECRET"] = "test-secret"` |
| `tests/conftest.py` | 269 | `secret: str = "test-secret"` |

**Risk:** None in production. These are test fixtures.

---

## 3. Summary

### Fixes Applied

| # | File | Severity | Status |
|---|------|----------|--------|
| 1 | `api/init_db.py` | HIGH | FIXED - Added whitelists + parameterized queries + identifier quoting |
| 2 | `core/embeddings.py` | MEDIUM | FIXED - Parameterized vector + float validation |
| 3 | `api/routers/admin/dangerous.py:264` | LOW | HARDENED - Added identifier quoting |
| 4 | `api/routers/admin/dangerous.py:1032-1037` | LOW | HARDENED - Added identifier quoting |
| 5 | `scripts/backup_db.py:81` | LOW | HARDENED - Added identifier quoting |

### Items Requiring Future Work

| Priority | Item | Risk |
|----------|------|------|
| P1 | Remove admin key fallback `"clonnect_admin_secret_2024"` from 3 scripts | HIGH - Known admin key |
| P1 | Remove verify token fallbacks from 7 locations | MEDIUM - Known webhook tokens |
| P2 | Generate random API keys for default creators | MEDIUM - Known API keys |
| P2 | Validate JWT_SECRET is non-empty at startup | MEDIUM - Auth bypass risk |
| P3 | Remove hardcoded demo password | LOW - Only for demo user |
| P3 | Move hardcoded UUIDs to configuration | LOW - Code maintainability |

### Verification

After applying fixes, automated searches confirmed:
- **0** unvalidated f-string SQL interpolations remain
- All remaining f-string SQL patterns use whitelist-validated + quoted identifiers
- All information_schema queries now use parameterized bind variables
- The embedding vector injection path is fully parameterized
