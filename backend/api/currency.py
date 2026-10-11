"""
Currency conversion API.

Server-side companion to the dashboard's display-currency selector. Fetches
live reference rates from the keyless Frankfurter (ECB) API, caches them
in-memory for a few hours, and degrades gracefully to baked-in fallback rates
when the upstream service is unreachable.

The dashboard's native reporting currency is USD; all rates are quoted as
"1 unit of <base> = X units of <code>".
"""

import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger("uvicorn.error")

router = APIRouter(tags=["Currency Conversion"])

FX_ENDPOINT = "https://api.frankfurter.app/latest"
CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours
REQUEST_TIMEOUT_SECONDS = 8

# Currencies exposed by the API (ECB reference set — all resolvable live).
CURRENCY_META: Dict[str, Dict[str, str]] = {
    "USD": {"symbol": "$", "name": "US Dollar"},
    "EUR": {"symbol": "€", "name": "Euro"},
    "GBP": {"symbol": "£", "name": "British Pound"},
    "INR": {"symbol": "₹", "name": "Indian Rupee"},
    "JPY": {"symbol": "¥", "name": "Japanese Yen"},
    "AUD": {"symbol": "A$", "name": "Australian Dollar"},
    "CAD": {"symbol": "C$", "name": "Canadian Dollar"},
    "CHF": {"symbol": "CHF", "name": "Swiss Franc"},
    "CNY": {"symbol": "¥", "name": "Chinese Yuan"},
    "SGD": {"symbol": "S$", "name": "Singapore Dollar"},
    "HKD": {"symbol": "HK$", "name": "Hong Kong Dollar"},
    "BRL": {"symbol": "R$", "name": "Brazilian Real"},
    "ZAR": {"symbol": "R", "name": "South African Rand"},
    "MXN": {"symbol": "MX$", "name": "Mexican Peso"},
    "KRW": {"symbol": "₩", "name": "South Korean Won"},
    "SEK": {"symbol": "kr", "name": "Swedish Krona"},
    "NOK": {"symbol": "kr", "name": "Norwegian Krone"},
    "NZD": {"symbol": "NZ$", "name": "New Zealand Dollar"},
}

BASE_CURRENCY = "USD"

# Approximate offline rates quoted from USD, used only if the live fetch fails.
FALLBACK_RATES: Dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "INR": 83.4,
    "JPY": 151.2,
    "AUD": 1.52,
    "CAD": 1.36,
    "CHF": 0.88,
    "CNY": 7.24,
    "SGD": 1.34,
    "HKD": 7.82,
    "BRL": 5.05,
    "ZAR": 18.6,
    "MXN": 17.1,
    "KRW": 1335.0,
    "SEK": 10.5,
    "NOK": 10.7,
    "NZD": 1.64,
}

# base -> {rates, date, source, fetched_at}
_rate_cache: Dict[str, dict] = {}


def _normalize(code: str) -> str:
    return (code or "").strip().upper()


def _validate(code: str) -> str:
    normalized = _normalize(code)
    if normalized not in CURRENCY_META:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported currency '{code}'. Supported: {', '.join(CURRENCY_META)}.",
        )
    return normalized


def _fallback_rates(base: str) -> Dict[str, float]:
    base_rate = FALLBACK_RATES.get(base, 1.0)
    rates = {base: 1.0}
    for code, usd_rate in FALLBACK_RATES.items():
        if code == base:
            continue
        # Cross-rate via USD: (USD->code) / (USD->base)
        rates[code] = round(usd_rate / base_rate, 6)
    return rates


def _fetch_upstream(base: str) -> dict:
    """Fetch live rates from Frankfurter for the given base currency."""
    targets = [code for code in CURRENCY_META if code != base]
    query = urllib.parse.urlencode({"from": base, "to": ",".join(targets)})
    request = urllib.request.Request(
        f"{FX_ENDPOINT}?{query}",
        headers={"Accept": "application/json", "User-Agent": "CyberRisk-API/1.0"},
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def get_rates(base: str = BASE_CURRENCY, force: bool = False) -> dict:
    """
    Return a rate snapshot for `base`, using the in-memory cache when fresh.
    Never raises for upstream problems — falls back to static rates instead.
    """
    base = _normalize(base)
    now = time.time()
    cached = _rate_cache.get(base)

    if cached and not force and (now - cached["fetched_at"]) < CACHE_TTL_SECONDS:
        return {**cached, "cached": True}

    try:
        payload = _fetch_upstream(base)
        upstream_rates = payload.get("rates", {}) or {}
        rates = {base: 1.0}
        for code in CURRENCY_META:
            if code == base:
                continue
            value = upstream_rates.get(code)
            if isinstance(value, (int, float)) and value > 0:
                rates[code] = float(value)
            else:
                rates[code] = _fallback_rates(base)[code]

        snapshot = {
            "base": base,
            "rates": rates,
            "date": payload.get("date"),
            "source": "live",
            "fetched_at": now,
        }
        _rate_cache[base] = snapshot
        return {**snapshot, "cached": False}
    except Exception as exc:  # noqa: BLE001 - degrade gracefully on any upstream error
        logger.warning(f"Live FX fetch failed for base {base}: {exc}")
        if cached:
            return {**cached, "cached": True, "source": "stale-cache"}
        return {
            "base": base,
            "rates": _fallback_rates(base),
            "date": None,
            "source": "fallback",
            "fetched_at": now,
            "cached": False,
        }


@router.get("/currency/currencies")
def list_currencies():
    """Returns the currencies supported by the converter."""
    return {
        "base": BASE_CURRENCY,
        "currencies": [
            {"code": code, "symbol": meta["symbol"], "name": meta["name"]}
            for code, meta in CURRENCY_META.items()
        ],
    }


@router.get("/currency/rates")
def get_exchange_rates(
    base: str = Query(BASE_CURRENCY, description="Base currency code, e.g. USD"),
    force: bool = Query(False, description="Bypass the in-memory cache and refetch"),
):
    """
    Returns live exchange rates for the requested base currency.
    Falls back to cached or static rates if the upstream provider is unavailable.
    """
    snapshot = get_rates(_validate(base), force=force)
    return {
        "base": snapshot["base"],
        "date": snapshot["date"],
        "rates": snapshot["rates"],
        "source": snapshot["source"],
        "cached": snapshot["cached"],
        "updated_at": int(snapshot["fetched_at"] * 1000),
    }


@router.get("/currency/convert")
def convert_currency(
    amount: float = Query(..., gt=0, description="Amount to convert"),
    from_currency: str = Query(BASE_CURRENCY, alias="from", description="Source currency code"),
    to: str = Query(..., description="Target currency code"),
):
    """
    Converts an amount between two supported currencies using live cross-rates.

    Example: /currency/convert?amount=1000000&from=USD&to=INR
    """
    src = _validate(from_currency)
    dst = _validate(to)

    # Quote everything through USD so a single cache entry serves all pairs.
    usd_snapshot = get_rates(BASE_CURRENCY)
    usd_rates = usd_snapshot["rates"]

    rate = usd_rates.get(dst, 1.0) / usd_rates.get(src, 1.0)
    converted = round(amount * rate, 2)

    return {
        "from": src,
        "to": dst,
        "amount": amount,
        "rate": round(rate, 6),
        "converted": converted,
        "date": usd_snapshot["date"],
        "source": usd_snapshot["source"],
    }
