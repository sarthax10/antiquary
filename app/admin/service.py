from app.auth import service as auth_service
from app.db import get_session
from app.models import User, utcnow


def list_users(status: str | None = None) -> list[User]:
    session = get_session()
    query = session.query(User).order_by(User.created_at.desc())
    if status:
        query = query.filter_by(status=status)
    return query.all()


def set_user_status(user_id: int, status: str, approved_by: User) -> User | None:
    session = get_session()
    user = session.get(User, user_id)
    if user is None:
        return None
    user.status = status
    if status == "approved":
        user.approved_at = utcnow()
        user.approved_by_id = approved_by.id
    session.commit()
    return user


def set_user_role(user_id: int, role: str) -> User | None:
    session = get_session()
    user = session.get(User, user_id)
    if user is None:
        return None
    user.role = role
    session.commit()
    return user


def reset_password(user_id: int, new_password: str) -> tuple[User | None, str | None]:
    """Returns (user, error) — error is None on success. Used when a member has lost
    access and can't use the (also new) self-service change-password flow."""
    user = get_session().get(User, user_id)
    if user is None:
        return None, "not found"
    error = auth_service.set_password(user, new_password)
    return (None, error) if error else (user, None)
