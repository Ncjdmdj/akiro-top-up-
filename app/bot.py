import asyncio
import base64
import html
import io
import logging
import math
import time
import uuid
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

from app.config import ADMIN_TELEGRAM_ID, BOT_TOKEN, DEFAULT_MARKUP, KHPAY_EXPIRES_IN, SHOP_NAME
from app.db import SessionLocal
from app.khpay import check_khpay_paid, create_khpay_qr
from app.models import ShopOrder
from app.services import approve_order, refresh_processing_orders, supplier
from app.supplier import SupplierError

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)  # កុំអោយ token ចេញក្នុង log

HTML = ParseMode.HTML
esc = html.escape
PER_PAGE = 8
MAX_RETRY = 20          # ចំនួនដងអតិបរមា retry approve (ម្តងក្នុង ~30s)
TXN_PREFIX = "khpay:"   # txn_id ទុកក្នុង ShopOrder.receipt_file_id (មិនចាំបាច់ migrate)

STATUS_KM = {
    "awaiting_payment": "⏳ រង់ចាំបង់ប្រាក់",
    "payment_submitted": "💳 បានបង់ - កំពុងដំណើរការ",
    "processing": "⚙️ កំពុងដំណើរការ",
    "pending": "⚙️ កំពុងដំណើរការ",
    "accepted": "⚙️ កំពុងដំណើរការ",
    "completed": "✅ ជោគជ័យ",
    "refunded": "↩️ មានបញ្ហា (ទាក់ទង Admin)",
    "expired": "⌛ ផុតកំណត់",
    "cancelled": "🚫 បោះបង់",
}

_cache = {"games": None, "ts": 0.0}
_fail_count: dict[str, int] = {}
_fail_notified: set[str] = set()


# ============================================================
# Helpers
# ============================================================
def sell_price(cost: float) -> float:
    return math.ceil(float(cost) * (1 + DEFAULT_MARKUP) * 100 - 1e-9) / 100


def paginate(items, n, per=PER_PAGE):
    total = max(1, math.ceil(len(items) / per))
    n = max(0, min(n, total - 1))
    return items[n * per:(n + 1) * per], n, total


def nav_row(prefix, n, total):
    row = []
    if n > 0:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"{prefix}:{n - 1}"))
    if total > 1:
        row.append(InlineKeyboardButton(f"{n + 1}/{total}", callback_data="noop"))
    if n < total - 1:
        row.append(InlineKeyboardButton("➡️", callback_data=f"{prefix}:{n + 1}"))
    return row


async def send(target, text, markup=None, edit=False):
    kw = dict(reply_markup=markup, parse_mode=HTML)
    if edit:
        return await target.edit_message_text(text, **kw)
    return await target.reply_text(text, **kw)


async def send_to(context, chat_id, text, markup=None):
    try:
        await context.bot.send_message(chat_id, text, parse_mode=HTML, reply_markup=markup)
    except Exception:
        log.warning("send_to %s failed", chat_id)


async def notify_admin(context, text):
    if ADMIN_TELEGRAM_ID:
        await send_to(context, ADMIN_TELEGRAM_ID, text)


async def get_games():
    if _cache["games"] and time.time() - _cache["ts"] < 300:
        return _cache["games"]
    try:
        games = await asyncio.to_thread(supplier.games)
    except SupplierError as e:
        log.error("games failed: %s", e)
        return _cache["games"]
    _cache.update(games=[g for g in games if g.get("packages")], ts=time.time())
    return _cache["games"]


async def find_game(slug):
    games = await get_games() or []
    return next((g for g in games if g["slug"] == slug), None)


# ============================================================
# DB helpers (sync - ហៅតាម asyncio.to_thread)
# ============================================================
def _txn(o):
    v = o.receipt_file_id or ""
    return v[len(TXN_PREFIX):] if v.startswith(TXN_PREFIX) else None


