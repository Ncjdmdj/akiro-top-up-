import logging
import requests
from app.config import KHPAY_API_KEY, KHPAY_BASE_URL, KHPAY_EXPIRES_IN

log = logging.getLogger(__name__)


def _headers():
    return {"Authorization": f"Bearer {KHPAY_API_KEY}", "Content-Type": "application/json"}


def create_khpay_qr(order_ref, amount):
    if not KHPAY_API_KEY:
        return {"success": False, "message": "KHPAY_API_KEY មិនទាន់ដាក់ក្នុង .env"}
    body = {
        "amount": f"{float(amount):.2f}",
        "currency": "USD",
        "note": order_ref,
        "expires_in": KHPAY_EXPIRES_IN,
    }
    try:
        r = requests.post(f"{KHPAY_BASE_URL}/qr/generate", json=body, headers=_headers(), timeout=25)
        d = r.json()
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
            "qr_url": data.get("qr_image") or data.get("qr_url"),  # data:image/png;base64,...
            "payment_url": data.get("payment_url"),
            "message": "" if txn else "transaction_id missing",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def check_khpay_paid(transaction_id):
    try:
        r = requests.get(f"{KHPAY_BASE_URL}/qr/check/{transaction_id}", headers=_headers(), timeout=20)
        d = r.json()
        if not d.get("success"):
            return False
        data = d.get("data") or {}
        return bool(data.get("paid")) or str(data.get("action") or "").lower() == "approved"
    except Exception:
        return False