import os

# Set before app modules import, so logging is configured quietly for tests.
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-in-production")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.core.database import Base, get_db
import app.models  # noqa: F401  register tables
from app.main import app


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session):
    def override():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def auth(client):
    r = client.post("/auth/register", json={"email": "t@express.os", "password": "secret123", "name": "Pooji"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ─── Gemini ────────────────────────────────────────────────────────────────
# JOCasta's LLM provider is mocked everywhere. No test reaches the network, and
# none needs a real GEMINI_API_KEY. The patch is applied to `genai.Client`
# itself rather than to our own wrapper, so `llm.py` and `brain.py` both run for
# real — a test that stubbed our code would prove only that the stub works.
class _FakeReason:
    def __init__(self, name): self.name = name


class _FakeCandidate:
    def __init__(self, reason): self.finish_reason = _FakeReason(reason)


class FakeGeminiResponse:
    def __init__(self, text="", function_calls=None, finish_reason="STOP"):
        self.text = text
        self.function_calls = function_calls or []
        self.candidates = [_FakeCandidate(finish_reason)]


class FakeFunctionCall:
    def __init__(self, name, args=None):
        self.name, self.args = name, args or {}


@pytest.fixture()
def gemini(monkeypatch):
    """Stand a fake Gemini up. Returns a factory; call it to configure the turn.

        sent = gemini("Hey — I'm good.")          # a normal reply
        gemini(error=RuntimeError("no network"))  # a failure
        gemini(finish_reason="SAFETY")            # a refusal
        gemini(calls=[FakeFunctionCall("get_tasks")])

    The returned list collects every request that reached the SDK, so a test can
    assert on what the model was actually given.
    """
    from app.core.config import settings

    def configure(text="A natural reply.", calls=None, finish_reason="STOP",
                  error=None, key="test-key"):
        from google import genai
        sent = []

        class Models:
            def generate_content(self, **kw):
                sent.append(kw)
                if error is not None:
                    raise error
                return FakeGeminiResponse(text, calls, finish_reason)

        class Client:
            def __init__(self, **kw): self.models = Models()

        monkeypatch.setattr(settings, "GEMINI_API_KEY", key)
        monkeypatch.setattr(genai, "Client", Client)
        return sent

    return configure


@pytest.fixture(autouse=True)
def _clean_llm_state(monkeypatch):
    """Provider health and the cached client are module state; keep them from
    leaking between tests, and make sure a test that swaps the SDK doesn't get
    a client built by an earlier one."""
    from app.jocasta import llm
    monkeypatch.setattr(llm, "_last_error", None)
    monkeypatch.setattr(llm, "_last_ok", False)
    llm.reset_client()
    yield
    llm.reset_client()