def create_order_row(s: dict, user) -> str:
    ref = "TG" + uuid.uuid4().hex[:14].upper()
    db = SessionLocal()
    try:
        db.add(ShopOrder(
            order_ref=ref, telegram_id=user.id, username=user.username or user.first_name,
            game_slug=s["slug"], game_name=s["game_name"],
            package_id=int(s["package_id"]), package_name=s["package_name"],
            player_id=s["player_id"], server_id=s["server_id"] or None,
            supplier_price=s["cost"], sell_price=s["price"], status="awaiting_payment",
        ))
        db.commit()
    finally:
        db.close()
    return ref


def set_txn(ref, txn):
    db = SessionLocal()
    try:
        db.query(ShopOrder).filter(ShopOrder.order_ref == ref).update(
            {"receipt_file_id": TXN_PREFIX + txn}, synchronize_session=False)
        db.commit()
    finally:
        db.close()


def set_status(ref, new, only_from=None) -> bool:
    db = SessionLocal()
    try:
        q = db.query(ShopOrder).filter(ShopOrder.order_ref == ref)
        if only_from:
            q = q.filter(ShopOrder.status == only_from)
        n = q.update({"status": new}, synchronize_session=False)
        db.commit()
        return n > 0
    finally:
        db.close()


def get_order(ref):
    db = SessionLocal()
    try:
        o = db.query(ShopOrder).filter(ShopOrder.order_ref == ref).first()
        if not o:
            return None
        return dict(id=o.id, ref=o.order_ref, tg=o.telegram_id, status=o.status, txn=_txn(o),
                    price=o.sell_price, game=o.game_name, package=o.package_name, created=o.created_at)
    finally:
        db.close()


def user_orders(tg):
    db = SessionLocal()
    try:
        rows = db.query(ShopOrder).filter(ShopOrder.telegram_id == tg).order_by(ShopOrder.id.desc()).limit(5).all()
        return [(o.order_ref, o.game_name, o.package_name, o.sell_price, o.status) for o in rows]
    finally:
        db.close()


def fulfil(ref):
    """បង់ប្រាក់ហើយ -> approve ទៅ supplier។ Atomic: មានតែម្ចាស់មួយដែលឈ្នះ។"""
    db = SessionLocal()
    try:
        n = db.query(ShopOrder).filter(
            ShopOrder.order_ref == ref, ShopOrder.status == "awaiting_payment"
        ).update({"status": "payment_submitted"}, synchronize_session=False)
        db.commit()
        if not n:
            return None
        o = db.query(ShopOrder).filter(ShopOrder.order_ref == ref).first()
        oid, tg = o.id, o.telegram_id
    finally:
        db.close()
    try:
        tg, ref, status, code = approve_order(oid)
        return dict(type="ok", tg=tg, ref=ref, status=status, code=code)
    except Exception as e:
        log.exception("approve failed %s", ref)
        return dict(type="fail", tg=tg, ref=ref, error=str(e)[:200])


def poll_payments():
    db = SessionLocal()
    try:
        rows = db.query(ShopOrder).filter(ShopOrder.status == "awaiting_payment") \
            .order_by(ShopOrder.id).limit(30).all()
        rows = [(o.order_ref, o.telegram_id, _txn(o), o.created_at) for o in rows]
    finally:
        db.close()

    events = []
    limit = timedelta(seconds=KHPAY_EXPIRES_IN + 120)
    for ref, tg, txn, created in rows:
        age = datetime.utcnow() - created
        if not txn:
            if age > timedelta(minutes=10):
                set_status(ref, "cancelled", only_from="awaiting_payment")
            continue
        if check_khpay_paid(txn):
            res = fulfil(ref)
            if res:
                events.append(res)
        elif age > limit:
            if set_status(ref, "expired", only_from="awaiting_payment"):
                events.append(dict(type="expired", tg=tg, ref=ref))
    return events


