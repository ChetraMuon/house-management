import json
from datetime import datetime
from urllib.request import Request, urlopen

from .config import settings


def _send_telegram_message(text: str) -> bool:
    token = settings.TELEGRAM_BOT_TOKEN.strip()
    chat_id = settings.TELEGRAM_CHAT_ID.strip()
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }).encode("utf-8")

    request = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=10) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body or "{}")
        return bool(data.get("ok"))
    except Exception:
        return False


def build_stock_message(
    action: str,
    product_name: str,
    quantity: int,
    actor_name: str,
    total_stock: int | None = None,
    reference: str | None = None,
    note: str | None = None,
) -> str:
    lines = [
        f"📦 Stock {action.upper()}",
        f"Product: {product_name}",
        f"Quantity: {quantity}",
        f"By: {actor_name}",
    ]
    if total_stock is not None:
        lines.append(f"Total stock: {total_stock}")
    if reference:
        lines.append(f"Reference: {reference}")
    if note:
        lines.append(f"Note: {note}")
    return "\n".join(lines)


def build_low_stock_message(product_name: str, stock_qty: int, min_stock: int, actor_name: str | None = None, reference: str | None = None) -> str:
    lines = [
        "⚠️ LOW STOCK",
        f"Product: {product_name}",
        f"Current stock: {stock_qty}",
        f"Minimum stock: {min_stock}",
    ]
    if actor_name:
        lines.append(f"Updated by: {actor_name}")
    if reference:
        lines.append(f"Reference: {reference}")
    return "\n".join(lines)


def build_approval_message(decision: str, receipt_no: str, total: int | float, admin_name: str, note: str | None = None) -> str:
    lines = [
        "📣 SALE APPROVAL ALERT",
        f"Decision: {decision.upper()}",
        f"Receipt: {receipt_no}",
        f"Total: ${float(total):.2f}",
        f"By: {admin_name}",
    ]
    if note:
        lines.append(f"Note: {note}")
    return "\n".join(lines)


def build_sale_paid_message(
    receipt_no: str,
    total: int | float,
    payment_label: str,
    cashier_name: str,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    paid_at: datetime | None = None,
) -> str:
    lines = [
        "💰 SALE PAID",
        f"Receipt: {receipt_no}",
        f"Total: ${float(total):.2f}",
        f"Payment: {payment_label}",
        f"Cashier: {cashier_name}",
    ]
    if customer_name:
        lines.append(f"Customer: {customer_name}")
    if customer_phone:
        lines.append(f"Phone: {customer_phone}")
    lines.append(f"Time: {(paid_at or datetime.now()).strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


def send_sale_paid_notification(
    receipt_no: str,
    total: int | float,
    payment_label: str,
    cashier_name: str,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    paid_at: datetime | None = None,
) -> bool:
    return _send_telegram_message(
        build_sale_paid_message(
            receipt_no,
            total,
            payment_label,
            cashier_name,
            customer_name,
            customer_phone,
            paid_at,
        )
    )


def send_stock_notification(
    action: str,
    product_name: str,
    quantity: int,
    actor_name: str,
    total_stock: int | None = None,
    reference: str | None = None,
    note: str | None = None,
) -> bool:
    return _send_telegram_message(
        build_stock_message(action, product_name, quantity, actor_name, total_stock, reference, note)
    )


def send_low_stock_notification(product_name: str, stock_qty: int, min_stock: int, actor_name: str | None = None, reference: str | None = None) -> bool:
    return _send_telegram_message(build_low_stock_message(product_name, stock_qty, min_stock, actor_name, reference))


def send_approval_notification(decision: str, receipt_no: str, total: int | float, admin_name: str, note: str | None = None) -> bool:
    return _send_telegram_message(build_approval_message(decision, receipt_no, total, admin_name, note))
