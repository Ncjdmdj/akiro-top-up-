import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from app.db import get_db_connection

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
KHMER_TOPUP_BASE_URL = os.getenv("KHMER_TOPUP_BASE_URL", "https://khmer-topup.com/api/v1")
KHMER_TOPUP_API_KEY = os.getenv("KHMER_TOPUP_API_KEY")

user_selection = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎮 Mobile Legends", callback_data="game_mobile-legends")],
        [InlineKeyboardButton("🎮 PUBG Mobile", callback_data="game_pubg-mobile")],
        [InlineKeyboardButton("🎮 Free Fire", callback_data="game_free-fire")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 សួស្តី! សូមស្វាគមន៍មកកាន់ប្រព័ន្ធបំពេញទឹកប្រាក់ហ្គេមស្វ័យប្រវត្ត (GameZone Topup)。\n\n"
        "👇 សូមជ្រើសរើសហ្គេមដែលអ្នកចង់បំពេញ៖",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data

    if data.startswith("game_"):
        game_slug = data.split("_")[1]
        user_selection[user_id] = {"slug": game_slug, "step": "choose_product"}
        
        # គំរូ Package ID យោងតាម Docs (អាចហៅពី /games មកបង្ហាញបាន បើចង់បានស្វ័យប្រវត្ត)
        keyboard = [
            [InlineKeyboardButton("💎 55 Diamonds ($0.78)", callback_data="prod_268")],
            [InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="back_to_games")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text=f"📦 អ្នកបានជ្រើសរើសហ្គេម៖ **{game_slug.upper()}**\n\n👇 សូមជ្រើសរើសកញ្ចប់ទឹកប្រាក់៖", 
            reply_markup=reply_markup, 
            parse_mode="Markdown"
        )

    elif data.startswith("prod_"):
        package_id = int(data.replace("prod_", ""))
        if user_id in user_selection:
            user_selection[user_id]["package_id"] = package_id
            user_selection[user_id]["step"] = "wait_for_userid"
        
        await query.edit_message_text(
            text="✍️ សូមផ្ញើលេខ **User ID** របស់អ្នកមកទីនេះជាអត្ថបទ (ឧ. `12345678`)៖",
            parse_mode="Markdown"
        )

    elif data == "back_to_games":
        keyboard = [
            [InlineKeyboardButton("🎮 Mobile Legends", callback_data="game_mobile-legends")],
            [InlineKeyboardButton("🎮 PUBG Mobile", callback_data="game_pubg-mobile")],
            [InlineKeyboardButton("🎮 Free Fire", callback_data="game_free-fire")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="👇 សូមជ្រើសរើសហ្គេមដែលអ្នកចង់បំពេញទឹកប្រាក់៖", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if user_id in user_selection and user_selection[user_id].get("step") == "wait_for_userid":
        sel = user_selection[user_id]
        package_id = sel["package_id"]
        player_id = text

        # ត្រៀម Payload ផ្ញើទៅកាន់ Endpoint /orders តាម Docs ផ្លូវការ
        payload = {
            "package_id": package_id,
            "player_id": player_id,
            "server_id": "1234", # អាចកែសម្រួលសួរយក Zone ID បន្ថែមបើហ្គេមនោះទាមទារ
            "reference": f"order-{user_id}-{int(requests.utils.datetime.datetime.now().timestamp())}"
        }

        headers = {
            "Authorization": f"Bearer {KHMER_TOPUP_API_KEY}",
            "Content-Type": "application/json"
        }

        try:
            order_api_url = f"{KHMER_TOPUP_BASE_URL}/orders"
            response = requests.post(order_api_url, json=payload, headers=headers)
            res_data = response.json()

            # រក្សាទុកចូល Supabase Table orders
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO orders (game_id, user_id, product_code, status, response_data)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (sel["slug"], player_id, str(package_id), res_data.get("status", "pending"), str(res_data))
            )
            conn.commit()
            cur.close()
            conn.close()

            await update.message.reply_text(
                f"✅ ការបញ្ជាទិញបានបញ្ជូនទៅកាន់ Khmer Topup ដោយជោគជ័យ!\n\nព័ត៌មានលម្អិត៖\n```json\n{res_data}\n```", 
                parse_mode="Markdown"
            )
            del user_selection[user_id]

        except Exception as e:
            await update.message.reply_text(f"❌ មានបញ្ហាកើតឡើង៖ {str(e)}")
    else:
        await update.message.reply_text("⚠️ សូមចាប់ផ្តើមជាថ្មីដោយវាយពាក្យបញ្ជា `/start` ។")

def create_bot_app():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("BOT_TOKEN is missing!")
        return None
        
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    return app