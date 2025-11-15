import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# تنظیمات لاگ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN', '8437924316:AAFysR4_YGYr2HxhxLHWUVAJJdNHSXxNXns')

async def start(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("💄 خدمات زیبایی", callback_data="beauty")],
        [InlineKeyboardButton("📅 رزرو نوبت", callback_data="booking")],
        [InlineKeyboardButton("👨‍⚕️ پزشکان ما", callback_data="doctors")],
        [InlineKeyboardButton("🔐 پنل مدیریت", callback_data="admin")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🏠 **به کلینیک زیبایی گلوریا خوش آمدید!**\n\n"
        "✅ ربات آنلاین و فعال\n"
        "📞 پشتیبانی: 09190432181\n\n"
        "لطفاً گزینه مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def handle_query(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    if query.data == "admin":
        await query.edit_message_text(
            "🔐 **پنل مدیریت**\n\n"
            "برای دسترسی با پشتیبانی تماس بگیرید:\n"
            "📞 09190432181\n\n"
            "یا از منوی اصلی استفاده کنید:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 منوی اصلی", callback_data="main")]
            ])
        )
    elif query.data == "main":
        await start(update, context)
    else:
        await query.edit_message_text(
            "✅ **سرویس فعال**\n\n"
            "این بخش به زودی راه‌اندازی می‌شود.\n"
            "📞 پشتیبانی: 09190432181\n\n"
            "بازگشت به منوی اصلی:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 منوی اصلی", callback_data="main")]
            ])
        )

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, 
                                         lambda u, c: u.message.reply_text("لطفاً از منوی اصلی استفاده کنید 🏠")))
    
    logger.info("🤖 Bot is starting on Render...")
    application.run_polling()

if __name__ == '__main__':
    main()