def retry_stuck():
    """order បង់ហើយ តែ supplier fail (ឧ. អស់លុយ) -> retry។ reference ដដែល = មិនកាត់ពីរដង។"""
    cutoff = datetime.utcnow() - timedelta(seconds=90)
    db = SessionLocal()
    try:
        rows = db.query(ShopOrder).filter(
            ShopOrder.status == "payment_submitted", ShopOrder.updated_at < cutoff
        ).limit(20).all()
        rows = [(o.id, o.order_ref, o.telegram_id) for o in rows]
    finally:
        db.close()

    events = []
    for oid, ref, tg in rows:
        if _fail_count.get(ref, 0) >= MAX_RETRY:
            continue
        try:
            tg, ref, status, code = approve_order(oid)
            _fail_count.pop(ref, None)
            events.append(dict(type="ok", tg=tg, ref=ref, status=status, code=code))
        except Exception as e:
            _fail_count[ref] = _fail_count.get(ref, 0) + 1
            events.append(dict(type="fail", tg=tg, ref=ref, error=str(e)[:200]))
    return events


# ============================================================
# Event dispatch (សារទៅអតិថិជន / Admin)
# ============================================================
async def handle_event(context, e):
    t, tg, ref = e["type"], e["tg"], e["ref"]
    if t == "ok":
        if e["status"] == "completed":
            await send_to(context, tg, f"✅ <b>បំពេញជោគជ័យ!</b>\n🧾 <code>{ref}</code>\nសូមអរគុណ 🎉")
        else:
            await send_to(context, tg, f"✅ <b>បានទទួលការបង់ប្រាក់</b>\n🧾 <code>{ref}</code>\n⚙️ កំពុងបញ្ចូលទៅគណនីអ្នក...")
    elif t == "fail":
        if ref not in _fail_notified:
            _fail_notified.add(ref)
            await send_to(context, tg, f"✅ បានទទួលការបង់ប្រាក់\n🧾 <code>{ref}</code>\n⏳ ការបញ្ចូលយឺតបន្តិច Admin កំពុងដោះស្រាយ។")
            await notify_admin(context, f"⚠️ <b>Paid but supplier failed</b>\n<code>{ref}</code>\n{esc(e['error'])}\nនឹង retry ស្វ័យប្រវត្តិ ឬចុច Approve ក្នុង admin panel។")
    elif t == "expired":
        await send_to(context, tg, f"⌛ QR ផុតកំណត់ <code>{ref}</code>\nវាយ /start ដើម្បីបញ្ជាទិញម្តងទៀត។")
    elif t == "final":
        if e["status"] == "completed":
            await send_to(context, tg, f"✅ <b>បំពេញជោគជ័យ!</b>\n🧾 <code>{ref}</code>\nសូមអរគុណ 🎉")
        else:
            await send_to(context, tg, f"↩️ ការបញ្ចូលមិនបានសម្រេច\n🧾 <code>{ref}</code>\nសូមទាក់ទង Admin ដើម្បីសងប្រាក់។")
            await notify_admin(context, f"↩️ <b>Supplier refunded</b> <code>{ref}</code> - ត្រូវសងអតិថិជនដោយដៃ។")


async def dispatch(context, events):
    for e in events or []:
        try:
            await handle_event(context, e)
        except Exception:
            log.exception("event failed")


async def job_payments(context: ContextTypes.DEFAULT_TYPE):
    try:
        await dispatch(context, await asyncio.to_thread(poll_payments))
    except Exception:
        log.exception("job_payments")


async def job_supplier(context: ContextTypes.DEFAULT_TYPE):
    try:
        changed = await asyncio.to_thread(refresh_processing_orders)
        events = [dict(type="final", tg=tg, ref=ref, status=st, code=code) for tg, ref, st, code in changed]
        events += await asyncio.to_thread(retry_stuck)
        await dispatch(context, events)
    except Exception:
        log.exception("job_supplier")


# ============================================================
# UI
# ============================================================
async def show_games(target, page=0, edit=False):
    games = await get_games()
    if not games:
        return await send(target, "❌ មិនអាចទាញបញ្ជីហ្គេមបានទេ សូមសាកល្បងម្តងទៀត។", edit=edit)
    chunk, page, total = paginate(games, page)
    kb = [[InlineKeyboardButton(f"🎮 {g['name']}", callback_data=f"g:{g['slug']}")] for g in chunk]
    nav = nav_row("gp", page, total)
    if nav:
        kb.append(nav)
    await send(target, f"👋 សួស្តី! សូមស្វាគមន៍មកកាន់ <b>{esc(SHOP_NAME)}</b>\n\n👇 សូមជ្រើសរើសហ្គេម៖",
               InlineKeyboardMarkup(kb), edit=edit)


