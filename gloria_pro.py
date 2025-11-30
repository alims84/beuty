# -*- coding: utf-8 -*-
"""
Gloria Clinic Bot - PRO (Full)

نسخه کامل با:
- پنل ادمین + CRM
- رزرو نوبت + یادآوری + Recall
- مشاوره پوستی هوشمند (روتین صبح/شب)
- پرداخت آفلاین (کارت به کارت)
- پرداخت آنلاین (زرین‌پال - حالت سندباکس/تستی)
- منوی شیشه‌ای پایین (ReplyKeyboard) + منوهای Inline
- سازگار با Render (Webhook) و لوکال (Polling)
"""

import logging
import os
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List

import requests
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    JobQueue,
    filters,
)

# ======================= تنظیمات اصلی =======================

CLINIC_NAME = "Gloria Clinic"

# توکن ربات
DEFAULT_BOT_TOKEN = "8437924316:AAFysR4_YGYr2HxhxLHWUVAJJdNHSXxNXns"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", DEFAULT_BOT_TOKEN).strip()
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN تنظیم نشده است.")

WEBHOOK_PATH = f"webhook/{TELEGRAM_BOT_TOKEN.split(':')[0]}"

DB_PATH = "clinic_pro.db"

# کارت برای پرداخت آفلاین
OFFLINE_CARD_NUMBER = "6037-9917-1234-5678"
OFFLINE_CARD_OWNER = "Gloria Clinic"

# ادمین ثابت
ADMIN_LOGIN_USERNAME = "admin"
ADMIN_LOGIN_PASSWORD = "12345"

# زرین‌پال (سندباکس)
# مرچنت تستی تو:
DEFAULT_ZARINPAL_MERCHANT_ID = "120c505c-81e1-41e2-8138-63b819e324ae"
ZARINPAL_MERCHANT_ID = os.getenv(
    "ZARINPAL_MERCHANT_ID", DEFAULT_ZARINPAL_MERCHANT_ID
).strip()

ZARINPAL_SANDBOX = True
ZARINPAL_REQUEST_URL = (
    "https://sandbox.zarinpal.com/pg/rest/WebGate/PaymentRequest.json"
    if ZARINPAL_SANDBOX
    else "https://api.zarinpal.com/pg/v4/payment/request.json"
)
ZARINPAL_STARTPAY_URL = (
    "https://sandbox.zarinpal.com/pg/StartPay/{Authority}"
    if ZARINPAL_SANDBOX
    else "https://www.zarinpal.com/pg/StartPay/{Authority}"
)

# Referral
REFERRAL_BONUS_POINTS = 10
VIP_THRESHOLD_POINTS = 50

# دکتر‌ها و زمان‌ها
DOCTORS = ["دکتر احمدی", "دکتر رضایی", "دکتر محمدی"]
TIME_SLOTS = ["10:00", "11:00", "12:00", "14:00", "15:00", "16:00", "17:00"]

# ------------- وضعیت‌ها (state keys) -------------

STATE_AWAITING_ADMIN_USERNAME = "awaiting_admin_username"
STATE_AWAITING_ADMIN_PASSWORD = "awaiting_admin_password"

STATE_AWAITING_RECEIPT_PHOTO = "awaiting_receipt_photo"

STATE_AWAITING_ALLERGIES = "awaiting_allergies"
STATE_AWAITING_IMPORTANT_NOTES = "awaiting_important_notes"

STATE_AWAITING_REFERRAL_CODE = "awaiting_referral_code"

STATE_AWAITING_BROADCAST_TEXT = "awaiting_broadcast_text"

# ------------- مشاوره پوستی -------------

SKIN_TYPES = {
    "dry": "خشک",
    "oily": "چرب",
    "combination": "مختلط",
    "normal": "نرمال",
    "sensitive": "حساس",
}

SKIN_CONCERNS = {
    "acne": "جوش فعال / آکنه",
    "pigmentation": "لک و تیرگی",
    "wrinkles": "چروک و خطوط ریز",
    "redness": "قرمزی و التهاب",
    "pores": "منافذ باز",
    "scars": "اسکار و فرورفتگی",
}

SENSITIVITY_LEVELS = {
    "low": "کم",
    "medium": "متوسط",
    "high": "زیاد",
}

# چند ترکیب نمونه با پاسخ کاملاً اختصاصی
TREATMENT_SUGGESTIONS = {
    ("oily", "acne", "high"): {
        "title": "پوست چرب + آکنه فعال + حساسیت زیاد",
        "routine_morning": [
            "ژل شستشوی ملایم مخصوص پوست چرب و حساس (بدون سولفات)",
            "اسپری آب حرارتی یا تونر بدون الکل",
            "سرم نیاسینامید ۵٪",
            "کرم ضدآفتاب مینرال SPF 50 مخصوص پوست حساس",
        ],
        "routine_night": [
            "شستشوی ملایم",
            "کرم ضدالتهاب (آلوئه‌ورا، پانتنول، بیزابولول)",
            "هفته‌ای ۲ شب در صورت تحمل، سرم حاوی BHA با درصد پایین",
        ],
        "clinic_treatments": [
            "درمان آکنه با نوردرمانی/لیزر ملایم، طبق نظر پزشک",
            "پاکسازی حرفه‌ای با فاصله زمانی مناسب و بسیار ملایم",
        ],
        "notes": "در این نوع پوست، از محصولات الکل‌دار، اسکراب دانه‌دار و شست‌وشوی شدید پرهیز کنید.",
    },
    ("dry", "wrinkles", "low"): {
        "title": "پوست خشک + خطوط ریز + حساسیت کم",
        "routine_morning": [
            "شیرپاک‌کن یا فوم بسیار ملایم",
            "سرم هیالورونیک اسید + پپتید",
            "کرم مرطوب‌کننده غنی (حاوی سرامید)",
            "کرم ضدآفتاب SPF 50 با فیلترهای ترکیبی",
        ],
        "routine_night": [
            "شستشوی ملایم",
            "کرم/سرم حاوی رتینول با دوز پایین (با مشورت پزشک)",
            "کرم مغذی شب (حاوی روغن‌های سبک و سرامید)",
        ],
        "clinic_treatments": [
            "مزوتراپی آبرسان",
            "درمان‌های جوانسازی غیرتهاجمی مثل میکرونیدلینگ ملایم یا RF فرکشنال",
        ],
        "notes": "شست‌وشوی بیش از حد و آب داغ را محدود کنید و حتماً بعد شست‌وشو تا چند دقیقه کرم بزنید.",
    },
}

