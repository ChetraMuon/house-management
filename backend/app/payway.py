"""ABA PayWay QR payment client.

Docs: https://developer.payway.com.kh/

Every request is signed with HMAC-SHA512 (Base64) over a fixed field order.
The API key never leaves the backend.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from .config import settings
from .money import q


class PaywayError(Exception):
    """A safe, user-facing PayWay error (never includes the API key)."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code


def enabled() -> bool:
    return bool(settings.PAYWAY_ENABLED and settings.PAYWAY_MERCHANT_ID and settings.PAYWAY_API_KEY)


def is_sandbox() -> bool:
    """True when the configured PayWay base URL is the sandbox environment."""
    return "sandbox" in settings.PAYWAY_BASE_URL.lower()


def simulator_available() -> bool:
    """The built-in test payer is deliberately limited to sandbox mode."""
    return bool(enabled() and is_sandbox() and settings.PAYWAY_SIMULATOR_ENABLED)


def _req_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _hash(parts: list[str | None]) -> str:
    message = "".join("" if part is None else str(part) for part in parts)
    digest = hmac.new(
        settings.PAYWAY_API_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha512,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _amount(value: Decimal) -> str:
    if settings.PAYWAY_CURRENCY.upper() == "KHR":
        return str(int(q(value)))
    return f"{q(value):.2f}"


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not enabled():
        raise PaywayError("PayWay is not configured")

    url = f"{settings.PAYWAY_BASE_URL.rstrip('/')}{path}"
    try:
        response = httpx.post(url, json=payload, timeout=20.0)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        raise PaywayError("Could not reach PayWay. Please try again.") from exc
    except ValueError as exc:
        raise PaywayError("PayWay returned an invalid response.") from exc

    if not isinstance(data, dict):
        raise PaywayError("PayWay returned an invalid response.")
    return data


def _check_status(data: dict[str, Any], *, success: str, fallback: str) -> dict[str, Any]:
    status = data.get("status") or {}
    code = status.get("code")
    if str(code) != success:
        raise PaywayError(status.get("message") or fallback, None if code is None else str(code))
    return data


def _encode_items(rows: list[dict[str, Any]]) -> str:
    return base64.b64encode(
        json.dumps(rows, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def _items_payload(items: list[dict[str, Any]]) -> str:
    """Base64 JSON item list. PayWay caps this field at 500 characters, so
    long product names are shortened and a summary line is the last resort."""
    rows = [
        {
            "name": str(item.get("name") or "Item")[:100],
            "quantity": int(item.get("quantity") or 1),
            "price": float(q(item.get("price") or 0)),
        }
        for item in items[:10]
    ]
    if not rows:
        return _encode_items([])

    encoded = _encode_items(rows)
    if len(encoded) <= 500:
        return encoded

    for limit in (60, 40, 25, 15, 8):
        trimmed = [{**row, "name": row["name"][:limit]} for row in rows]
        encoded = _encode_items(trimmed)
        if len(encoded) <= 500:
            return encoded

    total = q(
        sum(
            Decimal(str(item.get("price") or 0)) * int(item.get("quantity") or 1)
            for item in items[:10]
        )
    )
    return _encode_items([{"name": "Sale", "quantity": 1, "price": float(total)}])


def generate_qr(
    *,
    tran_id: str,
    amount: Decimal,
    items: list[dict[str, Any]],
    lifetime_minutes: int,
) -> dict[str, Any]:
    """Create a dynamic ABA KHQR. Returns PayWay's response (qrImage, qrString...)."""
    req_time = _req_time()
    merchant_id = settings.PAYWAY_MERCHANT_ID
    amount_str = _amount(amount)
    items_str = _items_payload(items)
    callback_url = (
        base64.b64encode(settings.PAYWAY_CALLBACK_URL.encode("utf-8")).decode("ascii")
        if settings.PAYWAY_CALLBACK_URL
        else ""
    )
    purchase_type = "purchase"
    payment_option = "abapay_khqr"
    currency = settings.PAYWAY_CURRENCY.upper()
    lifetime = int(lifetime_minutes)
    template = settings.PAYWAY_QR_IMAGE_TEMPLATE

    # Hash order is defined by PayWay and differs from the JSON field order:
    # ... callback_url, return_deeplink, currency, custom_fields, return_params,
    # payout, lifetime, qr_image_template.
    signature = _hash([
        req_time, merchant_id, tran_id, amount_str, items_str,
        None, None, None, None,  # first_name, last_name, email, phone
        purchase_type, payment_option, callback_url,
        None,  # return_deeplink
        currency,
        None, None, None,  # custom_fields, return_params, payout
        lifetime, template,
    ])

    payload: dict[str, Any] = {
        "req_time": req_time,
        "merchant_id": merchant_id,
        "tran_id": tran_id,
        "amount": amount_str,
        "items": items_str,
        "purchase_type": purchase_type,
        "payment_option": payment_option,
        "currency": currency,
        "lifetime": lifetime,
        "qr_image_template": template,
        "hash": signature,
    }
    if callback_url:
        payload["callback_url"] = callback_url

    data = _post("/api/payment-gateway/v1/payments/generate-qr", payload)
    return _check_status(data, success="0", fallback="PayWay rejected the QR request.")


def check_transaction(tran_id: str) -> dict[str, Any]:
    """Ask PayWay for the authoritative status of a transaction."""
    req_time = _req_time()
    merchant_id = settings.PAYWAY_MERCHANT_ID
    payload = {
        "req_time": req_time,
        "merchant_id": merchant_id,
        "tran_id": tran_id,
        "hash": _hash([req_time, merchant_id, tran_id]),
    }
    data = _post("/api/payment-gateway/v1/payments/check-transaction-2", payload)
    return _check_status(data, success="00", fallback="Could not check the PayWay transaction.")


def close_transaction(tran_id: str) -> dict[str, Any]:
    """Cancel a pending transaction so an old QR cannot be paid."""
    req_time = _req_time()
    merchant_id = settings.PAYWAY_MERCHANT_ID
    payload = {
        "req_time": req_time,
        "merchant_id": merchant_id,
        "tran_id": tran_id,
        "hash": _hash([req_time, merchant_id, tran_id]),
    }
    data = _post("/api/payment-gateway/v1/payments/close-transaction", payload)
    return _check_status(data, success="00", fallback="Could not close the PayWay transaction.")


def payment_state(data: dict[str, Any]) -> str:
    """Normalised PayWay payment status: APPROVED / PENDING / DECLINED / ..."""
    payload = data.get("data") or {}
    return str(payload.get("payment_status") or "").upper()


def payment_reference(data: dict[str, Any]) -> str | None:
    payload = data.get("data") or {}
    reference = payload.get("apv") or payload.get("transaction_id") or payload.get("bank_ref")
    return str(reference) if reference else None
