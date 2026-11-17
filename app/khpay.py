import logging
import requests
from app.config import KHPAY_API_KEY, KHPAY_BASE_URL, KHPAY_EXPIRES_IN

log = logging.getLogger(__name__)


def _headers():
    return {
        "Authorization": f"Bearer {KHPAY_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }


def create_khpay_qr(order_ref, amount):
    if not KHPAY_API_KEY:
        return {"success": False, "message": "KHPAY_API_KEY មិនទាន់ដាក់"}
    body = {
        "amount": f"{float(amount):.2f}",
        "currency": "USD",
        "note": order_ref,
        "expires_in": KHPAY_EXPIRES_IN,
    }
    url = f"{KHPAY_BASE_URL}/qr/generate"
    try:
        r = requests.post(url, json=body, headers=_headers(), timeout=25)
    except Exception as e:
        log.error("KHPay request error: %s", e)
        return {"success": False, "message": str(e)[:200]}

    try:
        d = r.json()
    except ValueError:
        log.error("KHPay non-JSON: url=%s status=%s body=%r", url, r.status_code, r.text[:300])
        return {"success": False, "message": f"HTTP {r.status_code} non-JSON"}

    if not r.ok:
        log.warning("KHPay generate HTTP %s: %s", r.status_code, d)
        return {"success": False, "message": str(d.get("message") or d.get("error") or d)[:200]}
    if not d.get("success"):
        log.warning("KHPay generate failed: %s %s", d.get("error_code"), d.get("error"))
        return {"success": False, "message": f"{d.get('error_code', '')}: {d.get('error', d)}"[:200]}

    data = d.get("data") or {}
    txn = data.get("transaction_id")
    log.info("KHPay generate OK: txn=%s", txn)
    return {
        "success": bool(txn),
        "transaction_id": txn,
        "qr_url": data.get("qr_image") or data.get("qr_url"),
        "payment_url": data.get("payment_url"),
        "message": "" if txn else "transaction_id missing",
    }


def check_khpay_paid(transaction_id):
    url = f"{KHPAY_BASE_URL}/qr/check/{transaction_id}"
    try:
        r = requests.get(url, headers=_headers(), timeout=20)
        d = r.json()
    except Exception as e:
        log.warning("KHPay check error: %s", e)
        return False
    if not d.get("success"):
        log.warning("KHPay check not success: %s", str(d)[:200])
        return False
    data = d.get("data") or {}
    return bool(data.get("paid")) or str(data.get("action") or "").lower() == "approved"