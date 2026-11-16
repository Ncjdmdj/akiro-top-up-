import os
import logging
import asyncio
from flask import Flask, render_template, jsonify
from app.db import init_db
from app.bot import create_bot_app
import threading

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

# ចាប់ផ្តើម Database Table ពេល Start App
init_db()

# បង្កើតនិងរត់ Telegram Bot ក្នុង Background Thread ជាមួយ Event Loop ថ្មី
bot_app = create_bot_app()
if bot_app:
    def run_telegram_bot():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info("🤖 Starting Telegram Bot polling...")
        loop.run_until_complete(bot_app.initialize())
        loop.run_until_complete(bot_app.start())
        bot_app.updater.start_polling()
        loop.run_forever()

    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)