# مراقبت بعد درمان
POST_CARE_MESSAGES = {
    "Botox": "مراقبت‌های بعد از بوتاکس:\n- تا ۴ ساعت دراز نکشید.\n- از ماساژ ناحیه تزریق خودداری کنید.\n- در صورت سردرد یا علائم غیرعادی با پزشک مشورت کنید.",
    "Filler": "مراقبت‌های بعد از فیلر:\n- استفاده از کمپرس سرد ملایم در ۲۴ ساعت اول.\n- خودداری از فشار و ماساژ شدید ناحیه تزریق.\n- در صورت تورم شدید، با پزشک تماس بگیرید.",
    "Laser": "مراقبت‌های بعد از لیزر:\n- تا ۴۸ ساعت از آفتاب مستقیم، سونا و استخر پرهیز کنید.\n- استفاده از کرم ترمیم‌کننده طبق نسخه پزشک.\n- کرم ضدآفتاب هر ۲–۳ ساعت تمدید شود.",
    "Meso": "مراقبت‌های بعد از مزوتراپی:\n- تا ۲۴ ساعت از شستشوی ناحیه تزریق خودداری کنید.\n- از محصولات تحریک‌کننده (اسیدها، رتینول) برای چند روز استفاده نکنید.\n- در صورت قرمزی یا التهاب شدید با پزشک مشورت کنید.",
}

# برای Recall دوره‌ای
TREATMENT_RECALL_DAYS = {
    "Botox": 180,
    "Filler": 270,
    "Laser": 45,
    "Meso": 90,
}

# ------------- Logging -------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================= دیتابیس =======================


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS clinics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            city TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER UNIQUE,
            full_name TEXT,
            phone_number TEXT,
            is_admin INTEGER DEFAULT 0,
            tags TEXT DEFAULT '',
            clinic_id INTEGER,
            allergies TEXT DEFAULT '',
            important_notes TEXT DEFAULT '',
            referral_code TEXT UNIQUE,
            referred_by_user_id INTEGER,
            referral_points INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            clinic_id INTEGER,
            service_name TEXT,
            doctor_name TEXT,
            date TEXT,
            time TEXT,
            status TEXT DEFAULT 'reserved',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            recall_date TEXT,
            recall_sent INTEGER DEFAULT 0
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            appointment_id INTEGER,
            amount INTEGER,
            method TEXT,
            status TEXT,
            gateway TEXT,
            authority TEXT,
            card_last4 TEXT,
            tracking_code TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            skin_type_key TEXT,
            skin_concern_key TEXT,
            sensitivity_key TEXT,
            suggestion_title TEXT,
            suggestion_text TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            package_code TEXT,
            title TEXT,
            total_sessions INTEGER,
            used_sessions INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            note_text TEXT,
            created_by_admin_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS user_states (
            user_id INTEGER PRIMARY KEY,
            state_json TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def get_or_create_user(chat_id: int, full_name: str = "") -> sqlite3.Row:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    if row:
        conn.close()
        return row
    c.execute(
        "INSERT INTO users (chat_id, full_name) VALUES (?, ?)", (chat_id, full_name)
    )
    conn.commit()
    c.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    conn.close()
    return row


def is_admin(chat_id: int) -> bool:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT is_admin FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row["is_admin"])


def set_user_state(chat_id: int, key: str, value: Any):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    user_id = row["id"]
    c.execute("SELECT state_json FROM user_states WHERE user_id = ?", (user_id,))
    sr = c.fetchone()
    if sr and sr["state_json"]:
        data = json.loads(sr["state_json"])
    else:
        data = {}
    data[key] = value
    c.execute(
        "INSERT OR REPLACE INTO user_states (user_id, state_json) VALUES (?, ?)",
        (user_id, json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def get_user_state(chat_id: int, key: str, default: Any = None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return default
    user_id = row["id"]
    c.execute("SELECT state_json FROM user_states WHERE user_id = ?", (user_id,))
    sr = c.fetchone()
    conn.close()
    if not sr or not sr["state_json"]:
        return default
    data = json.loads(sr["state_json"])
    return data.get(key, default)


def clear_user_state(chat_id: int, key: Optional[str] = None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    user_id = row["id"]
    c.execute("SELECT state_json FROM user_states WHERE user_id = ?", (user_id,))
    sr = c.fetchone()
    if not sr or not sr["state_json"]:
        conn.close()
        return
    data = json.loads(sr["state_json"])
    if key is None:
        data = {}
    else:
        data.pop(key, None)
    c.execute(
        "UPDATE user_states SET state_json = ? WHERE user_id = ?",
        (json.dumps(data, ensure_ascii=False), user_id),
    )
    conn.commit()
    conn.close()


def get_all_users() -> List[sqlite3.Row]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    rows = c.fetchall()
    conn.close()
    return rows


# ======================= کیبوردها =======================


def build_reply_keyboard(is_admin_user: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("🗓 رزرو نوبت"), KeyboardButton("💳 پرداخت")],
        [KeyboardButton("🧴 مشاوره پوستی"), KeyboardButton("👤 پروفایل من")],
        [KeyboardButton("📣 لینک من / کد معرف")],
    ]
    if is_admin_user:
        rows.append([KeyboardButton("🛠 پنل مدیریت")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def main_menu_inline(is_admin_user: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🗓 رزرو نوبت", callback_data="menu_reserve")],
        [InlineKeyboardButton("💳 پرداخت", callback_data="menu_payment")],
        [InlineKeyboardButton("🧴 مشاوره پوستی", callback_data="menu_consult")],
        [InlineKeyboardButton("📦 پکیج‌ها", callback_data="menu_packages")],
        [InlineKeyboardButton("👤 پروفایل من", callback_data="menu_profile")],
        [InlineKeyboardButton("📣 لینک من / کد معرف", callback_data="menu_referral")],
    ]
    if is_admin_user:
        buttons.append([InlineKeyboardButton("🛠 پنل مدیریت", callback_data="menu_admin")])
    return InlineKeyboardMarkup(buttons)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📊 داشبورد", callback_data="admin_dashboard")],
        [InlineKeyboardButton("👥 کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("🗓 نوبت‌ها", callback_data="admin_appointments")],
        [InlineKeyboardButton("💳 پرداخت‌ها", callback_data="admin_payments")],
        [InlineKeyboardButton("🧴 مشاوره‌ها", callback_data="admin_consults")],
        [InlineKeyboardButton("📦 پکیج‌ها", callback_data="admin_packages")],
        [InlineKeyboardButton("📨 پیام گروهی", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def clinics_keyboard() -> InlineKeyboardMarkup:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM clinics ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    if not rows:
        buttons = [[InlineKeyboardButton("کلینیک مرکزی", callback_data="clinic_1")]]
    else:
        buttons = [
            [
                InlineKeyboardButton(
                    f"{r['name']} - {r['city']}", callback_data=f"clinic_{r['id']}"
                )
            ]
            for r in rows
        ]
    return InlineKeyboardMarkup(buttons)


def services_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("بوتاکس", callback_data="service_Botox")],
        [InlineKeyboardButton("فیلر", callback_data="service_Filler")],
        [InlineKeyboardButton("لیزر", callback_data="service_Laser")],
        [InlineKeyboardButton("مزوتراپی", callback_data="service_Meso")],
    ]
    return InlineKeyboardMarkup(buttons)


def date_keyboard() -> InlineKeyboardMarkup:
    today = datetime.now().date()
    buttons: List[List[InlineKeyboardButton]] = []
    for i in range(0, 7):
        d = today + timedelta(days=i)
        s = d.strftime("%Y-%m-%d")
        buttons.append([InlineKeyboardButton(s, callback_data=f"date_{s}")])
    buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")])
    return InlineKeyboardMarkup(buttons)


def time_slots_keyboard(selected_date: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(t, callback_data=f"time_{selected_date}_{t}")]
        for t in TIME_SLOTS
    ]
    buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_dates")])
    return InlineKeyboardMarkup(buttons)


def skin_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("خشک", callback_data="skin_type_dry"),
                InlineKeyboardButton("چرب", callback_data="skin_type_oily"),
            ],
            [
                InlineKeyboardButton("مختلط", callback_data="skin_type_combination"),
                InlineKeyboardButton("نرمال", callback_data="skin_type_normal"),
            ],
            [InlineKeyboardButton("حساس", callback_data="skin_type_sensitive")],
        ]
    )


def skin_concern_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("جوش فعال / آکنه", callback_data="concern_acne"),
                InlineKeyboardButton("لک و تیرگی", callback_data="concern_pigmentation"),
            ],
            [
                InlineKeyboardButton("چروک/خطوط ریز", callback_data="concern_wrinkles"),
                InlineKeyboardButton("قرمزی/التهاب", callback_data="concern_redness"),
            ],
            [
                InlineKeyboardButton("منافذ باز", callback_data="concern_pores"),
                InlineKeyboardButton("اسکار/فرورفتگی", callback_data="concern_scars"),
            ],
        ]
    )


