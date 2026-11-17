import os
import time
import uuid
import asyncio
import logging
import html
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters,
)
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE = os.getenv("KHMER_TOPUP_BASE_URL", "https://khmer-topup.com/api/v1").rstrip("/")
API_KEY = os.getenv("KHMER_TOPUP_API_KEY")
ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID")

HEADERS = {"Authorization": f"Bearer {API_KEY}"}
TIMEOUT = 20

_games_cache = {"data": None, "ts": 0}


# ---------- API ----------
def _api(method, path, **kw):
    r = requests.request(method, f"{API_BASE}{path}", headers=HEADERS, timeout=TIMEOUT, **kw)
    try:
        data = r.json()
    except Exception:
        data = {"message": r.text[:200]}
    return r.status_code, data


async def api(method, path, **kw):
    return await asyncio.to_thread(_api, method, path, **kw)


async def get_games():
    if _games_cache["data"] and time.time() - _games_cache["ts"] < 300:
        return _games_cache["data"]
    status, data = await api("GET", "/games")
    if status != 200:
        logger.error("games failed %s %s", status, data)
        return None
    _games_cache.update(data=data.get("games", []), ts=time.time())
    return _games_cache["data"]


def find_game(games, slug):
    return next((g for g in games if g["slug"] == slug), None)


def find_pkg(game, pid):
    return next((p for p in game["packages"] if str(p["package_id"]) == str(pid)), None)


async def notify_admin(context, text):
    if ADMIN_ID:
        try:
            await context.bot.send_message(int(ADMIN_ID), text)
        except Exception:
            logger.exception("notify_admin failed")


# ---------- UI ----------
async def show_games(target, edit=False):
    games = await get_games()
    if not games:
        text = "❌ មិនអាចទាញបញ្ជីហ្គេមបានទេ សូមសាកល្បងម្តងទៀតពេលក្រោយ។"
        return await (target.edit_message_text(text) if edit else target.reply_text(text))
    kb = [[InlineKeyboardButton(f"🎮 {g['name']}", callback_data=f"g:{g['slug']}")] for g in games]
    text = "👋 សួស្តី! សូមជ្រើសរើសហ្គេមដែលអ្នកចង់បំពេញ៖"
    markup = InlineKeyboardMarkup(kb)
    if edit:
        await target.edit_message_text(text, reply_markup=markup)
    else:
        await target.reply_text(text, reply_markup=markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await show_games(update.message)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    ud = context.user_data

    if data == "back":
        ud.clear()
        return await show_games(q, edit=True)

    if data.startswith("g:"):
        games = await get_games()
        game = find_game(games or [], data[2:])
        if not game:
            return await q.edit_message_text("❌ រកមិនឃើញហ្គេម។ វាយ /start ម្តងទៀត។")
        ud.clear()
        ud["slug"] = game["slug"]
        kb = [
            [InlineKeyboardButton(f"💎 {p['name']} - ${p['price']:.2f}", callback_data=f"p:{p['package_id']}")]
            for p in game["packages"]
        ]
        kb.append([InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="back")])
        return await q.edit_message_text(
            f"📦 {game['name']}\n\n👇 សូមជ្រើសរើសកញ្ចប់៖", reply_markup=InlineKeyboardMarkup(kb)
        )

    if data.startswith("p:"):
        games = await get_games()
        game = find_game(games or [], ud.get("slug"))
        pkg = find_pkg(game, data[2:]) if game else None
        if not pkg:
            return await q.edit_message_text("❌ Session ផុតកំណត់។ វាយ /start ម្តងទៀត។")
        ud.update(package_id=pkg["package_id"], package_name=pkg["name"], price=pkg["price"], step="player_id")
        return await q.edit_message_text(f"🆔 សូមផ្ញើ {game.get('id_label') or 'Player ID'} របស់អ្នក៖")

    if data == "retry":
        ud["step"] = "player_id"
        ud.pop("reference", None)
        return await q.edit_message_text("🆔 សូមវាយ Player ID ថ្មីម្តងទៀត៖")

    if data == "confirm":
        return await place_order(q, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    text = (update.message.text or "").strip()
    step = ud.get("step")
    if not step:
        return await update.message.reply_text("⚠️ សូមវាយ /start ដើម្បីចាប់ផ្តើម។")

    games = await get_games()
    game = find_game(games or [], ud.get("slug"))
    if not game:
        return await update.message.reply_text("❌ Session ផុតកំណត់។ វាយ /start ម្តងទៀត។")

    if step == "player_id":
        if not text or len(text) > 32:
            return await update.message.reply_text("⚠️ Player ID មិនត្រឹមត្រូវ (អតិបរមា 32 តួអក្សរ)។")
        ud["player_id"] = text
        if game.get("server_label"):
            ud["step"] = "server_id"
            return await update.message.reply_text(f"🌐 សូមផ្ញើ {game['server_label']}៖")
        ud["server_id"] = ""
        return await verify_and_confirm(update, context, game)

    if step == "server_id":
        if not text or len(text) > 16:
            return await update.message.reply_text("⚠️ Server/Zone ID មិនត្រឹមត្រូវ (អតិបរមា 16 តួអក្សរ)។")
        ud["server_id"] = text
        return await verify_and_confirm(update, context, game)


async def verify_and_confirm(update, context, game):
    ud = context.user_data
    ud["step"] = None
    msg = await update.message.reply_text("⏳ កំពុងផ្ទៀងផ្ទាត់គណនី...")

    status, res = await api("GET", "/check", params={
        "slug": game["slug"], "player_id": ud["player_id"], "server_id": ud["server_id"],
    })
    result = res.get("result") if status == 200 else "unknown"

    retry_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 វាយ ID ម្តងទៀត", callback_data="retry")]])

    if result == "invalid":
        return await msg.edit_text("❌ គណនីមិនត្រឹមត្រូវ។ សូមពិនិត្យ ID ហើយសាកល្បងម្តងទៀត។", reply_markup=retry_kb)
    if result == "incomplete":
        return await msg.edit_text(f"⚠️ ព័ត៌មានមិនគ្រប់គ្រាន់។ {res.get('message', '')}", reply_markup=retry_kb)

    nick = html.escape(res.get("nickname") or "-")
    warn = "\n⚠️ មិនអាចផ្ទៀងផ្ទាត់ឈ្មោះបានទេ សូមពិនិត្យ ID ឲ្យច្បាស់។" if result == "unknown" else ""

    ud["reference"] = f"tg{update.effective_user.id}-{uuid.uuid4().hex[:16]}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ត្រឹមត្រូវ (Confirm)", callback_data="confirm")],
        [InlineKeyboardButton("❌ ច្រឡំ / កែប្រែ", callback_data="retry")],
    ])
    await msg.edit_text(
        f"🧾 សូមផ្ទៀងផ្ទាត់៖\n\n"
        f"🎮 {game['name']}\n"
        f"📦 {ud['package_name']} - ${ud['price']:.2f}\n"
        f"👤 Player ID: {ud['player_id']}\n"
        f"🌐 Server: {ud['server_id'] or '-'}\n"
        f"🏷 ឈ្មោះ: {nick}{warn}\n\n"
        f"⚠️ ពិនិត្យឲ្យច្បាស់មុនចុចបញ្ជាក់!",
        reply_markup=kb,
    )


