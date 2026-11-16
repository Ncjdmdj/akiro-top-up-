from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from app.Khpay import create_payway_transaction

async def checkout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # ឧទាហរណ៍តម្លៃ និង លេខ Reference នៃការបញ្ជាទិញ
    order_ref = "INV-20261115-001"
    amount = 5.00 # ទឹកប្រាក់ជា USD
    user_phone = "012345678" # លេខទូរស័ព្ទអតិថិជន (បើមាន)

    # ហៅទៅកាន់ function បង្កើត PayWay Transaction
    result = create_payway_transaction(order_ref, amount, user_phone)

    if result["success"]:
        checkout_url = result["checkout_url"]
        
        # បង្កើត Inline Button ឱ្យអតិថិជនចុចបង់ប្រាក់
        keyboard = [
            [InlineKeyboardButton("💳 បង់ប្រាក់តាម ABA PayWay", url=checkout_url)],
            [InlineKeyboardButton("🔄 ឆែកស្ថានភាពបង់ប្រាក់", callback_data=f"check_{order_ref}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=(
                f"🛒 **វិក្កយបត្រ៖** `{order_ref}`\n"
                f"💰 **តម្លៃសរុប៖** `${amount:.2f}`\n\n"
                f"សូមចុចប៊ូតុងด้านក្រោមដើម្បីទូទាត់ប្រាក់តាមរយៈ ABA Payway យ៉ាងមានសុវត្ថិភាព!"
            ),
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(text=f"❌ មានបញ្ហាក្នុងการបង្កើតវិក្កយបត្រ៖ {result['message']}")