def sensitivity_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("کم", callback_data="sens_low"),
                InlineKeyboardButton("متوسط", callback_data="sens_medium"),
                InlineKeyboardButton("زیاد", callback_data="sens_high"),
            ]
        ]
    )


# ======================= متن‌ها =======================


def format_user_profile(user_row: sqlite3.Row) -> str:
    tags = user_row["tags"] or ""
    allergies = user_row["allergies"] or "ثبت نشده"
    notes = user_row["important_notes"] or "ثبت نشده"
    ref_code = user_row["referral_code"] or "تعریف نشده"
    points = user_row["referral_points"] or 0
    vip = "✅" if points >= VIP_THRESHOLD_POINTS else "❌"
    return (
        "👤 پروفایل شما:\n\n"
        f"نام: {user_row['full_name'] or 'ثبت نشده'}\n"
        f"شماره تماس: {user_row['phone_number'] or 'ثبت نشده'}\n"
        f"حساسیت‌ها: {allergies}\n"
        f"یادداشت‌های مهم: {notes}\n"
        f"کد معرف: {ref_code}\n"
        f"امتیاز معرف: {points}\n"
        f"وضعیت VIP: {vip}\n"
        f"برچسب‌ها: {tags or '-'}\n"
    )


def build_skin_consultation_text(
    skin_type_key: str,
    skin_concern_key: str,
    sensitivity_key: str,
) -> Dict[str, str]:
    key = (skin_type_key, skin_concern_key, sensitivity_key)
    data = TREATMENT_SUGGESTIONS.get(key)
    if not data:
        title = "مشاوره پوستی اختصاصی شما"
        body = (
            f"نوع پوست: {SKIN_TYPES.get(skin_type_key, 'نامشخص')}\n"
            f"مشکل اصلی: {SKIN_CONCERNS.get(skin_concern_key, 'نامشخص')}\n"
            f"حساسیت: {SENSITIVITY_LEVELS.get(sensitivity_key, 'نامشخص')}\n\n"
            "در حال حاضر برای این ترکیب خاص، پروتکل اختصاصی تعریف نشده.\n"
            "پیشنهاد می‌کنیم برای مشاوره تخصصی، با کلینیک تماس بگیرید 🌸"
        )
        return {"title": title, "body": body}

    lines: List[str] = []
    lines.append(f"✨ {data['title']}\n")
    lines.append("روتین صبح:\n")
    for s in data["routine_morning"]:
        lines.append(f"• {s}")
    lines.append("\nروتین شب:\n")
    for s in data["routine_night"]:
        lines.append(f"• {s}")
    lines.append("\nدرمان‌های پیشنهادی در کلینیک:\n")
    for s in data["clinic_treatments"]:
        lines.append(f"• {s}")
    lines.append("\nنکات مهم:\n" + data["notes"])
    return {"title": data["title"], "body": "\n".join(lines)}


# ======================= پرداخت زرین‌پال =======================


