import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from app.db import get_db_connection

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")

# ดึง URL និង API Key ពី Environment Variables របស់ Render
KHMER_TOPUP_API_URL = os.getenv("KHMER_TOPUP_API_URL", "https://khmer-topup.com/api/v1/order")
KHMER_TOPUP_API_KEY = os.getenv("KHMER_TOPUP_API_KEY")

user_selection = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎮 Mobile Legends (MLBB)", callback_data="game_mlbb")],
        [InlineKeyboardButton("🎮 PUBG Mobile", callback_data="game_pubg")],
        [InlineKeyboardButton("🎮 Free Fire", callback_data="game_ff")]
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
        game_id = data.split("_")[1]
        user_selection[user_id] = {"game_id": game_id, "step": "choose_product"}
        
        keyboard = [
            [InlineKeyboardButton("💎 86 Diamonds ($1.00)", callback_data="prod_86_diamonds")],
            [InlineKeyboardButton("💎 172 Diamonds ($2.00)", callback_data="prod_172_diamonds")],
            [InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="back_to_games")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text=f"📦 អ្នកបានជ្រើសរើសហ្គេម៖ **{game_id.upper()}**\n\n👇 សូមជ្រើសរើសកញ្ចប់ទឹកប្រាក់៖", 
            reply_markup=reply_markup, 
            parse_mode="Markdown"
        )

    elif data.startswith("prod_"):
        product_code = data.replace("prod_", "")
        if user_id in user_selection:
            user_selection[user_id]["product_code"] = product_code
            user_selection[user_id]["step"] = "wait_for_userid"
        
        await query.edit_message_text(
            text="✍️ សូមផ្ញើលេខ **User ID** (និង Zone ID បើមាន) របស់អ្នកមកទីនេះជាអត្ថបទ。\n\nឧទាហរណ៍៖ `12345678 (1234)`",
            parse_mode="Markdown"
        )

    elif data == "back_to_games":
        keyboard = [
            [InlineKeyboardButton("🎮 Mobile Legends (MLBB)", callback_data="game_mlbb")],
            [InlineKeyboardButton("🎮 PUBG Mobile", callback_data="game_pubg")],
            [InlineKeyboardButton("🎮 Free Fire", callback_data="game_ff")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="👇 សូមជ្រើសរើសហ្គេមដែលអ្នកចង់បំពេញទឹកប្រាក់៖", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if user_id in user_selection and user_selection[user_id].get("step") == "wait_for_userid":
        user_selection[user_id]["game_user_id"] = text
        sel = user_selection[user_id]
        game_id = sel["game_id"]
        product_code = sel["product_code"]

        payload = {
            "api_key": KHMER_TOPUP_API_KEY,
            "game_id": game_id,
            "user_id": text,
            "product_code": product_code
        }

        try:
            # ផ្ញើសំណើទៅកាន់ API Endpoint ដែលបានកំណត់
            response = requests.post(KHMER_TOPUP_API_URL, json=payload)
            res_data = response.json()

            # រក្សាទុកចូល Supabase
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO orders (game_id, user_id, product_code, status, response_data)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (game_id, text, product_code, "pending", str(res_data))
            )
            conn.commit()
            cur.close()
            conn.close()

            await update.message.reply_text(
                f"✅ ការបញ្ជាទិញបានបញ្ជូនទៅកាន់ប្រព័ន្ធដោយជោគជ័យ!\n\nព័ត៌មានលម្អិត៖\n```json\n{res_data}\n```", 
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