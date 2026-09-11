"""Business logic for connected third-party accounts (SocialAccount): lookup, upsert on
(re)connect, disconnect, and handing out a currently-valid (decrypted, refreshed if
needed) access token to app/publishing/manager.py. Token values passed into this module
are plaintext, encrypted before they touch the database (see app/crypto.py)."""
from datetime import datetime, timedelta

from app import crypto
from app.db import get_session
from app.models import SocialAccount, utcnow

from . import youtube

# Refresh proactively rather than waiting for an actual 401 from the platform — a
# publish job is a multi-minute operation (upload time included), so a token that's
# merely close to expiring is treated the same as one that already has.
_REFRESH_BUFFER = timedelta(minutes=5)


def get_accounts_for_user(user_id: int) -> list[SocialAccount]:
    return get_session().query(SocialAccount).filter_by(user_id=user_id).order_by(SocialAccount.platform).all()


def get_account(user_id: int, platform: str) -> SocialAccount | None:
    return get_session().query(SocialAccount).filter_by(user_id=user_id, platform=platform).one_or_none()


def save_account(
    user_id: int,
    platform: str,
    external_account_id: str,
    external_account_name: str,
    access_token: str,
    refresh_token: str | None,
    token_expires_at: datetime | None,
    scopes: str,
) -> SocialAccount:
    """Upsert on (user_id, platform) — reconnecting the same platform replaces the
    existing row (fresh tokens, possibly a different external account) rather than
    erroring on the unique constraint or leaving stale tokens in place."""
    session = get_session()
    account = get_account(user_id, platform)
    if account is None:
        account = SocialAccount(user_id=user_id, platform=platform)
        session.add(account)

    account.external_account_id = external_account_id
    account.external_account_name = external_account_name
    account.access_token = crypto.encrypt(access_token)
    account.refresh_token = crypto.encrypt(refresh_token) if refresh_token else None
    account.token_expires_at = token_expires_at
    account.scopes = scopes
    session.commit()
    return account


def get_valid_access_token(account: SocialAccount) -> str:
    """Returns a decrypted access token guaranteed not to be near-expired, refreshing
    and persisting a new one first if needed. Only YouTube is implemented — Instagram's
    connect flow doesn't exist yet (see app/social/routes.py)."""
    needs_refresh = account.token_expires_at is None or account.token_expires_at <= utcnow() + _REFRESH_BUFFER
    if not needs_refresh:
        return crypto.decrypt(account.access_token)

    if account.platform != "youtube":
        raise NotImplementedError(f"Token refresh not implemented for platform {account.platform!r}.")
    if not account.refresh_token:
        raise ValueError("This account has no refresh token on file — reconnect it.")

    token_data = youtube.refresh_access_token(crypto.decrypt(account.refresh_token))
    new_access_token = token_data["access_token"]

    session = get_session()
    account.access_token = crypto.encrypt(new_access_token)
    account.token_expires_at = youtube.expires_at_from(token_data)
    session.commit()
    return new_access_token


def delete_account(user_id: int, account_id: int) -> bool:
    session = get_session()
    account = session.query(SocialAccount).filter_by(id=account_id, user_id=user_id).one_or_none()
    if account is None:
        return False
    session.delete(account)
    session.commit()
    return True