def create_zarinpal_payment_link(amount: int, description: str) -> Optional[str]:
    """
    درخواست لینک پرداخت از زرین‌پال (حالت سندباکس).
    """
    if not ZARINPAL_MERCHANT_ID:
        logger.warning("ZARINPAL_MERCHANT_ID تنظیم نشده است.")
        return None

    callback_url = "https://example.com/payment/callback"

    payload = {
        "MerchantID": ZARINPAL_MERCHANT_ID,
        "Amount": amount,
        "Description": description,
        "CallbackURL": callback_url,
        "Email": "",
        "Mobile": "",
    }
    try:
        r = requests.post(ZARINPAL_REQUEST_URL, json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        authority = None
        status = None
        if isinstance(data, dict):
            status = data.get("Status") or data.get("status")
            authority = data.get("Authority") or (data.get("data") or {}).get(
                "authority"
            )
        if status == 100 and authority:
            return ZARINPAL_STARTPAY_URL.format(Authority=authority)
        logger.warning("Zarinpal response not success: %s", data)
        return None
    except Exception as e:
        logger.exception("خطا در ارتباط با زرین‌پال: %s", e)
        return None


# ======================= فرمان‌ها =======================


async def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user = update.effective_user
    full_name = user.full_name

    # همه stateها را پاک می‌کنیم تا گیر نکند
    clear_user_state(chat_id, None)

    db_user = get_or_create_user(chat_id, full_name)

    welcome = (
        f"سلام {full_name} 🌸\n"
        f"به ربات {CLINIC_NAME} (نسخه PRO) خوش آمدید.\n\n"
        "از منوی پایین یا منوی شیشه‌ای زیر استفاده کنید."
    )

    await update.message.reply_text(
        welcome,
        reply_markup=build_reply_keyboard(is_admin(chat_id)),
    )

    # یک منوی Inline هم برای راحتی
    await update.message.reply_text(
        "منوی اصلی:",
        reply_markup=main_menu_inline(is_admin(chat_id)),
    )


async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "راهنما:\n"
        "• /start شروع مجدد\n"
        "• /adminlogin ورود به پنل مدیریت (فقط برای مدیر)\n"
        "• بقیه تنظیمات از طریق منو انجام می‌شود."
    )