async def show_packages(q, game, page=0):
    pkgs, page, total = paginate(game["packages"], page)
    kb = [[InlineKeyboardButton(f"💎 {p['name']} - ${sell_price(p['price']):.2f}",
                                callback_data=f"p:{p['package_id']}")] for p in pkgs]
    nav = nav_row("pk", page, total)
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="back")])
    await send(q, f"📦 <b>{esc(game['name'])}</b>\n\n👇 សូមជ្រើសរើសកញ្ចប់៖", InlineKeyboardMarkup(kb), edit=True)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await show_games(update.message)


async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await asyncio.to_thread(user_orders, update.effective_user.id)
    if not rows:
        return await update.message.reply_text("មិនទាន់មានការបញ្ជាទិញទេ។ វាយ /start")
    lines = [f"🧾 <code>{r}</code>\n{esc(g)} - {esc(p)} - ${price:.2f}\n{STATUS_KM.get(st, st)}"
             for r, g, p, price, st in rows]
    await update.message.reply_text("\n\n".join(lines), parse_mode=HTML)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    step = ud.get("step")
    text = (update.message.text or "").strip()
    if not step:
        return await update.message.reply_text("⚠️ សូមវាយ /start ដើម្បីចាប់ផ្តើម។")
    game = await find_game(ud.get("slug"))
    if not game:
        ud.clear()
        return await update.message.reply_text("❌ Session ផុតកំណត់។ វាយ /start ម្តងទៀត។")

    if step == "player_id":
        if not text or len(text) > 32:
            return await update.message.reply_text("⚠️ ID មិនត្រឹមត្រូវ (អតិបរមា 32 តួអក្សរ)។")
        ud["player_id"] = text
        if game.get("server_label"):
            ud["step"] = "server_id"
            return await update.message.reply_text(f"🌐 សូមផ្ញើ {esc(game['server_label'])}៖", parse_mode=HTML)
        ud["server_id"] = ""
        return await verify_and_confirm(update, ud, game)

    if step == "server_id":
        if not text or len(text) > 16:
            return await update.message.reply_text("⚠️ Server/Zone ID មិនត្រឹមត្រូវ (អតិបរមា 16 តួអក្សរ)។")
        ud["server_id"] = text
        return await verify_and_confirm(update, ud, game)


async def verify_and_confirm(update, ud, game):
    ud["step"] = None
    msg = await update.message.reply_text("⏳ កំពុងផ្ទៀងផ្ទាត់គណនី...")
    try:
        res = await asyncio.to_thread(supplier.check, game["slug"], ud["player_id"], ud["server_id"] or None)
    except SupplierError as e:
        log.warning("check failed: %s", e)
        res = {"result": "unknown"}
    result = res.get("result", "unknown")

    retry = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 វាយ ID ម្តងទៀត", callback_data="retry")]])
    if result == "invalid":
        return await msg.edit_text("❌ គណនីមិនត្រឹមត្រូវ។ សូមពិនិត្យ ID ហើយសាកល្បងម្តងទៀត។", reply_markup=retry)
    if result == "incomplete":
        return await msg.edit_text(f"⚠️ ព័ត៌មានមិនគ្រប់គ្រាន់។ {esc(res.get('message') or '')}",
                                   reply_markup=retry, parse_mode=HTML)

    nick = esc(res.get("nickname") or "-")
    warn = "\n⚠️ មិនអាចផ្ទៀងផ្ទាត់ឈ្មោះបានទេ សូមពិនិត្យ ID ឲ្យច្បាស់។" if result == "unknown" else ""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ត្រឹមត្រូវ - បង់ប្រាក់", callback_data="ok")],
        [InlineKeyboardButton("❌ ច្រឡំ / កែប្រែ", callback_data="retry")],
    ])
    await msg.edit_text(
        f"🧾 <b>សូមផ្ទៀងផ្ទាត់៖</b>\n\n"
        f"🎮 {esc(game['name'])}\n"
        f"📦 {esc(ud['package_name'])}\n"
        f"💰 <b>${ud['price']:.2f}</b>\n"
        f"👤 ID: <code>{esc(ud['player_id'])}</code>\n"
        f"🌐 Server: <code>{esc(ud['server_id'] or '-')}</code>\n"
        f"🏷 ឈ្មោះ: <b>{nick}</b>{warn}\n\n"
        f"⚠️ ពិនិត្យឲ្យច្បាស់មុនចុចបន្ត!",
        reply_markup=kb, parse_mode=HTML,
    )


