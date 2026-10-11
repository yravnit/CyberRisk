import time

from fastapi.testclient import TestClient

from api import currency
from api.main import app

client = TestClient(app)


def test_list_currencies():
    response = client.get("/currency/currencies")
    assert response.status_code == 200
    data = response.json()
    assert data["base"] == "USD"
    codes = {c["code"] for c in data["currencies"]}
    assert {"USD", "EUR", "INR", "GBP", "JPY"}.issubset(codes)


def _fake_snapshot(base="USD"):
    return {
        "base": base,
        "rates": {"USD": 1.0, "EUR": 0.5, "INR": 80.0},
        "date": "2026-01-01",
        "source": "test",
        "fetched_at": time.time(),
        "cached": False,
    }


def test_get_rates_returns_shape(monkeypatch):
    monkeypatch.setattr(currency, "get_rates", lambda base=currency.BASE_CURRENCY, force=False: _fake_snapshot(base))
    response = client.get("/currency/rates?base=USD")
    assert response.status_code == 200
    data = response.json()
    assert data["base"] == "USD"
    assert data["rates"]["USD"] == 1.0
    assert data["source"] == "test"
    assert "updated_at" in data


def test_convert_currency(monkeypatch):
    monkeypatch.setattr(currency, "get_rates", lambda base=currency.BASE_CURRENCY, force=False: _fake_snapshot(base))
    response = client.get("/currency/convert?amount=1000&from=USD&to=EUR")
    assert response.status_code == 200
    data = response.json()
    assert data["from"] == "USD"
    assert data["to"] == "EUR"
    assert data["rate"] == 0.5
    assert data["converted"] == 500.0


def test_convert_cross_rate(monkeypatch):
    monkeypatch.setattr(currency, "get_rates", lambda base=currency.BASE_CURRENCY, force=False: _fake_snapshot(base))
    response = client.get("/currency/convert?amount=80&from=INR&to=EUR")
    assert response.status_code == 200
    data = response.json()
    assert data["rate"] == 0.00625
    assert data["converted"] == 0.5


def test_rejects_unsupported_currency():
    response = client.get("/currency/convert?amount=100&from=USD&to=XYZ")
    assert response.status_code == 400
    assert "Unsupported currency" in response.json()["detail"]


def test_fallback_rates_are_relative_to_base():
    usd = currency._fallback_rates("USD")
    assert usd["USD"] == 1.0
    inr = currency._fallback_rates("INR")
    assert inr["INR"] == 1.0
    assert inr["USD"] > 0
