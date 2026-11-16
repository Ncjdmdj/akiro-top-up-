import os
import logging
import asyncio
import threading
from flask import Flask, jsonify
from app.db import init_db
from app.bot import create_bot_app

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='../templates')


@app.route('/')
def index():
    return "🤖 GameZone Topup Bot & Flask Server is running successfully 24/7!"


@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "service": "active"})


init_db()

_bot_started = False
_bot_lock = threading.Lock()


def run_telegram_bot():
    # thread នេះគ្មាន event loop ត្រូវបង្កើតថ្មី
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        bot_app = create_bot_app()
        if not bot_app:
            logger.error("create_bot_app() returned None (check BOT_TOKEN)")
            return
        logger.info("🤖 Starting Telegram Bot polling...")
        bot_app.run_polling(
            drop_pending_updates=True,
            stop_signals=None,   # signal handler ប្រើបានតែ main thread
            close_loop=False,
        )
    except Exception:
        logger.exception("Telegram bot crashed")


def start_bot_once():
    global _bot_started
    with _bot_lock:
        if _bot_started:
            return
        _bot_started = True
    threading.Thread(target=run_telegram_bot, daemon=True).start()


start_bot_once()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)