async def admin_login_cmd(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    set_user_state(chat_id, STATE_AWAITING_ADMIN_USERNAME, True)
    await update.message.reply_text(
        "🔐 لطفاً نام کاربری ادمین را وارد کنید:",
        reply_markup=build_reply_keyboard(is_admin(chat_id)),
    )


# ======================= مسیج هندلرها =======================


async def handle_text(update: Update, context: CallbackContext):
    message = update.message
    text = (message.text or "").strip()
    chat_id = message.chat_id
    user_row = get_or_create_user(chat_id, message.from_user.full_name)

    # --- اول stateهای خاص (لاگین ادمین، آلرژی، ...) ---

    if get_user_state(chat_id, STATE_AWAITING_ADMIN_USERNAME):
        clear_user_state(chat_id, STATE_AWAITING_ADMIN_USERNAME)
        set_user_state(chat_id, STATE_AWAITING_ADMIN_PASSWORD, text)
        await message.reply_text("لطفاً رمز عبور ادمین را وارد کنید:")
        return

    if get_user_state(chat_id, STATE_AWAITING_ADMIN_PASSWORD):
        username = get_user_state(chat_id, STATE_AWAITING_ADMIN_PASSWORD)
        clear_user_state(chat_id, STATE_AWAITING_ADMIN_PASSWORD)
        if username == ADMIN_LOGIN_USERNAME and text == ADMIN_LOGIN_PASSWORD:
            conn = get_conn()
            conn.execute(
                "UPDATE users SET is_admin = 1 WHERE chat_id = ?", (chat_id,)
            )
            conn.commit()
            conn.close()
            await message.reply_text(
                "✅ ورود موفق به پنل مدیریت.\n"
                "از منوی پایین می‌توانید «🛠 پنل مدیریت» را انتخاب کنید.",
                reply_markup=build_reply_keyboard(True),
            )
        else:
            await message.reply_text("❌ نام کاربری یا رمز عبور اشتباه است.")
        return

    if get_user_state(chat_id, STATE_AWAITING_ALLERGIES):
        clear_user_state(chat_id, STATE_AWAITING_ALLERGIES)
        conn = get_conn()
        conn.execute(
            "UPDATE users SET allergies = ? WHERE chat_id = ?", (text, chat_id)
        )
        conn.commit()
        conn.close()
        await message.reply_text(
            "✅ حساسیت‌ها/آلرژی‌ها ذخیره شد.",
            reply_markup=build_reply_keyboard(is_admin(chat_id)),
        )
        return

    if get_user_state(chat_id, STATE_AWAITING_IMPORTANT_NOTES):
        clear_user_state(chat_id, STATE_AWAITING_IMPORTANT_NOTES)
        conn = get_conn()
        conn.execute(
            "UPDATE users SET important_notes = ? WHERE chat_id = ?",
            (text, chat_id),
        )
        conn.commit()
        conn.close()
        await message.reply_text(
            "✅ یادداشت در پرونده شما ذخیره شد.",
            reply_markup=build_reply_keyboard(is_admin(chat_id)),
        )
        return

    if get_user_state(chat_id, STATE_AWAITING_REFERRAL_CODE):
        await save_referral_from_text(update, text)
        return

    if get_user_state(chat_id, STATE_AWAITING_BROADCAST_TEXT) and is_admin(chat_id):
        await handle_broadcast_text(update, text)
        return

    # --- منوی پایین (ReplyKeyboard) ---

    if text == "🗓 رزرو نوبت":
        await message.reply_text(
            "🗓 رزرو نوبت:\n\nابتدا شعبه/کلینیک را انتخاب کنید.",
            reply_markup=clinics_keyboard(),
        )
        return

    if text == "💳 پرداخت":
        await show_payment_menu_message(message, user_row)
        return

    if text == "🧴 مشاوره پوستی":
        await message.reply_text(
            "ابتدا نوع پوست خود را انتخاب کنید:", reply_markup=skin_type_keyboard()
        )
        return

    if text == "👤 پروفایل من":
        await show_profile_message(message, user_row)
        return

    if text == "📣 لینک من / کد معرف":
        await show_referral_menu_message(message, user_row)
        return

    if text == "🛠 پنل مدیریت" and is_admin(chat_id):
        await message.reply_text("🛠 پنل مدیریت:", reply_markup=admin_menu_keyboard())
        return

    # --- حالت پیش‌فرض ---
    await message.reply_text(
        "پیام شما دریافت شد. برای استفاده از امکانات، از منو استفاده کنید.",
        reply_markup=build_reply_keyboard(is_admin(chat_id)),
    )


async def handle_contact(update: Update, context: CallbackContext):
    contact = update.message.contact
    chat_id = update.message.chat_id
    conn = get_conn()
    conn.execute(
        "UPDATE users SET phone_number = ? WHERE chat_id = ?",
        (contact.phone_number, chat_id),
    )
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ شماره تماس شما ذخیره شد.")


async def handle_photo(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    if get_user_state(chat_id, STATE_AWAITING_RECEIPT_PHOTO):
        clear_user_state(chat_id, STATE_AWAITING_RECEIPT_PHOTO)
        await update.message.reply_text(
            "✅ تصویر رسید دریافت شد.\n"
            "پس از بررسی ادمین، وضعیت پرداخت در سیستم به‌روزرسانی می‌شود.",
            reply_markup=build_reply_keyboard(is_admin(chat_id)),
        )
    else:
        await update.message.reply_text("عکس شما دریافت شد.")


# ======================= Callback Router =======================


async def callback_router(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id
    user_row = get_or_create_user(chat_id, query.from_user.full_name)

    # منوی اصلی
    if data == "menu_reserve":
        await query.message.edit_text(
            "🗓 رزرو نوبت:\n\nابتدا شعبه/کلینیک را انتخاب کنید.",
            reply_markup=clinics_keyboard(),
        )
    elif data == "menu_payment":
        await show_payment_menu_query(query, user_row)
    elif data == "menu_consult":
        await start_skin_consult(query)
    elif data == "menu_packages":
        await query.message.edit_text(
            "📦 مدیریت پکیج‌ها در نسخه بعدی تکمیل‌تر خواهد شد.",
            reply_markup=main_menu_inline(is_admin(chat_id)),
        )
    elif data == "menu_profile":
        await show_profile_query(query, user_row)
    elif data == "menu_referral":
        await show_referral_menu_query(query, user_row)
    elif data == "menu_admin":
        if is_admin(chat_id):
            await show_admin_menu(query)
        else:
            await query.message.reply_text("❌ شما دسترسی ادمین ندارید.")

    # رزرو
    elif data.startswith("clinic_"):
        await handle_clinic_select(query, data, user_row)
    elif data.startswith("service_"):
        await handle_service_select(query, data, user_row)
    elif data.startswith("date_"):
        await handle_date_select(query, data, user_row)
    elif data.startswith("time_"):
        await handle_time_select(query, data, user_row)

    elif data == "back_to_dates":
        await query.message.edit_text(
            "تاریخ را انتخاب کنید:", reply_markup=date_keyboard()
        )
        return

    elif data == "back_to_main":
        await query.message.edit_text(
            "منوی اصلی:",
            reply_markup=main_menu_inline(is_admin(chat_id)),
        )
        return

    # پرداخت
    elif data == "payment_offline":
        await show_offline_payment_query(query, user_row)
    elif data == "payment_online":
        await show_online_payment_query(query, user_row)

    # مشاوره پوستی
    elif data.startswith("skin_type_"):
        await handle_skin_type_select(query, data, user_row)
    elif data.startswith("concern_"):
        await handle_skin_concern_select(query, data, user_row)
    elif data.startswith("sens_"):
        await handle_sensitivity_select(query, data, user_row)

    # Referral
    elif data == "enter_referral":
        await ask_referral_code(query, user_row)
    elif data == "my_referral_link":
        await show_my_referral_link(query, user_row)

    # پروفایل - آلرژی و یادداشت
    elif data == "enter_allergies":
        await ask_allergies(query)
    elif data == "enter_important_notes":
        await ask_important_notes(query)

    # Admin
    elif data == "admin_dashboard" and is_admin(chat_id):
        await show_admin_dashboard(query)
    elif data == "admin_users" and is_admin(chat_id):
        await show_admin_users(query)
    elif data == "admin_appointments" and is_admin(chat_id):
        await show_admin_appointments(query)
    elif data == "admin_payments" and is_admin(chat_id):
        await show_admin_payments(query)
    elif data == "admin_consults" and is_admin(chat_id):
        await show_admin_consults(query)
    elif data == "admin_packages" and is_admin(chat_id):
        await show_admin_packages(query)
    elif data == "admin_broadcast" and is_admin(chat_id):
        await ask_broadcast_text(query)


# ======================= رزرو نوبت =======================


async def handle_clinic_select(query, data: str, user_row):
    clinic_id = int(data.split("_")[1])
    chat_id = query.message.chat_id
    set_user_state(chat_id, "selected_clinic_id", clinic_id)
    await query.message.edit_text(
        "نوع خدمت را انتخاب کنید:", reply_markup=services_keyboard()
    )


async def handle_service_select(query, data: str, user_row):
    service_code = data.split("_", 1)[1]  # Botox/Filler/...
    chat_id = query.message.chat_id
    set_user_state(chat_id, "selected_service_code", service_code)
    await query.message.edit_text(
        "تاریخ مراجعه را انتخاب کنید:", reply_markup=date_keyboard()
    )


async def handle_date_select(query, data: str, user_row):
    _, date_str = data.split("_", 1)
    chat_id = query.message.chat_id
    set_user_state(chat_id, "selected_date", date_str)
    await query.message.edit_text(
        f"تاریخ انتخاب‌شده: {date_str}\n\nلطفاً ساعت را انتخاب کنید:",
        reply_markup=time_slots_keyboard(date_str),
    )


async def handle_time_select(query, data: str, user_row):
    _, date_str, time_str = data.split("_", 2)
    chat_id = query.message.chat_id

    clinic_id = get_user_state(chat_id, "selected_clinic_id")
    service_code = get_user_state(chat_id, "selected_service_code")
    if not clinic_id or not service_code:
        await query.message.edit_text(
            "❌ اطلاعات نوبت کامل نیست. لطفاً از اول رزرو را شروع کنید.",
            reply_markup=main_menu_inline(is_admin(chat_id)),
        )
        return

    service_name_map = {
        "Botox": "بوتاکس",
        "Filler": "فیلر",
        "Laser": "لیزر",
        "Meso": "مزوتراپی",
    }
    service_name = service_name_map.get(service_code, service_code)

    recall_days = TREATMENT_RECALL_DAYS.get(service_code, 0)
    recall_date = None
    if recall_days > 0:
        d = datetime.strptime(date_str, "%Y-%m-%d").date() + timedelta(days=recall_days)
        recall_date = d.strftime("%Y-%m-%d")

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO appointments (user_id, clinic_id, service_name, doctor_name, date, time, recall_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_row["id"],
            clinic_id,
            service_name,
            DOCTORS[0],
            date_str,
            time_str,
            recall_date,
        ),
    )
    conn.commit()
    app_id = c.lastrowid
    conn.close()

    text = (
        "✅ نوبت شما ثبت شد.\n\n"
        f"شماره نوبت: {app_id}\n"
        f"خدمت: {service_name}\n"
        f"تاریخ: {date_str}\n"
        f"ساعت: {time_str}\n"
        f"پزشک: {DOCTORS[0]}\n"
    )
    if recall_date:
        text += f"\n📅 زمان مناسب برای یادآوری جلسه بعدی: {recall_date}"

    await query.message.edit_text(
        text, reply_markup=main_menu_inline(is_admin(chat_id))
    )


# ======================= پرداخت =======================


async def show_payment_menu_message(message, user_row):
    chat_id = message.chat_id
    text = (
        "💳 پرداخت خدمات:\n\n"
        "می‌توانید پرداخت خود را به‌صورت آفلاین (کارت به کارت) یا از طریق درگاه ایرانی (زرین‌پال - تست) انجام دهید."
    )
    buttons = [
        [
            InlineKeyboardButton(
                "🏦 پرداخت آفلاین (کارت به کارت)", callback_data="payment_offline"
            )
        ],
        [
            InlineKeyboardButton(
                "💳 پرداخت آنلاین (درگاه ایرانی - تست)", callback_data="payment_online"
            )
        ],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")],
    ]
    await message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(buttons)
    )


async def show_payment_menu_query(query, user_row):
    text = (
        "💳 پرداخت خدمات:\n\n"
        "می‌توانید پرداخت خود را به‌صورت آفلاین (کارت به کارت) یا از طریق درگاه ایرانی (زرین‌پال - تست) انجام دهید."
    )
    buttons = [
        [
            InlineKeyboardButton(
                "🏦 پرداخت آفلاین (کارت به کارت)", callback_data="payment_offline"
            )
        ],
        [
            InlineKeyboardButton(
                "💳 پرداخت آنلاین (درگاه ایرانی - تست)", callback_data="payment_online"
            )
        ],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")],
    ]
    await query.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(buttons)
    )


