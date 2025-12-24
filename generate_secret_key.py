#!/usr/bin/env python
"""Generate a secure secret key for JWT tokens and session management."""
import secrets

# Generate a secure random key
secret_key = secrets.token_urlsafe(32)

print("=" * 60)
print("Generated SECRET_KEY (use this as JWT_SECRET_KEY in Railway/Render):")
print("=" * 60)
print(secret_key)
print("=" * 60)
print("\nCopy the key above and use it as:")
print("- JWT_SECRET_KEY in Railway (API service)")
print("- JWT_SECRET_KEY in Render (when migrating)")
print("\nNote: If you generate a new key, existing user sessions will be invalidated.")

