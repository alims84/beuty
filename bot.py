import os
import logging
from telegram.ext import Updater, CommandHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN', '8437924316:AAFysR4_YGYr2HxhxLHWUVAJJdNHSXxNXns')

def start(update, context):
    update.message.reply_text(
        "✅ **ربات کلینیک گلوریا فعال شد!**\n\n"
        "🏠 به کلینیک زیبایی گلوریا خوش آمدید\n"
        "📞 پشتیبانی: 09190432181\n\n"
        "سرویس آنلاین و آماده به کار!"
    )

def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    logger.info("🤖 Bot starting...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
