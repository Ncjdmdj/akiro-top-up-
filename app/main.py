import logging, threading
from app.db import init_db
from app.bot import build_bot
from app.admin import create_admin_app
from app.config import ADMIN_HOST, ADMIN_PORT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

def run_web():
    web = create_admin_app()
    web.run(host=ADMIN_HOST, port=ADMIN_PORT, debug=False, use_reloader=False)

def main():
    init_db()
    threading.Thread(target=run_web, daemon=True).start()
    bot = build_bot()
    bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
