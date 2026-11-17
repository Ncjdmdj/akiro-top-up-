import os
from dotenv import load_dotenv

load_dotenv()

def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

BOT_TOKEN = required("BOT_TOKEN")
KHMER_TOPUP_API_KEY = required("KHMER_TOPUP_API_KEY")
KHMER_TOPUP_BASE_URL = os.getenv("KHMER_TOPUP_BASE_URL", "https://khmer-topup.com/api/v1")
DATABASE_URL = required("DATABASE_URL")
ADMIN_USERNAME = required("ADMIN_USERNAME")
ADMIN_PASSWORD = required("ADMIN_PASSWORD")
SECRET_KEY = required("SECRET_KEY")
ADMIN_HOST = os.getenv("ADMIN_HOST", "0.0.0.0")
ADMIN_PORT = int(os.getenv("PORT") or os.getenv("ADMIN_PORT", "8080"))
# បន្ថែម Variable ទាំងនេះចូលក្នុង app/config.py របស់អ្នក
SHOP_NAME = os.getenv("SHOP_NAME", "Game Top Up Shop")
CURRENCY = os.getenv("CURRENCY", "USD")
DEFAULT_MARKUP = float(os.getenv("DEFAULT_MARKUP", "0.25"))
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

# ===== ABA PayWay Config =====
PAYWAY_MERCHANT_ID = os.getenv("PAYWAY_MERCHANT_ID", "")
PAYWAY_API_KEY = os.getenv("PAYWAY_API_KEY", "")
PAYWAY_API_URL = os.getenv(
    "PAYWAY_API_URL",
    "https://checkout-sandbox.payway.com.kh/api/payment-gateway/v1/payments/generate-qr",
)
PAYWAY_CHECK_URL = os.getenv(
    "PAYWAY_CHECK_URL",
    "https://checkout-sandbox.payway.com.kh/api/payment-gateway/v1/payments/check-transaction-2",
)
PAYWAY_CALLBACK_URL = os.getenv("PAYWAY_CALLBACK_URL", "")  # URL សាធារណៈ (បើមាន)
PAYWAY_QR_LIFETIME = os.getenv("PAYWAY_QR_LIFETIME", "30")   # នាទី

# ===== KHPay =====
KHPAY_API_KEY = os.getenv("KHPAY_API_KEY", "")
KHPAY_BASE_URL = os.getenv("KHPAY_BASE_URL", "https://khpay.site/api/v1").rstrip("/")
KHPAY_EXPIRES_IN = int(os.getenv("KHPAY_EXPIRES_IN", "1800"))  # វិនាទី