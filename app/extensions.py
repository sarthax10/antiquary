"""Shared Flask extension instances (auth/security only — DB access goes through
db.py's plain SQLAlchemy session; see that module's docstring for why this app doesn't
use Flask-SQLAlchemy).
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_wtf import CSRFProtect

login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