async def show_offline_payment_query(query, user_row):
    chat_id = query.message.chat_id
    set_user_state(chat_id, STATE_AWAITING_RECEIPT_PHOTO, True)
    text = (
        "🏦 پرداخت آفلاین (کارت به کارت):\n\n"
        f"شماره کارت:\n{OFFLINE_CARD_NUMBER}\n"
        f"به نام: {OFFLINE_CARD_OWNER}\n\n"
        "پس از واریز، تصویر رسید را برای ربات ارسال کنید.\n\n"
        "برای بازگشت می‌توانید /start یا منوی پایین را استفاده کنید."
    )
    await query.message.edit_text(
        text, reply_markup=main_menu_inline(is_admin(chat_id))
    )


async def show_online_payment_query(query, user_row):
    chat_id = query.message.chat_id
    amount = 500000  # مثال: ۵۰ هزار تومان = ۵۰۰۰۰۰ ریال
    description = f"پرداخت خدمات {CLINIC_NAME}"

    link = create_zarinpal_payment_link(amount, description)
    if not link:
        text = (
            "❌ در حال حاضر امکان اتصال کامل به درگاه پرداخت فراهم نیست.\n"
            "می‌توانید از روش کارت به کارت استفاده کنید.\n\n"
            "برای بازگشت از منوی پایین یا /start استفاده کنید."
        )
        await query.message.edit_text(
            text, reply_markup=main_menu_inline(is_admin(chat_id))
        )
        return

    text = (
        "💳 پرداخت آنلاین (زرین‌پال - تست):\n\n"
        "برای ادامه پرداخت روی لینک زیر کلیک کنید:\n"
        f"{link}\n\n"
        "در این نسخه‌ی تست، وضعیت پرداخت به‌صورت خودکار تایید نمی‌شود و توسط کلینیک بررسی می‌گردد.\n\n"
        "پس از پرداخت، می‌توانید با منوی پایین به سایر بخش‌ها برگردید."
    )
    await query.message.edit_text(
        text, reply_markup=main_menu_inline(is_admin(chat_id))
    )


# ======================= مشاوره پوستی =======================


async def start_skin_consult(query):
    chat_id = query.message.chat_id
    await query.message.edit_text(
        "ابتدا نوع پوست خود را انتخاب کنید:", reply_markup=skin_type_keyboard()
    )


async def handle_skin_type_select(query, data: str, user_row):
    chat_id = query.message.chat_id
    skin_type_key = data.split("_", 2)[2]
    set_user_state(chat_id, "skin_type_key", skin_type_key)
    await query.message.edit_text(
        "مشکل اصلی پوست خود را انتخاب کنید:", reply_markup=skin_concern_keyboard()
    )


async def handle_skin_concern_select(query, data: str, user_row):
    chat_id = query.message.chat_id
    concern_key = data.split("_", 1)[1]
    set_user_state(chat_id, "skin_concern_key", concern_key)
    await query.message.edit_text(
        "میزان حساسیت پوست خود را مشخص کنید:", reply_markup=sensitivity_keyboard()
    )


async def handle_sensitivity_select(query, data: str, user_row):
    chat_id = query.message.chat_id
    sens_key = data.replace("sens_", "")

    skin_type_key = get_user_state(chat_id, "skin_type_key")
    skin_concern_key = get_user_state(chat_id, "skin_concern_key")
    if not skin_type_key or not skin_concern_key:
        await query.message.edit_text(
            "❌ اطلاعات مشاوره کامل نیست. لطفاً از ابتدا شروع کنید.",
            reply_markup=main_menu_inline(is_admin(chat_id)),
        )
        return

    consult = build_skin_consultation_text(skin_type_key, skin_concern_key, sens_key)

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO consultations (
            user_id, skin_type_key, skin_concern_key, sensitivity_key,
            suggestion_title, suggestion_text
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_row["id"],
            skin_type_key,
            skin_concern_key,
            sens_key,
            consult["title"],
            consult["body"],
        ),
    )
    conn.commit()
    conn.close()

    await query.message.edit_text(
        f"📋 {consult['title']}\n\n{consult['body']}",
        reply_markup=main_menu_inline(is_admin(chat_id)),
    )


# ======================= پروفایل و Referral =======================


def generate_referral_code(user_id: int) -> str:
    return f"GLR{user_id:05d}"


