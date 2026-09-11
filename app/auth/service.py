"""Auth business logic: password hashing, user lookup/creation, authentication.
Called by both the API routes and app/cli.py's seed-admin command — kept here once
rather than duplicated in each."""
import re

from werkzeug.security import check_password_hash, generate_password_hash

from app.db import get_session
from app.models import User

MIN_PASSWORD_LENGTH = 10
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# A fixed, valid scrypt hash checked when the email doesn't exist, purely so
# check_password_hash() always runs and takes roughly the same time whether or not the
# account is real — without this, "no such user" short-circuits before hashing while a
# real-user-wrong-password case does the full hash comparison, and that time difference
# is a classic (if narrow) side channel for enumerating valid emails.
_DUMMY_HASH = generate_password_hash("not-a-real-password-just-for-timing")


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email or ""))


def password_error(password: str) -> str | None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    return None


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def get_user_by_email(email: str) -> User | None:
    return get_session().query(User).filter_by(email=normalize_email(email)).one_or_none()


def get_user_by_id(user_id: int) -> User | None:
    return get_session().get(User, user_id)


def create_signup_request(email: str, password: str, role: str = "user", status: str = "pending") -> User:
    session = get_session()
    user = User(
        email=normalize_email(email),
        password_hash=generate_password_hash(password),
        role=role,
        status=status,
    )
    session.add(user)
    session.commit()
    return user


def change_password(user: User, current_password: str, new_password: str) -> str | None:
    """Self-service password change. Returns an error message, or None on success."""
    if not check_password_hash(user.password_hash, current_password):
        return "Current password is incorrect."
    pw_error = password_error(new_password)
    if pw_error:
        return pw_error
    user.password_hash = generate_password_hash(new_password)
    get_session().commit()
    return None


def set_password(user: User, new_password: str) -> str | None:
    """Admin-initiated reset — no current-password check, used from app/admin/service.py.
    Returns an error message, or None on success."""
    pw_error = password_error(new_password)
    if pw_error:
        return pw_error
    user.password_hash = generate_password_hash(new_password)
    get_session().commit()
    return None


def authenticate(email: str, password: str) -> tuple[User | None, str | None]:
    """Returns (user, error_message) — error_message is None on success.

    Password is checked before status is inspected, so a wrong password always
    produces the same generic message regardless of account state (an attacker without
    valid credentials learns nothing about whether the account is pending/rejected).
    Also always calls check_password_hash exactly once regardless of whether the user
    exists (see _DUMMY_HASH) — otherwise a nonexistent email returns near-instantly
    while a real-user-wrong-password case pays the full hash cost, and that timing gap
    is itself an account-enumeration side channel independent of the response body."""
    user = get_user_by_email(email)
    password_ok = check_password_hash(user.password_hash if user else _DUMMY_HASH, password)
    if user is None or not password_ok:
        return None, "Invalid email or password."
    if user.status == "pending":
        return None, "Your account is awaiting admin approval."
    if user.status == "rejected":
        return None, "Your access request was not approved."
    if user.status == "suspended":
        return None, "Your account has been suspended."
    return user, None
