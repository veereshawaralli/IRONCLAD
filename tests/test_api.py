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


def test_webhook_signature_and_deduplication(client, monkeypatch):
    import hashlib
    import hmac
    import json

    monkeypatch.setenv("IRONCLAD_WEBHOOK_SECRET", "signing-secret-0123456789012345")
    monkeypatch.setenv("IRONCLAD_GITHUB_REPO", "example/repo")
    body = json.dumps(
        {
            "repository": {"full_name": "example/repo"},
            "action": "completed",
            "check_run": {
                "conclusion": "failure",
                "head_sha": "abc",
                "output": {"summary": "ZeroDivisionError"},
            },
        }
    ).encode()
    assert client.post("/api/webhooks/github", content=body).status_code == 401
    headers = {
        "X-Hub-Signature-256": "sha256="
        + hmac.new(
            b"signing-secret-0123456789012345", body, hashlib.sha256
        ).hexdigest(),
        "X-GitHub-Event": "check_run",
        "X-GitHub-Delivery": "delivery-1",
    }
    first = client.post("/api/webhooks/github", content=body, headers=headers)
    second = client.post("/api/webhooks/github", content=body, headers=headers)
    assert first.status_code == 200
    assert second.json()["duplicate"]
    assert first.json()["id"] == second.json()["id"]


def test_metrics_and_simulation_publication_blocked(client):
    headers = auth(client)
    rid = client.post("/api/demo", headers=headers).json()["id"]
    assert "ironclad_incidents 1" in client.get("/api/metrics").text
    assert (
        client.post(
            "/api/runs/" + rid + "/approve", headers=headers, json={"confirmed": True}
        ).status_code
        == 409
    )


def test_login_rate_limit(client):
    for _ in range(10):
        assert client.post("/api/login", json={"token": "wrong"}).status_code == 401
    assert client.post("/api/login", json={"token": "wrong"}).status_code == 429


def test_paginated_history(client):
    headers = auth(client)
    for _ in range(3):
        client.post("/api/runs", headers=headers, json={"log": "fixture"})
    first = client.get("/api/runs?limit=2&offset=0").json()
    second = client.get("/api/runs?limit=2&offset=2").json()
    assert len(first) == 2 and len(second) == 1
    assert not ({r["id"] for r in first} & {r["id"] for r in second})
    assert client.get("/api/runs?limit=10000").status_code == 422


def test_logout_revokes_server_session(client):
    headers = auth(client)
    old = client.cookies["ironclad_session"]
    assert client.post("/api/logout", headers=headers).status_code == 200
    client.cookies.set("ironclad_session", old)
    assert client.get("/api/runs").status_code == 401


def test_chunked_body_limit(client):
    def chunks():
        for _ in range(16):
            yield b"x" * 65536

    assert (
        client.post(
            "/api/login", content=chunks(), headers={"Content-Type": "application/json"}
        ).status_code
        == 413
    )
