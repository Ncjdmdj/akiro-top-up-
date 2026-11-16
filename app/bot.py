import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# ហៅទាញយកតម្លៃពីဖိုင် .env
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")

# Supabase Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL")

# Khmer Topup API Configuration
KHMER_TOPUP_BASE_URL = os.getenv("KHMER_TOPUP_BASE_URL", "https://khmer-topup.com/api/v1")
KHMER_TOPUP_API_KEY = os.getenv("KHMER_TOPUP_API_KEY")

# កែសម្រួលត្រង់ចំណុចនេះឱ្យត្រូវស្តង់ដារ Python
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# ទិន្នន័យបណ្តោះអាសន្នសម្រាប់តាមដានការជ្រើសរើសរបស់អតិថិជន
user_selection = {}

# ពាក្យបញ្ជា /start ជាមួយ Inline Button ជ្រើសរើសហ្គេម
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎮 Mobile Legends (MLBB)", callback_data="game_mlbb")],
        [InlineKeyboardButton("🎮 PUBG Mobile", callback_data="game_pubg")],
        [InlineKeyboardButton("🎮 Free Fire", callback_data="game_ff")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 សួស្តី! សូមស្វាគមន៍មកកាន់ប្រព័ន្ធបំពេញទឹកប្រាក់ហ្គេមស្វ័យប្រវត្ត (GameZone Topup)។\n\n"
        "👇 សូមជ្រើសរើសហ្គេមដែលអ្នកចង់បំពេញ៖",
        reply_markup=reply_markup
    )

# គ្រប់គ្រងការចុចលើ Inline Keyboard
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
            text="✍️ សូមផ្ញើលេខ **User ID** (និង Zone ID បើមាន) របស់អ្នកមកទីនេះជាអត្ថបទ។\n\nឧទាហរណ៍៖ `12345678 (1234)`",
            parse_mode="Markdown"
        )

    elif data == "confirm_order":
        if user_id in user_selection:
            sel = user_selection[user_id]
            game_id = sel["game_id"]
            game_user_id = sel["game_user_id"]
            product_code = sel["product_code"]

            payload = {
                "api_key": KHMER_TOPUP_API_KEY,
                "game_id": game_id,
                "user_id": game_user_id,
                "product_code": product_code
            }

            try:
                # 1. បាញ់សំណើទៅ Khmer Topup API Endpoint (/order)
                order_api_url = f"{KHMER_TOPUP_BASE_URL}/order"
                response = requests.post(order_api_url, json=payload)
                res_data = response.json()

                # 2. រក្សាទុកចូល Supabase Table `orders`
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO orders (game_id, user_id, product_code, status, response_data)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (game_id, game_user_id, product_code, "pending", str(res_data))
                )
                conn.commit()
                cur.close()
                conn.close()

                await query.edit_message_text(
                    text=f"✅ ការបញ្ជាទិញបានបញ្ជូនទៅកាន់ប្រព័ន្ធដោយជោគជ័យ!\n\nព័ត៌មានលម្អិត៖\n```json\n{res_data}\n```", 
                    parse_mode="Markdown"
                )
                del user_selection[user_id]

            except Exception as e:
                await query.edit_message_text(text=f"❌ មានបញ្ហាកើតឡើង៖ {str(e)}")

    elif data == "cancel_order":
        if user_id in user_selection:
            user_selection[user_id]["step"] = "wait_for_userid"
        await query.edit_message_text(text="✍️ សូមវាយបញ្ចូល User ID ថ្មីរបស់អ្នកមកម្តងទៀត៖")

    elif data == "back_to_games":
        keyboard = [
            [InlineKeyboardButton("🎮 Mobile Legends (MLBB)", callback_data="game_mlbb")],
            [InlineKeyboardButton("🎮 PUBG Mobile", callback_data="game_pubg")],
            [InlineKeyboardButton("🎮 Free Fire", callback_data="game_ff")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="👇 សូមជ្រើសរើសហ្គេមដែលអ្នកចង់បំពេញទឹកប្រាក់៖", reply_markup=reply_markup)

# ទទួល User ID ជាអត្ថបទ និងផ្ទៀងផ្ទាត់មុនបញ្ជូន
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if user_id in user_selection and user_selection[user_id].get("step") == "wait_for_userid":
        user_selection[user_id]["game_user_id"] = text
        game_id = user_selection[user_id]["game_id"]
        
        ign_name = "RinGaming (គំរូឈ្មោះ)"

        keyboard = [
            [InlineKeyboardButton("✅ ត្រឹមត្រូវ (Confirm)", callback_data="confirm_order")],
            [InlineKeyboardButton("❌ ច្រឡំ / កែប្រែ (Cancel)", callback_data="cancel_order")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🧾 **សូមផ្ទៀងផ្ទាត់ព័ត៌មានរបស់អ្នក៖**\n\n"
            f"🎮 Game: `{game_id.upper()}`\n"
            f"👤 Player ID: `{text}`\n"
            f"👤 ឈ្មោះក្នុងហ្គេម (IGN): **{ign_name}**\n\n"
            f"⚠️ សូមពិនិត្យឱ្យបានច្បាស់លាស់ មុនពេលចុចបញ្ជាក់!",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⚠️ សូមចាប់ផ្តើមជាថ្មីដោយវាយពាក្យបញ្ជា `/start` ។")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("🤖 GameZone Topup Telegram Bot is running...")
    app.run_polling()