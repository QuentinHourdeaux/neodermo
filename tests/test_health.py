"""Health contract and test isolation."""

from unittest.mock import patch

from sqlalchemy.exc import OperationalError

from neodermo import PROJECT_ROOT, create_app

RUNTIME_DB = PROJECT_ROOT / "var" / "neodermo.sqlite"


def test_health_ok(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": "ok"}


def test_health_fails_when_database_unavailable(client):
    with patch(
        "neodermo.api.health.db.session.execute",
        side_effect=OperationalError("SELECT 1", {}, Exception("down")),
    ):
        response = client.get("/api/health")

    _assert_safe_unavailable(response)
    assert "down" not in response.get_data(as_text=True)


def test_testing_config_ignores_runtime_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///var/neodermo.sqlite")
    monkeypatch.setenv("SECRET_KEY", "must-not-be-used")

    app = create_app("testing")

    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"
    assert app.config["SECRET_KEY"] == "test"


def test_health_fails_when_database_is_corrupt(tmp_path, monkeypatch):
    corrupt = tmp_path / "corrupt.sqlite"
    corrupt.write_bytes(b"this is not a sqlite database")
    before_runtime = _snapshot(RUNTIME_DB)

    monkeypatch.setenv("SECRET_KEY", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{corrupt}")

    app = create_app("development")
    response = app.test_client().get("/api/health")

    _assert_safe_unavailable(response)
    assert _snapshot(RUNTIME_DB) == before_runtime


def test_pytest_does_not_touch_runtime_database(client):
    before = _snapshot(RUNTIME_DB)

    client.get("/api/health")

    assert _snapshot(RUNTIME_DB) == before


def _assert_safe_unavailable(response):
    assert response.status_code == 503
    assert response.get_json() == {"status": "unavailable", "database": "error"}
    body = response.get_data(as_text=True)
    assert "sqlite" not in body
    assert "Traceback" not in body
    assert "<!doctype" not in body.lower()
    assert str(RUNTIME_DB) not in body


def _snapshot(path):
    if not path.exists():
        return None
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_size)
