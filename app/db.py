"""Plain SQLAlchemy engine/session — deliberately NOT Flask-SQLAlchemy.

This project's DB access happens from three execution contexts that don't share
memory: Flask request handlers, a background watcher thread inside the Flask process
(app/generation/job_manager.py), and a completely separate OS subprocess
(pipeline/run_pipeline.py). Flask-SQLAlchemy's session is bound to Flask's app/request
context, which the latter two don't have — juggling "push an app context here, don't
there" across those three cases is exactly the kind of subtle-bug surface this project
doesn't need. A plain SQLAlchemy scoped_session works identically in all three and
needs zero Flask-specific wiring.

Flask still gets clean per-request session lifecycle via app/__init__.py's
teardown_appcontext calling remove_session().
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True, future=True)
    return _engine


def get_session():
    """Returns the current scoped session (same object within one thread/greenlet)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = scoped_session(sessionmaker(bind=get_engine(), future=True))
    return _session_factory()


def remove_session() -> None:
    """Call at the end of a unit of work (Flask's teardown_appcontext, or the end of a
    standalone script) to return the connection to the pool. Safe to call even if
    get_session() was never invoked in this thread — scoped_session.remove() is a no-op
    in that case."""
    if _session_factory is not None:
        _session_factory.remove()