async def place_order(q, context):
    ud = context.user_data
    if not ud.get("reference") or not ud.get("package_id"):
        return await q.edit_message_text("❌ Session ផុតកំណត់។ វាយ /start ម្តងទៀត។")

    await q.edit_message_text("⏳ កំពុងដាក់ការបញ្ជាទិញ...")
    body = {
        "package_id": ud["package_id"],
        "player_id": ud["player_id"],
        "server_id": ud["server_id"],
        "reference": ud["reference"],  # reference ដដែល = retry មិនកាត់លុយពីរដង
    }
    try:
        status, res = await api("POST", "/orders", json=body)
    except requests.Timeout:
        return await q.edit_message_text(
            "⚠️ ម៉ាស៊ីនបម្រើយឺត។ សូមចុច Confirm ម្តងទៀត (នឹងមិនកាត់លុយពីរដងទេ)។",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Confirm", callback_data="confirm")]]),
        )
    except Exception:
        logger.exception("order failed")
        return await q.edit_message_text("❌ មានបញ្ហាបច្ចេកទេស សូមព្យាយាមម្តងទៀត។")

    if status == 200:
        code = res["order_code"]
        ud.clear()
        await q.edit_message_text(f"✅ បានទទួលការបញ្ជាទិញ\n🧾 Order: {code}\n⏳ កំពុងដំណើរការ...")
        context.application.create_task(poll_order(q, context, code, res))
        return

    logger.error("order error %s %s", status, res)
    if status == 402:
        await notify_admin(context, "⚠️ Wallet khmer-topup អស់លុយ! សូមបញ្ចូលទឹកប្រាក់។")
        return await q.edit_message_text("❌ សេវាកម្មបណ្តោះអាសន្នមិនអាចប្រើបាន។ សូមទាក់ទង Admin។")
    if status in (401, 403):
        await notify_admin(context, f"⚠️ API key/IP បញ្ហា ({status}): {res.get('message')}")
        return await q.edit_message_text("❌ សេវាកម្មមានបញ្ហា។ សូមទាក់ទង Admin។")
    if status == 429:
        return await q.edit_message_text("⏳ សំណើច្រើនពេក សូមរង់ចាំបន្តិចហើយសាកល្បងម្តងទៀត។")
    await q.edit_message_text(f"❌ បញ្ជាទិញមិនបានសម្រេច ({status})។ {res.get('message', '')}")


async def poll_order(q, context, code, first):
    title = f"🎮 {first.get('game')} - {first.get('package')}\n🧾 {code}\n"
    for _ in range(36):  # ~6 នាទី
        await asyncio.sleep(10)
        try:
            status, res = await api("GET", f"/orders/{code}")
        except Exception:
            continue
        st = res.get("status") if status == 200 else None
        if st == "completed":
            return await q.edit_message_text(f"{title}✅ បំពេញជោគជ័យ! សូមអរគុណ 🎉")
        if st == "refunded":
            await notify_admin(context, f"↩️ Order {code} refunded")
            return await q.edit_message_text(f"{title}↩️ ការបញ្ជាទិញត្រូវបានhoàn ប្រាក់។ សូមទាក់ទង Admin។")
    await notify_admin(context, f"⏰ Order {code} នៅ processing លើស 6 នាទី")
    await q.edit_message_text(f"{title}⏳ នៅកំពុងដំណើរការ។ សូមរង់ចាំ ឬទាក់ទង Admin ជាមួយលេខ Order។")


def create_bot_app():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN missing")
        return None
    if not API_KEY:
        logger.error("KHMER_TOPUP_API_KEY missing")
        return None
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app