async def show_profile_query(query, user_row):
    chat_id = query.message.chat_id
    text = format_user_profile(user_row)
    buttons = [
        [
            InlineKeyboardButton("حساسیت‌ها / آلرژی‌ها", callback_data="enter_allergies"),
            InlineKeyboardButton(
                "یادداشت مهم", callback_data="enter_important_notes"
            ),
        ],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")],
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def show_profile_message(message, user_row):
    chat_id = message.chat_id
    text = format_user_profile(user_row)
    buttons = [
        [
            InlineKeyboardButton("حساسیت‌ها / آلرژی‌ها", callback_data="enter_allergies"),
            InlineKeyboardButton(
                "یادداشت مهم", callback_data="enter_important_notes"
            ),
        ],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")],
    ]
    await message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def ask_allergies(query):
    chat_id = query.message.chat_id
    set_user_state(chat_id, STATE_AWAITING_ALLERGIES, True)
    await query.message.edit_text("حساسیت‌ها و آلرژی‌های مهم خود را وارد کنید:")


async def ask_important_notes(query):
    chat_id = query.message.chat_id
    set_user_state(chat_id, STATE_AWAITING_IMPORTANT_NOTES, True)
    await query.message.edit_text(
        "یادداشت‌های مهم درباره‌ی وضعیت پوستی یا پزشکی خود را وارد کنید:"
    )


async def show_referral_menu_query(query, user_row):
    chat_id = query.message.chat_id
    text, buttons = build_referral_menu(user_row)
    await query.message.edit_text(text, reply_markup=buttons)


async def show_referral_menu_message(message, user_row):
    text, buttons = build_referral_menu(user_row)
    await message.reply_text(text, reply_markup=buttons)


def build_referral_menu(user_row):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT referral_code, referral_points FROM users WHERE id = ?",
        (user_row["id"],),
    )
    row = c.fetchone()
    conn.close()
    ref_code = row["referral_code"]
    points = row["referral_points"] or 0
    if not ref_code:
        ref_code = generate_referral_code(user_row["id"])
        conn2 = get_conn()
        conn2.execute(
            "UPDATE users SET referral_code = ? WHERE id = ?",
            (ref_code, user_row["id"]),
        )
        conn2.commit()
        conn2.close()

    referral_link = f"https://t.me/GloriaClinicBot?start={ref_code}"

    text = (
        "📣 لینک من / کد معرف:\n\n"
        f"کد معرف شما: {ref_code}\n"
        f"امتیاز معرف فعلی: {points}\n\n"
        f"لینک دعوت (نمونه):\n{referral_link}\n\n"
        "با اشتراک این لینک، در صورت ثبت‌نام دوستانتان، امتیاز دریافت می‌کنید."
    )
    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("ثبت کد معرف دوست", callback_data="enter_referral")],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")],
        ]
    )
    return text, buttons


async def ask_referral_code(query, user_row):
    chat_id = query.message.chat_id
    set_user_state(chat_id, STATE_AWAITING_REFERRAL_CODE, True)
    await query.message.edit_text(
        "لطفاً کد معرف دوست خود را ارسال کنید (مثلاً: GLR00012):"
    )


async def save_referral_from_text(update: Update, text: str):
    chat_id = update.message.chat_id
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, referred_by_user_id FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        clear_user_state(chat_id, STATE_AWAITING_REFERRAL_CODE)
        await update.message.reply_text("❌ خطا در یافتن کاربر.")
        return

    if row["referred_by_user_id"]:
        conn.close()
        clear_user_state(chat_id, STATE_AWAITING_REFERRAL_CODE)
        await update.message.reply_text("شما قبلاً یک معرف ثبت کرده‌اید.")
        return

    ref_code = text.strip().upper()
    c.execute("SELECT id FROM users WHERE referral_code = ?", (ref_code,))
    ref_row = c.fetchone()
    if not ref_row:
        conn.close()
        await update.message.reply_text("❌ کد معرف نامعتبر است. دوباره تلاش کنید.")
        return

    if ref_row["id"] == row["id"]:
        conn.close()
        await update.message.reply_text("نمی‌توانید خودتان را به‌عنوان معرف ثبت کنید.")
        return

    c.execute(
        "UPDATE users SET referred_by_user_id = ? WHERE id = ?",
        (ref_row["id"], row["id"]),
    )
    c.execute(
        "UPDATE users SET referral_points = referral_points + ? WHERE id = ?",
        (REFERRAL_BONUS_POINTS, ref_row["id"]),
    )
    conn.commit()
    conn.close()
    clear_user_state(chat_id, STATE_AWAITING_REFERRAL_CODE)
    await update.message.reply_text(
        "✅ کد معرف با موفقیت ثبت شد.",
        reply_markup=build_reply_keyboard(is_admin(chat_id)),
    )


async def show_my_referral_link(query, user_row):
    await show_referral_menu_query(query, user_row)


# ======================= Admin Panel =======================


async def show_admin_menu(query):
    await query.message.edit_text("🛠 پنل مدیریت:", reply_markup=admin_menu_keyboard())


async def show_admin_dashboard(query):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS cnt FROM users")
    users_cnt = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) AS cnt FROM appointments")
    app_cnt = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) AS cnt FROM payments")
    pay_cnt = c.fetchone()["cnt"]
    conn.close()
    text = (
        "📊 داشبورد کلی:\n\n"
        f"تعداد کاربران: {users_cnt}\n"
        f"تعداد نوبت‌ها: {app_cnt}\n"
        f"تعداد پرداخت‌ها: {pay_cnt}\n"
    )
    await query.message.edit_text(text, reply_markup=admin_menu_keyboard())


async def show_admin_users(query):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY id DESC LIMIT 20")
    rows = c.fetchall()
    conn.close()
    if not rows:
        text = "کاربری ثبت نشده است."
    else:
        lines = ["👥 آخرین کاربران:\n"]
        for r in rows:
            lines.append(
                f"- #{r['id']} | {r['full_name']} | {r['phone_number'] or 'بدون شماره'} | امتیاز: {r['referral_points']}"
            )
        text = "\n".join(lines)
    await query.message.edit_text(text, reply_markup=admin_menu_keyboard())


async def show_admin_appointments(query):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT a.*, u.full_name
        FROM appointments a
        LEFT JOIN users u ON a.user_id = u.id
        ORDER BY a.id DESC LIMIT 20
        """
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        text = "🗓 هنوز نوبتی ثبت نشده است."
    else:
        lines = ["🗓 آخرین نوبت‌ها:\n"]
        for r in rows:
            lines.append(
                f"- #{r['id']} | {r['full_name']} | {r['service_name']} | {r['date']} {r['time']} | وضعیت: {r['status']}"
            )
        text = "\n".join(lines)
    await query.message.edit_text(text, reply_markup=admin_menu_keyboard())


async def show_admin_payments(query):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT p.*, u.full_name
        FROM payments p
        LEFT JOIN users u ON p.user_id = u.id
        ORDER BY p.id DESC LIMIT 20
        """
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        text = "💳 پرداختی ثبت نشده است."
    else:
        lines = ["💳 آخرین پرداخت‌ها:\n"]
        for r in rows:
            lines.append(
                f"- #{r['id']} | {r['full_name']} | مبلغ: {r['amount']} | روش: {r['method']} | وضعیت: {r['status']}"
            )
        text = "\n".join(lines)
    await query.message.edit_text(text, reply_markup=admin_menu_keyboard())


