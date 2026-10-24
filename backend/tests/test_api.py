import uuid

from fastapi.testclient import TestClient

from app.auth.models import User
from app.auth.security import current_user, password_hash
from app.core.db import get_db
from app.main import app


def demo_user(role: str) -> User:
    return User(id=uuid.uuid4(), email=f"{role}@local.example", role=role,
                password_hash="unused", is_active=True)


def test_health_and_not_ready():
    class OfflineDB:
        def execute(self, _query):
            raise ConnectionError("private database details")

    app.dependency_overrides[get_db] = lambda: OfflineDB()
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/health").json() == {"status": "ok"}
            response = client.get("/api/v1/ready")
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "NOT_READY"
            assert "private" not in response.text
            assert response.headers["X-Request-ID"] == response.json()["request_id"]
    finally:
        app.dependency_overrides.clear()


def test_role_boundary_and_validation():
    app.dependency_overrides[current_user] = lambda: demo_user("viewer")
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/auth/me").status_code == 200
            forbidden = client.get("/api/v1/auth/admin-check")
            assert forbidden.status_code == 403
            assert forbidden.json()["error"]["code"] == "FORBIDDEN"
    finally:
        app.dependency_overrides.clear()

    app.dependency_overrides[current_user] = lambda: demo_user("admin")
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/auth/admin-check").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_missing_credentials_are_rejected():
    with TestClient(app) as client:
        result = client.get("/api/v1/auth/me")
        assert result.status_code == 401
        assert result.json()["error"]["code"] == "UNAUTHENTICATED"
        assert client.get("/api/v1/dashboard").status_code == 401


def test_viewer_cannot_replay_synthetic_fixture():
    app.dependency_overrides[current_user] = lambda: demo_user("viewer")
    try:
        with TestClient(app) as client:
            result = client.post("/api/v1/demo/replay")
            assert result.status_code == 403
            assert result.json()["error"]["code"] == "FORBIDDEN"
    finally:
        app.dependency_overrides.clear()


def test_login_and_protected_request_with_fake_store():
    user = demo_user("viewer")
    user.password_hash = password_hash("a secure local password")

    class FakeDB:
        def __init__(self):
            self.audit = []

        def scalar(self, _query):
            return user

        def get(self, _model, user_id):
            return user if user_id == user.id else None

        def add(self, event):
            self.audit.append(event)

        def commit(self):
            pass

    fake = FakeDB()
    app.dependency_overrides[get_db] = lambda: fake
    try:
        with TestClient(app) as client:
            invalid = client.post("/api/v1/auth/token", data={"username": user.email,
                                                               "password": "wrong"})
            assert invalid.status_code == 401
            assert invalid.json()["error"]["code"] == "INVALID_CREDENTIALS"
            response = client.post("/api/v1/auth/token", data={"username": user.email,
                                                                "password": "a secure local password"})
            assert response.status_code == 200
            headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
            assert client.get("/api/v1/auth/me", headers=headers).json()["email"] == user.email
            assert client.get("/api/v1/auth/admin-check", headers=headers).status_code == 403
            assert [event.outcome for event in fake.audit] == ["denied", "allowed"]
    finally:
        app.dependency_overrides.clear()
