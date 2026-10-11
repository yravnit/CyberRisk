"""Auth + session isolation checks. One runnable guard for the security path."""

import uuid

from fastapi.testclient import TestClient

from api.main import app


def _anon():
    return TestClient(app)


def test_health_is_public():
    resp = _anon().get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_protected_endpoint_requires_token():
    resp = _anon().get("/risk/assets")
    assert resp.status_code == 401


def test_bad_token_rejected():
    resp = _anon().get("/risk/assets", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def _register(c: TestClient, password: str = "strong-pass-1") -> str:
    username = f"user_{uuid.uuid4().hex[:10]}"
    resp = c.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()["token"]


def test_register_login_me_flow():
    c = TestClient(app)
    username = f"flow_{uuid.uuid4().hex[:10]}"
    reg = c.post("/api/auth/register", json={"username": username, "password": "strong-pass-1"})
    assert reg.status_code == 201
    token = reg.json()["token"]
    assert token

    me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == username

    login = c.post("/api/auth/login", json={"username": username, "password": "strong-pass-1"})
    assert login.status_code == 200
    assert login.json()["user"]["username"] == username


def test_duplicate_username_rejected():
    c = TestClient(app)
    username = f"dupe_{uuid.uuid4().hex[:10]}"
    body = {"username": username, "password": "strong-pass-1"}
    assert c.post("/api/auth/register", json=body).status_code == 201
    assert c.post("/api/auth/register", json=body).status_code == 409


def test_wrong_password_rejected():
    c = TestClient(app)
    username = f"wrong_{uuid.uuid4().hex[:10]}"
    assert c.post(
        "/api/auth/register", json={"username": username, "password": "strong-pass-1"}
    ).status_code == 201
    bad = c.post("/api/auth/login", json={"username": username, "password": "wrong-pass-9"})
    assert bad.status_code == 401


def test_short_password_rejected():
    c = TestClient(app)
    resp = c.post(
        "/api/auth/register",
        json={"username": f"short_{uuid.uuid4().hex[:8]}", "password": "abc"},
    )
    assert resp.status_code == 422  # pydantic min_length


def test_sessions_are_isolated_per_user():
    """User B must never be served user A's uploaded dataset."""
    a, b = TestClient(app), TestClient(app)
    token_a, token_b = _register(a), _register(b)

    assert a.post("/api/datasets/demo", headers={"Authorization": f"Bearer {token_a}"}).status_code == 200

    # B has no dataset yet: their outputs are not ready, and crucially they do
    # not silently fall through to A's session data.
    status_b = b.get("/api/datasets/status", headers={"Authorization": f"Bearer {token_b}"})
    assert status_b.status_code == 200
    assert status_b.json()["outputs_ready"] is False

    # B uploads their own; now B sees their own data, not A's.
    files = [
        ("files", ("assets.csv", b"asset_id,business_unit,criticality,data_sensitivity_tier,financial_value_usd,downtime_cost_per_hour_usd\nAST-B1,Ops,2,Public,1000,10\n", "text/csv")),
        ("files", ("controls.csv", b"control_id,name,risk_reduction_pct,cost_usd\nCTRL-B1,MFA,0.5,1000\n", "text/csv")),
        ("files", ("asset_controls.csv", b"asset_id,control_id\nAST-B1,CTRL-B1\n", "text/csv")),
        ("files", ("threat_events.csv", b"event_id,asset_id,downtime_hours_caused,records_compromised\nEVT-B1,AST-B1,1,5\n", "text/csv")),
        ("files", ("vulnerabilities.csv", b"asset_id,cve_id,cvss_score,epss_score\nAST-B1,CVE-2024-0001,7.0,0.3\n", "text/csv")),
    ]
    up = b.post("/api/datasets/upload", files=files, headers={"Authorization": f"Bearer {token_b}"})
    assert up.status_code == 200, up.text

    assets_b = b.get("/risk/assets", headers={"Authorization": f"Bearer {token_b}"})
    assert assets_b.status_code == 200
    ids_b = {r["asset_id"] for r in assets_b.json()}
    assert ids_b == {"AST-B1"}  # B sees their own single asset, not A's demo fleet

    assets_a = a.get("/risk/assets", headers={"Authorization": f"Bearer {token_a}"})
    assert {r["asset_id"] for r in assets_a.json()}.isdisjoint({"AST-B1"})
