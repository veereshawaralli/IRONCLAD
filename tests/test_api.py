import pytest
from fastapi.testclient import TestClient

from ironclad.api import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("IRONCLAD_DB", str(tmp_path / "api.db"))
    monkeypatch.setenv("IRONCLAD_ADMIN_TOKEN", "test-token-01234567890123456789")
    with TestClient(create_app()) as c:
        yield c


def auth(client):
    assert (
        client.post(
            "/api/login", json={"token": "test-token-01234567890123456789"}
        ).status_code
        == 200
    )
    return {"X-Ironclad-Intent": "dashboard"}


def test_auth_and_csrf(client):
    assert client.get("/api/runs").status_code == 401
    headers = auth(client)
    assert client.post("/api/runs", json={"log": "Error"}).status_code == 403
    assert (
        client.post(
            "/api/runs", headers=headers, json={"log": "Error", "mode": "shell"}
        ).status_code
        == 422
    )


def test_queue_detail_settings(client):
    headers = auth(client)
    run = client.post(
        "/api/runs", headers=headers, json={"log": "ZeroDivisionError"}
    ).json()
    assert client.get("/api/runs").json()[0]["id"] == run["id"]
    assert client.get("/api/runs/" + run["id"]).json()["events"] == []
    assert client.get("/api/runs/missing").status_code == 404
    settings = client.get("/api/settings").json()
    settings["max_attempts"] = 4
    assert (
        client.put("/api/settings", headers=headers, json=settings).status_code == 422
    )
    settings["max_attempts"] = 2
    assert (
        client.put("/api/settings", headers=headers, json=settings).status_code == 200
    )


def test_demo_stream_resume(client):
    headers = auth(client)
    rid = client.post("/api/demo", headers=headers).json()["id"]
    data = client.get("/api/runs/" + rid).json()
    assert data["mode"] == "simulation"
    assert all(e["payload"]["simulated"] for e in data["events"])
    with client.websocket_connect("/api/runs/" + rid + "/stream?after=6") as ws:
        assert ws.receive_json()["seq"] == 7
        assert ws.receive_json()["seq"] == 8
        assert ws.receive_json()["heartbeat"]


def test_knowledge(client):
    auth(client)
    assert (
        client.get("/api/knowledge?q=average").json()["results"][0]["path"]
        == "stats.py"
    )