def qr_to_photo(qr):
    if not qr:
        return None
    if qr.startswith("data:image"):
        bio = io.BytesIO(base64.b64decode(qr.split(",", 1)[1]))
        bio.name = "qr.png"
        return bio
    return qr


async def place_order(q, context):
    ud = context.user_data
    if not ud.get("package_id") or not ud.get("player_id") or ud.get("price") is None:
        return await q.edit_message_text("❌ Session ផុតកំណត់។ វាយ /start ម្តងទៀត។")
    snap = dict(ud)
    ud.clear()

    # កុំអោយអតិថិជនបង់ ពេល wallet supplier អស់លុយ
    try:
        me = await asyncio.to_thread(supplier.me)
        if float(me.get("balance", 0)) < snap["cost"]:
            await notify_admin(context, "⚠️ <b>Wallet khmer-topup អស់លុយ</b> សូមបញ្ចូលទឹកប្រាក់។")
            return await q.edit_message_text("❌ សេវាកម្មបណ្តោះអាសន្នមិនអាចប្រើបាន។ សូមទាក់ទង Admin។")
    except SupplierError as e:
        await notify_admin(context, f"⚠️ Supplier API error: {esc(str(e)[:200])}")
        return await q.edit_message_text("❌ សេវាកម្មមានបញ្ហា។ សូមសាកល្បងម្តងទៀតពេលក្រោយ។")

    await q.edit_message_text("⏳ កំពុងបង្កើត QR...")
    ref = await asyncio.to_thread(create_order_row, snap, q.from_user)
    qr = await asyncio.to_thread(create_khpay_qr, ref, snap["price"])
    if not qr.get("success"):
        log.error("khpay failed: %s", qr.get("message"))
        await asyncio.to_thread(set_status, ref, "cancelled")
        await notify_admin(context, f"⚠️ KHPay error: {esc(str(qr.get('message'))[:200])}")
        return await q.edit_message_text("❌ មិនអាចបង្កើត QR បានទេ។ សូមសាកល្បងម្តងទៀត។")
    await asyncio.to_thread(set_txn, ref, qr["transaction_id"])

    mins = max(1, KHPAY_EXPIRES_IN // 60)
    caption = (f"💳 <b>សូមស្កេន QR ដើម្បីបង់ប្រាក់</b>\n\n"
               f"🧾 <code>{ref}</code>\n🎮 {esc(snap['game_name'])} - {esc(snap['package_name'])}\n"
               f"💰 <b>${snap['price']:.2f}</b>\n⏱ ផុតកំណត់ក្នុង {mins} នាទី\n\n"
               f"បង់ហើយ bot នឹងបញ្ចូលស្វ័យប្រវត្តិ។")
    rows = []
    if qr.get("payment_url"):
        rows.append([InlineKeyboardButton("💳 បើកទំព័របង់ប្រាក់", url=qr["payment_url"])])
    rows.append([InlineKeyboardButton("🔄 ឆែកការបង់ប្រាក់", callback_data=f"chk:{ref}")])
    rows.append([InlineKeyboardButton("🚫 បោះបង់", callback_data=f"cx:{ref}")])
    markup = InlineKeyboardMarkup(rows)

    try:
        await q.message.delete()
    except Exception:
        pass
    chat_id = q.message.chat_id
    try:
        photo = qr_to_photo(qr.get("qr_url"))
        if photo:
            return await context.bot.send_photo(chat_id, photo, caption=caption, parse_mode=HTML, reply_markup=markup)
    except Exception:
        log.exception("send_photo failed")
    await send_to(context, chat_id, caption + "\n\n(មិនអាចបង្ហាញ QR - ប្រើប៊ូតុងខាងលើ)", markup)


async def check_payment(q, context, ref):
    o = await asyncio.to_thread(get_order, ref)
    if not o or o["tg"] != q.from_user.id:
        return await q.answer("រកមិនឃើញ order", show_alert=True)
    if o["status"] != "awaiting_payment":
        return await q.answer(STATUS_KM.get(o["status"], o["status"]), show_alert=True)
    paid = await asyncio.to_thread(check_khpay_paid, o["txn"]) if o["txn"] else False
    if not paid:
        return await q.answer("⏳ មិនទាន់ទទួលបានការបង់ប្រាក់។ សូមរង់ចាំបន្តិច។", show_alert=True)
    await q.answer("✅ បានទទួលការបង់ប្រាក់")
    res = await asyncio.to_thread(fulfil, ref)
    if res:
        await dispatch(context, [res])


async def cancel_order(q, context, ref):
    o = await asyncio.to_thread(get_order, ref)
    if not o or o["tg"] != q.from_user.id:
        return await q.answer("រកមិនឃើញ order", show_alert=True)
    if o["status"] != "awaiting_payment":
        return await q.answer(STATUS_KM.get(o["status"], o["status"]), show_alert=True)
    if o["txn"] and await asyncio.to_thread(check_khpay_paid, o["txn"]):
        return await check_payment(q, context, ref)  # បង់ហើយ មិនអាចបោះបង់
    await asyncio.to_thread(set_status, ref, "cancelled", "awaiting_payment")
    await q.answer("🚫 បានបោះបង់")
    try:
        await q.message.delete()
    except Exception:
        pass
    await send_to(context, q.message.chat_id, "🚫 បានបោះបង់។ វាយ /start ដើម្បីបញ្ជាទិញម្តងទៀត។")


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    ud = context.user_data

    if data.startswith("chk:"):
        return await check_payment(q, context, data[4:])
    if data.startswith("cx:"):
        return await cancel_order(q, context, data[3:])

    await q.answer()
    expired = "❌ Session ផុតកំណត់។ វាយ /start ម្តងទៀត។"

    if data == "noop":
        return
    if data == "back":
        ud.clear()
        return await show_games(q, 0, edit=True)
    if data.startswith("gp:"):
        return await show_games(q, int(data[3:]), edit=True)

    if data.startswith("g:"):
        game = await find_game(data[2:])
        if not game:
            return await q.edit_message_text(expired)
        ud.clear()
        ud.update(slug=game["slug"], game_name=game["name"])
        return await show_packages(q, game, 0)

    if data.startswith("pk:"):
        game = await find_game(ud.get("slug"))
        if not game:
            return await q.edit_message_text(expired)
        return await show_packages(q, game, int(data[3:]))

    if data.startswith("p:"):
        game = await find_game(ud.get("slug"))
        pkg = next((p for p in (game or {}).get("packages", []) if str(p["package_id"]) == data[2:]), None)
        if not pkg:
            return await q.edit_message_text(expired)
        ud.update(package_id=pkg["package_id"], package_name=pkg["name"],
                  cost=float(pkg["price"]), price=sell_price(pkg["price"]), step="player_id")
        back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="back")]])
        return await send(q, f"🆔 សូមផ្ញើ <b>{esc(game.get('id_label') or 'Player ID')}</b> របស់អ្នក៖", back, edit=True)

    if data == "retry":
        ud["step"] = "player_id"
        ud.pop("server_id", None)
        return await q.edit_message_text("🆔 សូមវាយ Player ID ថ្មីម្តងទៀត៖")

    if data == "ok":
        return await place_order(q, context)


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.error("Unhandled error: %s", context.error, exc_info=context.error)


# ============================================================
# Entry point (main.py ហៅ build_bot())
# ============================================================
def build_bot() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("orders", cmd_orders))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)

    if app.job_queue is None:
        raise RuntimeError("Install: pip install 'python-telegram-bot[job-queue]'")
    app.job_queue.run_repeating(job_payments, interval=8, first=10)
    app.job_queue.run_repeating(job_supplier, interval=30, first=20)
    return app