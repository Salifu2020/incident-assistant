# Security Review — Incident Assistant

A security assessment of the Incident Assistant project. Review date: 2025-03-14.

---

## Executive Summary

This review identifies several vulnerabilities across authentication, input validation, and data handling. **Critical issues** should be fixed before production deployment. **High** and **Medium** issues should be addressed as part of regular security hardening.

---

## Critical Issues

### 1. Password Reset Token Exposed in Development Mode

**Location:** `src/api.py` — `/auth/password-reset/request`

**Issue:** When email service is not configured, the API returns the password reset token in the JSON response. An attacker can request a reset for any email address and obtain the token without access to the victim's inbox.

```python
if not EmailService or not EmailService.is_configured():
    return {"message": "...", "token": token}  # Token exposed!
```

**Fix:** Never return the token in the API response. Log it for development only, or require email configuration for production.

---

### 2. Zip Slip in Backup Restore

**Location:** `src/api.py` — `/backup/restore`

**Issue:** Extracting files from a zip backup does not validate that extracted paths stay within the project directory. A malicious zip (or compromised backup) with entries like `data/../../../etc/passwd` could overwrite arbitrary files on the server.

**Fix:** Normalize each path and verify it is under `PROJECT_ROOT` before extracting.

---

### 3. Path Traversal in Document Filename

**Location:** `src/ingestion.py` — `delete_document()`, `get_document_info()`

**Issue:** The `filename` parameter from API paths (e.g. `/documents/{filename}`) is used in `os.path.join()` without validation. A filename like `../../../etc/passwd` or `..\\..\\..\\windows\\system32\\config\\sam` could escape intended directories, leading to deletion or exposure of unintended files.

**Fix:** Reject filenames containing `..`, path separators, or that resolve outside allowed directories.

---

### 4. Password Logged to Console/Files

**Location:** `src/auth.py` — `hash_password()`

**Issue:** Up to 20 characters of the password are logged:  
`logger.info(f"Calling pwd_context.hash() with password: '{password_for_bcrypt[:20]}...'")`  
Logs may be stored in files, sent to external services, or visible to operators.

**Fix:** Remove all password logging. Log only non-sensitive metadata (e.g. "Password hash attempted") if needed for debugging.

---

### 5. Unauthenticated Document Endpoints

**Location:** `src/api.py`

**Issue:** The following endpoints do not require authentication:
- `GET /documents` — Lists all documents
- `GET /documents/{filename}` — Returns document metadata
- `GET /status` — Returns knowledge base status and document list

Anyone can enumerate documents and metadata without logging in.

**Fix:** Add `Depends(get_current_user)` (or equivalent) to these endpoints, or document that they are intentionally public.

---

## High Issues

### 6. Default Admin Credentials Hardcoded

**Location:** `src/auth.py`, `src/db_auth.py`, `src/api.py`

**Issue:** Default admin user is created with `username: admin`, `password: REDACTED`. If not changed after first login, this acts as a persistent backdoor. The password appears in logs and UI hints.

**Fix:** Force password change on first login, remove credentials from logs/UI, and recommend changing defaults in deployment docs.

---

### 7. JWT Secret Key Fallback

**Location:** `src/auth.py`

**Issue:** `SECRET_KEY = os.environ.get("JWT_SECRET_KEY", secrets.token_urlsafe(32))`  
If `JWT_SECRET_KEY` is not set, a new key is generated on each restart, invalidating all existing tokens. This can lock users out and is confusing operationally. There is no warning when the fallback is used.

**Fix:** Require `JWT_SECRET_KEY` in production; fail startup or log a clear warning if it is missing.

---

### 8. Permissive CORS Configuration

**Location:** `src/api.py`

**Issue:** `allow_origins=["*"]` allows any origin to call the API. With cookie-based or mixed auth models, this increases CSRF risk. For Bearer-token-only APIs the impact is lower but still not ideal.

**Fix:** Restrict `allow_origins` to known frontend origins in production.

---

## Medium Issues

### 9. SQL Metadata Key Injection (pgvector)

**Location:** `src/vector_stores.py` — `PgVectorStore.query()`, `delete()`

**Issue:** The `where` clause builds SQL with `metadata->>'{key}'` where `key` comes from the caller. A malicious or buggy caller could supply a key that alters the query (e.g. `"source'; DROP TABLE documents; --"`).

**Fix:** Validate/whitelist metadata keys (e.g. alphanumeric, known keys only) before interpolating into SQL.

---

### 10. Avatar Upload Path

**Location:** `src/api.py` — `/auth/avatar`

**Issue:** Avatar filename is `{current_user.id}{ext}`. The `ext` comes from the uploaded file. If an attacker uploads a file with extension `.php` or similar, the saved file could be executed in some server configurations. Risk depends on server and static file handling.

**Fix:** Restrict allowed extensions to a fixed list (e.g. `.jpg`, `.png`, `.gif`, `.webp`) and ignore or replace any other extension.

---

### 11. Sensitive Data in Error Messages

**Location:** Multiple API handlers

**Issue:** Some endpoints return raw exception messages or internal details (e.g. `detail=str(e)`) to clients, which can leak implementation or path information.

**Fix:** Return generic error messages to clients; log detailed errors server-side only.

---

## Low Issues / Recommendations

- **Rate limiting:** Add rate limiting for auth endpoints (login, password reset) to reduce brute-force and token abuse.
- **Audit logging:** Ensure audit logs do not contain passwords or tokens.
- **File size limits:** Document and enforce limits for uploads and backups.
- **HTTPS:** Enforce HTTPS in production and document HTTP redirect behavior.
- **Dependency scanning:** Run `pip audit` or similar to detect known vulnerabilities in dependencies.

---

## Summary Table

| # | Severity | Issue | Status |
|---|----------|-------|--------|
| 1 | Critical | Password reset token exposed | Fixed (no longer returned) |
| 2 | Critical | Zip Slip in backup restore | Fixed (path validation) |
| 3 | Critical | Path traversal in document filename | Fixed (_safe_document_filename) |
| 4 | Critical | Password logged | Fixed (removed from logs) |
| 5 | Critical | Unauthenticated document endpoints | Fixed (auth required) |
| 6 | High | Hardcoded default admin credentials | Mitigate |
| 7 | High | JWT secret key fallback | Mitigate |
| 8 | High | Permissive CORS | Mitigate |
| 9 | Medium | SQL key injection (pgvector) | Fix recommended |
| 10 | Medium | Avatar upload extension | Fixed (whitelist .jpg, .png, etc.) |
| 11 | Medium | Sensitive data in errors | Mitigate |

---

*This document should be updated as fixes are applied or new security concerns emerge.*