async def show_admin_consults(query):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT c.*, u.full_name
        FROM consultations c
        LEFT JOIN users u ON c.user_id = u.id
        ORDER BY c.id DESC LIMIT 20
        """
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        text = "🧴 هنوز مشاوره‌ای ثبت نشده است."
    else:
        lines = ["🧴 آخرین مشاوره‌ها:\n"]
        for r in rows:
            lines.append(
                f"- #{r['id']} | {r['full_name']} | {r['suggestion_title']}"
            )
        text = "\n".join(lines)
    await query.message.edit_text(text, reply_markup=admin_menu_keyboard())


async def show_admin_packages(query):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT p.*, u.full_name
        FROM packages p
        LEFT JOIN users u ON p.user_id = u.id
        ORDER BY p.id DESC LIMIT 20
        """
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        text = "📦 هنوز پکیجی ثبت نشده است."
    else:
        lines = ["📦 آخرین پکیج‌ها:\n"]
        for r in rows:
            lines.append(
                f"- #{r['id']} | {r['full_name']} | {r['title']} | {r['used_sessions']}/{r['total_sessions']}"
            )
        text = "\n".join(lines)
    await query.message.edit_text(text, reply_markup=admin_menu_keyboard())


async def ask_broadcast_text(query):
    chat_id = query.message.chat_id
    set_user_state(chat_id, STATE_AWAITING_BROADCAST_TEXT, True)
    await query.message.edit_text(
        "📨 متن پیام گروهی را ارسال کنید.\nبرای لغو، /cancel بفرستید."
    )


async def handle_broadcast_text(update: Update, text: str):
    chat_id = update.message.chat_id
    if text.strip().lower().startswith("/cancel"):
        clear_user_state(chat_id, STATE_AWAITING_BROADCAST_TEXT)
        await update.message.reply_text("ارسال پیام گروهی لغو شد.")
        return

    users = get_all_users()
    sent = 0
    for u in users:
        try:
            if u["chat_id"] != 0:
                await update.get_bot().send_message(chat_id=u["chat_id"], text=text)
                sent += 1
        except Exception as e:
            logger.exception("خطا در ارسال پیام گروهی: %s", e)

    clear_user_state(chat_id, STATE_AWAITING_BROADCAST_TEXT)
    await update.message.reply_text(f"پیام گروهی ارسال شد. تعداد دریافت‌کنندگان: {sent}")


# ======================= JobQueue (یادآوری + Recall) =======================


async def reminder_job(context: CallbackContext):
    now = datetime.now()
    soon = now + timedelta(hours=24)
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT a.*, u.chat_id
        FROM appointments a
        LEFT JOIN users u ON a.user_id = u.id
        WHERE a.status='reserved'
          AND datetime(a.date || ' ' || a.time) BETWEEN ? AND ?
        """,
        (now.strftime("%Y-%m-%d %H:%M"), soon.strftime("%Y-%m-%d %H:%M")),
    )
    rows = c.fetchall()
    conn.close()
    for r in rows:
        try:
            msg = (
                "⏰ یادآوری نوبت:\n\n"
                f"خدمت: {r['service_name']}\n"
                f"تاریخ: {r['date']}\n"
                f"ساعت: {r['time']}\n"
                "در صورت نیاز به تغییر، لطفاً با کلینیک تماس بگیرید."
            )
            await context.bot.send_message(chat_id=r["chat_id"], text=msg)
        except Exception as e:
            logger.exception("خطا در reminder_job: %s", e)


async def recall_job(context: CallbackContext):
    today = datetime.now().date().strftime("%Y-%m-%d")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT a.*, u.chat_id
        FROM appointments a
        LEFT JOIN users u ON a.user_id = u.id
        WHERE a.recall_date = ? AND a.recall_sent = 0
        """,
        (today,),
    )
    rows = c.fetchall()
    for r in rows:
        try:
            msg = (
                "🔄 یادآوری دوره درمان:\n\n"
                f"خدمت: {r['service_name']}\n"
                f"تاریخ آخرین جلسه: {r['date']}\n\n"
                "زمان مناسبی برای تمدید یا ادامه دوره‌ی شماست.\n"
                "در صورت تمایل، می‌توانیم نوبت جدید تنظیم کنیم 🌿"
            )
            await context.bot.send_message(chat_id=r["chat_id"], text=msg)
            c2 = conn.cursor()
            c2.execute(
                "UPDATE appointments SET recall_sent = 1 WHERE id = ?", (r["id"],)
            )
            conn.commit()
        except Exception as e:
            logger.exception("خطا در recall_job: %s", e)
    conn.close()


# ======================= main (Webhook + Polling) =======================


def main():
    init_db()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # فرمان‌ها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("adminlogin", admin_login_cmd))

    # کال‌بک‌ها
    application.add_handler(CallbackQueryHandler(callback_router))

    # پیام‌ها
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # JobQueue
    jq: JobQueue = application.job_queue
    jq.run_repeating(reminder_job, interval=600, first=60)  # هر ۱۰ دقیقه چک ۲۴ ساعت بعد
    jq.run_repeating(recall_job, interval=3600, first=300)  # هر ۱ ساعت چک Recall

    webhook_url_base = os.getenv("WEBHOOK_URL", "").strip()
    port_str = os.getenv("PORT", "10000")
    try:
        port = int(port_str)
    except ValueError:
        port = 10000

    if webhook_url_base:
        full_webhook_url = webhook_url_base.rstrip("/") + "/" + WEBHOOK_PATH
        logger.info(
            "Starting PRO Bot in WEBHOOK mode on port %s, webhook: %s",
            port,
            full_webhook_url,
        )
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=WEBHOOK_PATH,
            webhook_url=full_webhook_url,
        )
    else:
        logger.warning("WEBHOOK_URL تنظیم نشده است. ربات در حالت polling اجرا می‌شود.")
        logger.info("PRO Bot started in POLLING mode...")
        application.run_polling()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("❕ ربات با دستور شما متوقف شد.")
    except Exception as e:
        logger.exception("⚠️ خطای کلی در اجرای ربات: %s", e)
