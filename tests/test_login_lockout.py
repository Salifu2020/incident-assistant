"""Six wrong passwords lock the next try. The same failure is returned either way."""
import os
import tempfile
from datetime import datetime, timedelta

import src.auth as auth
from src.auth import MAX_FAILED_ATTEMPTS, UserManager


def _use_temp_store():
    folder = tempfile.mkdtemp(prefix="lockout-")
    auth.USERS_FILE = os.path.join(folder, "users.json")
    auth.PASSWORD_HISTORY_FILE = os.path.join(folder, "password_history.json")
    auth.ensure_data_dir()


def test_six_wrong_passwords_block_the_next_try_until_the_window_ends():
    _use_temp_store()
    email = "lockout.check@example.com"
    password = "Correct-Lock-1!"
    UserManager.create_user(email=email, password=password, role="user", first_name="Lock")

    for _ in range(MAX_FAILED_ATTEMPTS - 1):
        result = UserManager.authenticate_user(email, "Wrong-Lock-1!")
        assert result == {"error": "invalid_credentials"}

    stored = next(user for user in auth.load_users()["users"] if user["email"] == email)
    assert stored["failed_attempts"] == MAX_FAILED_ATTEMPTS - 1
    assert not stored.get("locked_until")

    sixth = UserManager.authenticate_user(email, "Wrong-Lock-1!")
    assert sixth == {"error": "invalid_credentials"}
    stored = next(user for user in auth.load_users()["users"] if user["email"] == email)
    assert stored["failed_attempts"] == MAX_FAILED_ATTEMPTS
    assert stored.get("locked_until")

    blocked = UserManager.authenticate_user(email, password)
    assert blocked == {"error": "invalid_credentials"}
    still = next(user for user in auth.load_users()["users"] if user["email"] == email)
    assert still.get("locked_until")

    still["locked_until"] = (datetime.now() - timedelta(minutes=1)).isoformat()
    auth.save_users({"users": [still]})

    allowed = UserManager.authenticate_user(email, password)
    assert allowed and "error" not in allowed
    cleared = next(user for user in auth.load_users()["users"] if user["email"] == email)
    assert cleared["failed_attempts"] == 0
    assert not cleared.get("locked_until")

    missing = UserManager.authenticate_user("nobody@example.com", password)
    assert missing is None
    assert len(auth.load_users()["users"]) == 1
