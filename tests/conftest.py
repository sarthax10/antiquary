"""Runs against the real DATABASE_URL (same DB the app itself uses in dev) — this
project has no separate test-DB infra, matching the "real stack, no mocks" verification
approach used everywhere else in this project (see CLAUDE.md). Each fixture creates its
own rows (distinguishable by a test-run-scoped random suffix in emails/topics) and
deletes them again in teardown, rather than relying on transaction rollback — the app's
service functions call session.commit() directly, so a wrapping transaction wouldn't
isolate anything anyway.
"""
import uuid

import pytest
from werkzeug.security import generate_password_hash

from app.db import get_session, remove_session
from app.models import GenerationJob, Story, User


@pytest.fixture(autouse=True)
def _clean_session():
    yield
    get_session().rollback()
    remove_session()


@pytest.fixture
def make_user():
    created = []

    def _make(role="user", status="approved"):
        session = get_session()
        user = User(
            email=f"test-{uuid.uuid4().hex[:10]}@example.test",
            password_hash=generate_password_hash("not-a-real-password"),
            role=role,
            status=status,
        )
        session.add(user)
        session.commit()
        created.append(user.id)
        return user

    yield _make

    session = get_session()
    session.query(Story).filter(Story.created_by_id.in_(created)).delete(synchronize_session=False)
    session.query(GenerationJob).filter(GenerationJob.user_id.in_(created)).delete(synchronize_session=False)
    session.query(User).filter(User.id.in_(created)).delete(synchronize_session=False)
    session.commit()


@pytest.fixture
def make_story():
    created = []

    def _make(owner: User, status="pending"):
        session = get_session()
        story = Story(
            title=f"Test story {uuid.uuid4().hex[:6]}",
            narration="Test narration.",
            status=status,
            created_by_id=owner.id,
        )
        session.add(story)
        session.commit()
        created.append(story.id)
        return story

    yield _make

    session = get_session()
    session.query(Story).filter(Story.id.in_(created)).delete(synchronize_session=False)
    session.commit()


@pytest.fixture
def make_job():
    created = []

    def _make(owner: User, status="running"):
        session = get_session()
        job = GenerationJob(user_id=owner.id, topic=f"test-{uuid.uuid4().hex[:6]}", status=status, pid=999999)
        session.add(job)
        session.commit()
        created.append(job.id)
        return job

    yield _make

    session = get_session()
    session.query(GenerationJob).filter(GenerationJob.id.in_(created)).delete(synchronize_session=False)
    session.commit()
