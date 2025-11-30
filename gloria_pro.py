# -*- coding: utf-8 -*-
"""
Gloria Clinic Telegram Bot - PRO Version

ویژگی‌ها:
- چند شعبه (کلینیک)
- رزرو نوبت + یادآوری قبل نوبت + پیام مراقبت بعد درمان + امتیازدهی + Recall
- پرداخت آفلاین (کارت به کارت) + پرداخت آنلاین (در حالت pending برای تأیید توسط ادمین)
- مشاوره پوستی هوشمند (جواب اختصاصی بر اساس نوع پوست/مشکل/حساسیت)
- پرونده الکترونیک زیبایی (سوابق نوبت، مشاوره، حساسیت، یادداشت‌های CRM)
- پکیج درمانی (مثلاً ۳ جلسه جوانسازی، ۶ جلسه لیزر، با شمارش جلسات استفاده‌شده)
- کد معرف / لینک من (Referral) + امتیاز معرف
- پنل مدیریت با داشبورد، لیست کاربران، نوبت‌ها، پرداخت‌ها، مشاوره‌ها، پکیج‌ها و پیام گروهی
"""

import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    Update,
    ReplyKeyboardRemove,
    InputMediaPhoto,
)
from telegram.ext import (
    Application,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
    JobQueue,
)

# ==================== تنظیمات کلی ====================

CLINIC_NAME = "Gloria Clinic"

# ⚠️ اگر خواستی توکن را عوض کنی، فقط همین خط را عوض کن:
TELEGRAM_BOT_TOKEN = "8437924316:AAFysR4_YGYr2HxhxLHWUVAJJdNHSXxNXns"

DB_PATH = "clinic_pro.db"

# کارت برای پرداخت آفلاین
OFFLINE_CARD_NUMBER = "6037-9917-1234-5678"
OFFLINE_CARD_OWNER = "Gloria Clinic"

# یوزرنیم و پسورد ادمین (می‌توانی تغییر بدهی)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

# حداقل فاصله بین نوبت‌ها بر حسب دقیقه
MIN_SLOT_MINUTES = 30

# برای امتیاز معرف
REFERRAL_BONUS_POINTS = 10

# برای دسته‌بندی کاربران
VIP_THRESHOLD_POINTS = 50

# ==================== دیکشنری‌های ثابت ====================

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

TREATMENT_SUGGESTIONS = {
    ("oily", "acne", "high"): {
        "title": "پوست چرب + آکنه فعال + حساسیت زیاد",
        "routine_morning": [
            "ژل شستشوی ملایم مخصوص پوست‌های چرب و حساس",
            "اسپری آب حرارتی یا تونر بدون الکل",
            "سرم حاوی نیاسینامید ۵٪",
            "کرم ضدآفتاب مینرال SPF 50 مخصوص پوست حساس",
        ],
        "routine_night": [
            "شستشوی ملایم",
            "استفاده از کرم حاوی ترکیبات ضدالتهاب (مثل آلوئه‌ورا، پانتنول)",
            "هفته‌ای ۲ شب، در صورت تحمل، استفاده از سرم حاوی BHA با درصد پایین",
        ],
        "clinic_treatments": [
            "درمان آکنه با لیزر یا نوردرمانی ملایم، در صورت تأیید پزشک",
            "پاکسازی حرفه‌ای با احتیاط و فاصله مناسب جلسات",
        ],
        "notes": "در این نوع پوست، هرگونه محصول تحریک‌کننده باید با احتیاط و به تدریج وارد روتین شود.",
    },
    ("dry", "wrinkles", "low"): {
        "title": "پوست خشک + خطوط ریز + حساسیت کم",
        "routine_morning": [
            "شیرپاک‌کن یا فوم بسیار ملایم",
            "سرم حاوی هیالورونیک اسید",
            "کرم مرطوب‌کننده غنی",
            "کرم ضدآفتاب با فیلترهای فیزیکی و شیمیایی",
        ],
        "routine_night": [
            "شستشوی ملایم",
            "کرم یا سرم حاوی رتینول با دوز کم (در صورت تأیید پزشک)",
            "کرم مغذی شب",
        ],
        "clinic_treatments": [
            "مزوتراپی آبرسان",
            "درمان‌های جوانسازی غیرتهاجمی طبق نظر پزشک",
        ],
        "notes": "مصرف آب کافی و پرهیز از شست‌وشوی بیش‌ازحد، برای این نوع پوست بسیار مهم است.",
    },
    # می‌توانی بقیه ترکیب‌ها را هم اضافه کنی...
}

POST_CARE_MESSAGES = {
    "Botox": "مراقبت‌های بعد از بوتاکس:\n- تا ۴ ساعت دراز نکشید.\n- از ماساژ ناحیه تزریق خودداری کنید.\n- در صورت بروز سردرد خفیف، با پزشک مشورت کنید.",
    "Filler": "مراقبت‌های بعد از فیلر:\n- از کمپرس سرد ملایم استفاده کنید.\n- از لمس و فشار شدید روی ناحیه تزریق خودداری کنید.\n- هرگونه درد یا تورم شدید را به پزشک اطلاع دهید.",
    "Laser": "مراقبت‌های بعد از لیزر:\n- تا ۴۸ ساعت از قرار گرفتن در معرض آفتاب مستقیم خودداری کنید.\n- از کرم ترمیم‌کننده طبق دستور پزشک استفاده کنید.\n- سونا و استخر فعلاً ممنوع است.",
}

TREATMENT_RECALL_DAYS = {
    "Botox": {"tag": "Botox", "recall_days": 180},
    "Filler": {"tag": "Filler", "recall_days": 270},
    "Laser": {"tag": "Laser", "recall_days": 45},
    "Meso": {"tag": "Meso", "recall_days": 90},
}

# پکیج‌ها
TREATMENT_PACKAGES = {
    "laser_6": {
        "title": "پکیج ۶ جلسه‌ای لیزر",
        "total_sessions": 6,
        "description": "مناسب برای لیزر موهای زائد، با ۶ جلسه با فاصله زمانی مناسب.",
    },
    "rejuvenation_3": {
        "title": "پکیج جوانسازی ۳ جلسه‌ای",
        "total_sessions": 3,
        "description": "شامل ۳ جلسه جوانسازی غیرتهاجمی برای بهبود بافت و درخشندگی پوست.",
    },
}

# پزشکان
DOCTORS: List[str] = ["دکتر احمدی", "دکتر رضایی", "دکتر محمدی"]

TIME_SLOTS = ["10:00", "11:00", "12:00", "14:00", "15:00", "16:00", "17:00"]

# state codes
STATE_AWAITING_NAME = "awaiting_name"
STATE_AWAITING_CLINIC = "awaiting_clinic"
STATE_AWAITING_PHONE = "awaiting_phone"
STATE_ADMIN_USERNAME = "awaiting_admin_username"
STATE_ADMIN_PASSWORD = "awaiting_admin_password"
STATE_AWAITING_RECEIPT_PHOTO = "awaiting_receipt_photo"
STATE_AWAITING_CRM_NOTE = "awaiting_crm_note"
STATE_AWAITING_ALLERGIES = "awaiting_allergies"
STATE_AWAITING_IMPORTANT_NOTES = "awaiting_important_notes"
STATE_AWAITING_REFERRAL_CODE = "awaiting_referral_code"

STATE_AWAITING_SKIN_TYPE = "awaiting_skin_type"
STATE_AWAITING_SKIN_CONCERN = "awaiting_skin_concern"
STATE_AWAITING_SENSITIVITY = "awaiting_sensitivity"

STATE_AWAITING_PACKAGE_SELECT = "awaiting_package_select"
STATE_AWAITING_PACKAGE_ASSIGN_USER = "awaiting_package_assign_user"

STATE_AWAITING_BROADCAST_TEXT = "awaiting_broadcast_text"
STATE_AWAITING_RATING = "awaiting_rating"

STATE_AWAITING_NEXT_RECALL_DATE = "awaiting_next_recall_date"

# for payments
PAYMENT_STATUS_PENDING = "pending"
PAYMENT_STATUS_CONFIRMED = "confirmed"
PAYMENT_STATUS_REJECTED = "rejected"

# ==================== logging ====================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# ==================== DB Helpers ====================

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # clinics
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS clinics (
            id INTEGER PRIMARY KEY,
            name TEXT,
            city TEXT
        )
        """
    )

    # users
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

    # appointments
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
            rating INTEGER,
            rating_comment TEXT,
            recall_tag TEXT,
            recall_date TEXT,
            recall_sent INTEGER DEFAULT 0
        )
        """
    )

    # payments
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            appointment_id INTEGER,
            amount INTEGER,
            method TEXT,
            status TEXT,
            card_last4 TEXT,
            tracking_code TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # consultations
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

    # packages
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

    # crm notes
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

    conn.commit()
    conn.close()


# ==================== Helper Functions ====================

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


def set_user_state(chat_id: int, state_key: str, value: Any):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    user_id = row["id"]
    table_name = "user_states"
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS user_states (
            user_id INTEGER PRIMARY KEY,
            state_json TEXT
        )
        """
    )
    c.execute("SELECT state_json FROM user_states WHERE user_id = ?", (user_id,))
    sr = c.fetchone()
    import json

    if sr and sr["state_json"]:
        data = json.loads(sr["state_json"])
    else:
        data = {}
    data[state_key] = value
    c.execute(
        "INSERT OR REPLACE INTO user_states (user_id, state_json) VALUES (?, ?)",
        (user_id, json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def get_user_state(chat_id: int, state_key: str, default=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return default
    user_id = row["id"]
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS user_states (
            user_id INTEGER PRIMARY KEY,
            state_json TEXT
        )
        """
    )
    c.execute("SELECT state_json FROM user_states WHERE user_id = ?", (user_id,))
    sr = c.fetchone()
    import json

    if not sr or not sr["state_json"]:
        conn.close()
        return default
    data = json.loads(sr["state_json"])
    conn.close()
    return data.get(state_key, default)


def clear_user_state(chat_id: int, state_key: Optional[str] = None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    user_id = row["id"]
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS user_states (
            user_id INTEGER PRIMARY KEY,
            state_json TEXT
        )
        """
    )
    c.execute("SELECT state_json FROM user_states WHERE user_id = ?", (user_id,))
    sr = c.fetchone()
    import json

    if not sr or not sr["state_json"]:
        conn.close()
        return
    data = json.loads(sr["state_json"])
    if state_key is None:
        data = {}
    else:
        data.pop(state_key, None)
    c.execute(
        "UPDATE user_states SET state_json = ? WHERE user_id = ?",
        (json.dumps(data, ensure_ascii=False), user_id),
    )
    conn.commit()
    conn.close()


def get_all_users():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    rows = c.fetchall()
    conn.close()
    return rows


def get_user_by_id(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row


def get_user_by_chat(chat_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    conn.close()
    return row


def ensure_admin_user():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM users WHERE is_admin = 1 ORDER BY id ASC LIMIT 1"
    )
    row = c.fetchone()
    if not row:
        # اولین ادمین ایجاد می‌شود با chat_id فرضی 0
        c.execute(
            """
            INSERT INTO users (chat_id, full_name, phone_number, is_admin)
            VALUES (?, ?, ?, 1)
            """,
            (0, "Super Admin", "",),
        )
        conn.commit()
    conn.close()


# ==================== Keyboards ====================

def main_menu_keyboard(is_admin_user: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🗓 رزرو نوبت", callback_data="menu_reserve")],
        [InlineKeyboardButton("💳 پرداخت", callback_data="menu_payment")],
        [InlineKeyboardButton("🧴 مشاوره پوستی", callback_data="menu_consult")],
        [InlineKeyboardButton("📦 پکیج‌های درمانی", callback_data="menu_packages")],
        [InlineKeyboardButton("👤 پروفایل من", callback_data="menu_profile")],
        [InlineKeyboardButton("📣 لینک من / کد معرف", callback_data="menu_referral")],
    ]
    if is_admin_user:
        buttons.append(
            [InlineKeyboardButton("🛠 پنل مدیریت", callback_data="menu_admin")]
        )
    return InlineKeyboardMarkup(buttons)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📊 داشبورد کلی", callback_data="admin_dashboard")],
        [InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("🗓 نوبت‌ها", callback_data="admin_appointments")],
        [InlineKeyboardButton("💳 پرداخت‌ها", callback_data="admin_payments")],
        [InlineKeyboardButton("🧴 مشاوره‌ها", callback_data="admin_consults")],
        [InlineKeyboardButton("📦 پکیج‌ها", callback_data="admin_packages")],
        [InlineKeyboardButton("📨 پیام گروهی", callback_data="admin_broadcast")],
        [InlineKeyboardButton("↩️ بازگشت به منوی اصلی", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def skin_consult_keyboard() -> InlineKeyboardMarkup:
    skin_type_buttons = [
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
    return InlineKeyboardMarkup(skin_type_buttons)


def skin_concern_keyboard() -> InlineKeyboardMarkup:
    concern_buttons = [
        [
            InlineKeyboardButton("جوش فعال / آکنه", callback_data="concern_acne"),
            InlineKeyboardButton("لک و تیرگی", callback_data="concern_pigmentation"),
        ],
        [
            InlineKeyboardButton("چروک و خطوط ریز", callback_data="concern_wrinkles"),
            InlineKeyboardButton("قرمزی و التهاب", callback_data="concern_redness"),
        ],
        [
            InlineKeyboardButton("منافذ باز", callback_data="concern_pores"),
            InlineKeyboardButton("اسکار و فرورفتگی", callback_data="concern_scars"),
        ],
    ]
    return InlineKeyboardMarkup(concern_buttons)


def sensitivity_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("کم", callback_data="sens_low"),
            InlineKeyboardButton("متوسط", callback_data="sens_medium"),
            InlineKeyboardButton("زیاد", callback_data="sens_high"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def clinics_keyboard() -> InlineKeyboardMarkup:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM clinics ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()

    if not rows:
        buttons = [[InlineKeyboardButton("کلینیک پیش‌فرض", callback_data="clinic_1")]]
    else:
        buttons = [
            [
                InlineKeyboardButton(
                    f"{row['name']} - {row['city']}",
                    callback_data=f"clinic_{row['id']}",
                )
            ]
            for row in rows
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
    buttons = []
    for i in range(0, 7):
        d = today + timedelta(days=i)
        buttons.append(
            [
                InlineKeyboardButton(
                    d.strftime("%Y-%m-%d"),
                    callback_data=f"date_{d.strftime('%Y-%m-%d')}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")])
    return InlineKeyboardMarkup(buttons)


def time_slots_keyboard(selected_date: str) -> InlineKeyboardMarkup:
    buttons = []
    for t in TIME_SLOTS:
        buttons.append(
            [InlineKeyboardButton(t, callback_data=f"time_{selected_date}_{t}")]
        )
    buttons.append(
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_dates")]
    )
    return InlineKeyboardMarkup(buttons)


def packages_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for code, info in TREATMENT_PACKAGES.items():
        buttons.append(
            [InlineKeyboardButton(info["title"], callback_data=f"pkg_{code}")]
        )
    buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")])
    return InlineKeyboardMarkup(buttons)


# ==================== Text Builders ====================

def format_user_profile(user_row: sqlite3.Row) -> str:
    tags = user_row["tags"] or ""
    allergies = user_row["allergies"] or "ثبت نشده"
    notes = user_row["important_notes"] or "ثبت نشده"
    ref_code = user_row["referral_code"] or "تعریف نشده"
    points = user_row["referral_points"] or 0
    is_vip = "✅" if points >= VIP_THRESHOLD_POINTS else "❌"

    text = f"👤 پروفایل شما:\n\n"
    text += f"نام: {user_row['full_name'] or 'ثبت نشده'}\n"
    text += f"شماره تماس: {user_row['phone_number'] or 'ثبت نشده'}\n"
    text += f"برچسب‌ها: {tags}\n"
    text += f"حساسیت‌ها / آلرژی‌ها: {allergies}\n"
    text += f"یادداشت‌های مهم: {notes}\n"
    text += f"کد معرف شما: {ref_code}\n"
    text += f"امتیاز معرف: {points}\n"
    text += f"وضعیت VIP: {is_vip}\n"
    return text


def build_skin_consultation_text(
    skin_type_key: str,
    skin_concern_key: str,
    sensitivity_key: str,
) -> Dict[str, str]:
    base_key = (skin_type_key, skin_concern_key, sensitivity_key)
    data = TREATMENT_SUGGESTIONS.get(base_key)

    if not data:
        title = "مشاوره پوستی اختصاصی شما"
        body = (
            f"نوع پوست: {SKIN_TYPES.get(skin_type_key, 'نامشخص')}\n"
            f"مشکل اصلی: {SKIN_CONCERNS.get(skin_concern_key, 'نامشخص')}\n"
            f"میزان حساسیت: {SENSITIVITY_LEVELS.get(sensitivity_key, 'نامشخص')}\n\n"
            "در حال حاضر دیتا برای این ترکیب به‌صورت اختصاصی تنظیم نشده؛ "
            "اما می‌توانید با کلینیک برای مشاوره تخصصی تماس بگیرید."
        )
        return {"title": title, "body": body}

    text_lines = []
    text_lines.append(f"✨ {data['title']}\n")
    text_lines.append("روتین صبح:\n")
    for step in data["routine_morning"]:
        text_lines.append(f"• {step}")
    text_lines.append("\nروتین شب:\n")
    for step in data["routine_night"]:
        text_lines.append(f"• {step}")
    text_lines.append("\nدرمان‌های پیشنهادی در کلینیک:\n")
    for step in data["clinic_treatments"]:
        text_lines.append(f"• {step}")
    text_lines.append(f"\nنکات مهم:\n{data['notes']}")

    return {"title": data["title"], "body": "\n".join(text_lines)}


def build_appointment_summary(row: sqlite3.Row) -> str:
    return (
        f"📌 نوبت شماره {row['id']}:\n"
        f"نام خدمت: {row['service_name']}\n"
        f"تاریخ: {row['date']} - ساعت: {row['time']}\n"
        f"پزشک: {row['doctor_name']}\n"
        f"وضعیت: {row['status']}\n"
    )


# ==================== Command Handlers ====================

async def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user = update.effective_user
    full_name = user.full_name

    db_user = get_or_create_user(chat_id, full_name)
    ensure_admin_user()

    text = (
        f"سلام {full_name} 🌸\n"
        f"به ربات {CLINIC_NAME} (نسخه PRO) خوش آمدید.\n\n"
        "لطفاً از منوی زیر گزینه مورد نظر را انتخاب کنید."
    )
    await update.message.reply_text(
        text, reply_markup=main_menu_keyboard(is_admin(db_user["chat_id"]))
    )


async def help_command(update: Update, context: CallbackContext):
    text = (
        "راهنمای ربات:\n"
        "• /start - شروع مجدد\n"
        "• رزرو نوبت از طریق منوی اصلی\n"
        "• مشاهده پروفایل و لینک معرف از منوی اصلی\n"
        "• پنل مدیریت مخصوص ادمین‌ها\n"
    )
    await update.message.reply_text(text)


# ==================== Callback Router ====================

async def callback_router(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = query.message.chat_id

    user_row = get_or_create_user(chat_id, query.from_user.full_name)
    admin_flag = is_admin(chat_id)

    if data == "menu_reserve":
        await show_reserve_menu(query, user_row)
    elif data == "menu_payment":
        await show_payment_menu(query, user_row)
    elif data == "menu_consult":
        await start_skin_consult(query, user_row)
    elif data == "menu_packages":
        await show_packages_menu(query, user_row)
    elif data == "menu_profile":
        await show_profile(query, user_row)
    elif data == "menu_referral":
        await show_referral_menu(query, user_row)
    elif data == "menu_admin":
        if admin_flag:
            await show_admin_menu(query)
        else:
            await query.message.reply_text("شما دسترسی ادمین ندارید.")

    elif data.startswith("clinic_"):
        await handle_clinic_select(query, data, user_row)

    elif data.startswith("service_"):
        await handle_service_select(query, data, user_row)

    elif data == "back_to_main":
        await query.message.edit_text(
            "بازگشت به منوی اصلی ✅",
            reply_markup=main_menu_keyboard(admin_flag),
        )

    elif data == "admin_dashboard":
        if admin_flag:
            await show_admin_dashboard(query)
    elif data == "admin_users":
        if admin_flag:
            await show_admin_users(query)
    elif data == "admin_appointments":
        if admin_flag:
            await show_admin_appointments(query)
    elif data == "admin_payments":
        if admin_flag:
            await show_admin_payments(query)
    elif data == "admin_consults":
        if admin_flag:
            await show_admin_consults(query)
    elif data == "admin_packages":
        if admin_flag:
            await show_admin_packages(query)
    elif data == "admin_broadcast":
        if admin_flag:
            await ask_broadcast_text(query)

    elif data.startswith("date_"):
        await handle_date_select(query, data, user_row)

    elif data.startswith("time_"):
        await handle_time_select(query, data, user_row)

    elif data == "offline_payment":
        await show_offline_payment_instructions(query, user_row)

    elif data.startswith("skin_type_"):
        await handle_skin_type_select(query, data, user_row)

    elif data.startswith("concern_"):
        await handle_skin_concern_select(query, data, user_row)

    elif data.startswith("sens_"):
        await handle_sensitivity_select(query, data, user_row)

    elif data.startswith("pkg_"):
        await handle_package_select(query, data, user_row)

    elif data == "enter_referral":
        await ask_referral_code(query, user_row)

    elif data == "my_referral_link":
        await show_my_referral_link(query, user_row)

    elif data == "enter_allergies":
        await ask_allergies(query, user_row)

    elif data == "enter_important_notes":
        await ask_important_notes(query, user_row)


# ==================== Message Handlers ====================

async def handle_text(update: Update, context: CallbackContext):
    message = update.message
    chat_id = message.chat_id
    text = message.text.strip()

    state_referral = get_user_state(chat_id, STATE_AWAITING_REFERRAL_CODE)
    state_broadcast = get_user_state(chat_id, STATE_AWAITING_BROADCAST_TEXT)
    state_allergies = get_user_state(chat_id, STATE_AWAITING_ALLERGIES)
    state_notes = get_user_state(chat_id, STATE_AWAITING_IMPORTANT_NOTES)

    if state_referral:
        await save_referral_code_from_text(update, text)
        return

    if state_broadcast and is_admin(chat_id):
        await handle_broadcast_text(update, text)
        return

    if state_allergies:
        await save_allergies_from_text(update, text)
        return

    if state_notes:
        await save_important_notes_from_text(update, text)
        return

    await update.message.reply_text(
        "پیام شما دریافت شد. برای استفاده از امکانات ربات، از منو استفاده کنید."
    )


async def handle_contact(update: Update, context: CallbackContext):
    contact = update.message.contact
    chat_id = update.message.chat_id

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET phone_number = ? WHERE chat_id = ?",
        (contact.phone_number, chat_id),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text("شماره تماس شما با موفقیت ثبت شد ✅")


async def handle_photo(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    state_receipt = get_user_state(chat_id, STATE_AWAITING_RECEIPT_PHOTO)

    if state_receipt:
        await update.message.reply_text(
            "رسید پرداخت شما دریافت شد ✅\n"
            "ادمین بعد از بررسی، وضعیت پرداخت را در سیستم تأیید می‌کند."
        )
        clear_user_state(chat_id, STATE_AWAITING_RECEIPT_PHOTO)
        return

    await update.message.reply_text(
        "عکس شما دریافت شد، ولی در حال حاضر در حالتی نیستید که رسید پرداخت ثبت شود."
    )


# ==================== Feature: رزرو نوبت ====================

async def show_reserve_menu(query, user_row):
    text = (
        "🗓 رزرو نوبت:\n\n"
        "ابتدا کلینیک را انتخاب کنید."
    )
    await query.message.edit_text(text, reply_markup=clinics_keyboard())


async def handle_clinic_select(query, data: str, user_row):
    clinic_id = int(data.split("_")[1])
    chat_id = query.message.chat_id

    set_user_state(chat_id, "selected_clinic_id", clinic_id)

    text = "نوع خدمت مورد نظر را انتخاب کنید:"
    await query.message.edit_text(text, reply_markup=services_keyboard())


async def handle_service_select(query, data: str, user_row):
    service_code = data.split("_", 1)[1]
    chat_id = query.message.chat_id

    set_user_state(chat_id, "selected_service_code", service_code)

    text = "لطفاً تاریخ مراجعه را انتخاب کنید:"
    await query.message.edit_text(text, reply_markup=date_keyboard())


async def handle_date_select(query, data: str, user_row):
    _, date_str = data.split("_", 1)
    chat_id = query.message.chat_id
    set_user_state(chat_id, "selected_date", date_str)
    text = f"تاریخ انتخاب‌شده: {date_str}\n\nلطفاً ساعت را انتخاب کنید:"
    await query.message.edit_text(text, reply_markup=time_slots_keyboard(date_str))


async def handle_time_select(query, data: str, user_row):
    parts = data.split("_", 2)
    _, date_str, time_str = parts
    chat_id = query.message.chat_id

    clinic_id = get_user_state(chat_id, "selected_clinic_id")
    service_code = get_user_state(chat_id, "selected_service_code")

    if not clinic_id or not service_code:
        await query.message.edit_text("❌ خطا: اطلاعات نوبت کامل نیست. دوباره تلاش کنید.")
        return

    service_name = {
        "Botox": "بوتاکس",
        "Filler": "فیلر",
        "Laser": "لیزر",
        "Meso": "مزوتراپی",
    }.get(service_code, service_code)

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO appointments (user_id, clinic_id, service_name, doctor_name, date, time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_row["id"],
            clinic_id,
            service_name,
            DOCTORS[0],
            date_str,
            time_str,
        ),
    )
    conn.commit()
    appointment_id = c.lastrowid
    conn.close()

    summary = (
        f"✅ نوبت شما ثبت شد.\n\n"
        f"شماره نوبت: {appointment_id}\n"
        f"خدمت: {service_name}\n"
        f"تاریخ: {date_str}\n"
        f"ساعت: {time_str}\n"
        f"پزشک: {DOCTORS[0]}\n\n"
        "برای مشاهده نوبت‌های بعدی، از منوی اصلی استفاده کنید."
    )

    await query.message.edit_text(summary, reply_markup=main_menu_keyboard(is_admin(chat_id)))


# ==================== Feature: پرداخت ====================

async def show_payment_menu(query, user_row):
    text = (
        "💳 پرداخت هزینه خدمات:\n\n"
        "در این نسخه، پرداخت آنلاین به‌صورت نمایشی است و پول واقعی جابه‌جا نمی‌شود.\n"
        "برای تست و استفاده:\n"
        "• پرداخت آفلاین (کارت به کارت) را انتخاب کنید.\n"
    )
    buttons = [
        [InlineKeyboardButton("پرداخت آفلاین (کارت به کارت)", callback_data="offline_payment")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")],
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def show_offline_payment_instructions(query, user_row):
    text = (
        "💳 پرداخت آفلاین (کارت به کارت):\n\n"
        f"شماره کارت:\n{OFFLINE_CARD_NUMBER}\n"
        f"به نام: {OFFLINE_CARD_OWNER}\n\n"
        "بعد از انجام واریز، لطفاً تصویر رسید را برای ربات ارسال کنید "
        "تا توسط ادمین بررسی و تأیید شود."
    )
    set_user_state(query.message.chat_id, STATE_AWAITING_RECEIPT_PHOTO, True)
    await query.message.edit_text(text)


# ==================== Feature: مشاوره پوستی هوشمند ====================

async def start_skin_consult(query, user_row):
    chat_id = query.message.chat_id
    clear_user_state(chat_id, STATE_AWAITING_SKIN_TYPE)
    clear_user_state(chat_id, STATE_AWAITING_SKIN_CONCERN)
    clear_user_state(chat_id, STATE_AWAITING_SENSITIVITY)

    text = "لطفاً نوع پوست خود را انتخاب کنید:"
    await query.message.edit_text(text, reply_markup=skin_consult_keyboard())


async def handle_skin_type_select(query, data: str, user_row):
    chat_id = query.message.chat_id
    skin_type_key = data.split("_", 2)[2]
    set_user_state(chat_id, "skin_type_key", skin_type_key)

    text = "مشکل اصلی پوست خود را انتخاب کنید:"
    await query.message.edit_text(text, reply_markup=skin_concern_keyboard())


async def handle_skin_concern_select(query, data: str, user_row):
    chat_id = query.message.chat_id
    concern_key = data.split("_", 1)[1]
    set_user_state(chat_id, "skin_concern_key", concern_key)

    text = "میزان حساسیت پوست خود را مشخص کنید:"
    await query.message.edit_text(text, reply_markup=sensitivity_keyboard())


async def handle_sensitivity_select(query, data: str, user_row):
    chat_id = query.message.chat_id
    sens_key = data.split("_", 1)[1].replace("sens_", "")

    skin_type_key = get_user_state(chat_id, "skin_type_key")
    skin_concern_key = get_user_state(chat_id, "skin_concern_key")

    if not skin_type_key or not skin_concern_key:
        await query.message.edit_text("❌ اطلاعات مشاوره کامل نیست. لطفاً از ابتدا شروع کنید.")
        return

    consult_data = build_skin_consultation_text(
        skin_type_key, skin_concern_key, sens_key
    )

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO consultations (
            user_id, skin_type_key, skin_concern_key, sensitivity_key,
            suggestion_title, suggestion_text
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_row["id"],
            skin_type_key,
            skin_concern_key,
            sens_key,
            consult_data["title"],
            consult_data["body"],
        ),
    )
    conn.commit()
    conn.close()

    await query.message.edit_text(
        f"📋 {consult_data['title']}\n\n{consult_data['body']}",
        reply_markup=main_menu_keyboard(is_admin(chat_id)),
    )


# ==================== Feature: پکیج‌ها ====================

async def show_packages_menu(query, user_row):
    text = "📦 پکیج‌های درمانی در دسترس:"
    await query.message.edit_text(text, reply_markup=packages_keyboard())


async def handle_package_select(query, data: str, user_row):
    pkg_code = data.split("_", 1)[1]
    info = TREATMENT_PACKAGES.get(pkg_code)
    if not info:
        await query.message.edit_text("❌ پکیج انتخاب‌شده معتبر نیست.")
        return

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO packages (user_id, package_code, title, total_sessions)
        VALUES (?, ?, ?, ?)
        """,
        (
            user_row["id"],
            pkg_code,
            info["title"],
            info["total_sessions"],
        ),
    )
    conn.commit()
    conn.close()

    text = (
        f"✅ پکیج «{info['title']}» برای شما ثبت شد.\n"
        f"تعداد جلسات: {info['total_sessions']}\n"
        "در هر مراجعه، تعداد جلسات استفاده‌شده توسط کلینیک به‌روزرسانی می‌شود."
    )
    await query.message.edit_text(
        text,
        reply_markup=main_menu_keyboard(is_admin(query.message.chat_id)),
    )


async def show_profile(query, user_row):
    text = format_user_profile(user_row)
    await query.message.edit_text(
        text, reply_markup=main_menu_keyboard(is_admin(query.message.chat_id))
    )


# ==================== Feature: Referral / لینک من ====================

def generate_referral_code(user_id: int) -> str:
    return f"GLR{user_id:05d}"


async def show_referral_menu(query, user_row):
    chat_id = query.message.chat_id
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

    referral_link = f"https://t.me/{CLINIC_NAME.replace(' ', '')}_bot?start={ref_code}"

    text = (
        "📣 لینک من / کد معرف:\n\n"
        f"کد معرف شما: {ref_code}\n"
        f"امتیازهای فعلی: {points}\n\n"
        f"لینک دعوت:\n{referral_link}\n\n"
        "این لینک را برای دوستان خود بفرستید؛ در صورت ثبت‌نام، امتیاز دریافت می‌کنید."
    )
    buttons = [
        [InlineKeyboardButton("ثبت کد معرف دیگران", callback_data="enter_referral")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")],
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def ask_referral_code(query, user_row):
    chat_id = query.message.chat_id
    set_user_state(chat_id, STATE_AWAITING_REFERRAL_CODE, True)
    await query.message.edit_text(
        "لطفاً کد معرف دوست خود را ارسال کنید (مثلاً: GLR00012)."
    )


async def save_referral_code_from_text(update: Update, text: str):
    chat_id = update.message.chat_id
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, referral_code, referred_by_user_id FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        clear_user_state(chat_id, STATE_AWAITING_REFERRAL_CODE)
        await update.message.reply_text("❌ خطا در یافتن پروفایل کاربر.")
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
        await update.message.reply_text("نمی‌توانید خودتان را به عنوان معرف ثبت کنید.")
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
        "✅ کد معرف با موفقیت ثبت شد. از همراهی شما سپاسگزاریم."
    )


async def show_my_referral_link(query, user_row):
    # (اگر خواستی جداگانه پیاده‌سازی کنی)
    await show_referral_menu(query, user_row)


# ==================== Feature: Allergies & Notes ====================

async def ask_allergies(query, user_row):
    chat_id = query.message.chat_id
    set_user_state(chat_id, STATE_AWAITING_ALLERGIES, True)
    await query.message.edit_text(
        "لطفاً حساسیت‌ها و آلرژی‌های مهم خود را به‌صورت متنی وارد کنید."
    )


async def save_allergies_from_text(update: Update, text: str):
    chat_id = update.message.chat_id
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET allergies = ? WHERE chat_id = ?", (text, chat_id))
    conn.commit()
    conn.close()

    clear_user_state(chat_id, STATE_AWAITING_ALLERGIES)
    await update.message.reply_text("✅ حساسیت‌ها/آلرژی‌ها با موفقیت ثبت شد.")


async def ask_important_notes(query, user_row):
    chat_id = query.message.chat_id
    set_user_state(chat_id, STATE_AWAITING_IMPORTANT_NOTES, True)
    await query.message.edit_text(
        "لطفاً یادداشت‌های مهم (مثلاً نکات مربوط به پوست، ترجیحات، یا نکات پزشکی) را وارد کنید."
    )


async def save_important_notes_from_text(update: Update, text: str):
    chat_id = update.message.chat_id
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET important_notes = ? WHERE chat_id = ?", (text, chat_id)
    )
    conn.commit()
    conn.close()

    clear_user_state(chat_id, STATE_AWAITING_IMPORTANT_NOTES)
    await update.message.reply_text("✅ یادداشت‌های مهم در پروفایل شما ذخیره شد.")


# ==================== Feature: Admin Panel ====================

async def show_admin_menu(query):
    await query.message.edit_text("🛠 پنل مدیریت:", reply_markup=admin_menu_keyboard())


async def show_admin_dashboard(query):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM users")
    users_cnt = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM appointments")
    app_cnt = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM payments")
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
        text = "👥 هنوز کاربری ثبت نشده است."
    else:
        lines = ["👥 آخرین کاربران ثبت‌شده:\n"]
        for r in rows:
            lines.append(
                f"- [{r['id']}] {r['full_name']} / {r['phone_number'] or 'بدون شماره'} / امتیاز معرف: {r['referral_points']}"
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
        text = "💳 هنوز پرداختی ثبت نشده است."
    else:
        lines = ["💳 آخرین پرداخت‌ها:\n"]
        for r in rows:
            lines.append(
                f"- #{r['id']} | {r['full_name']} | مبلغ: {r['amount']} | وضعیت: {r['status']} | روش: {r['method']}"
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
                f"- #{r['id']} | {r['full_name']} | {r['suggestion_title']} | {r['created_at']}"
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
        "لطفاً متن پیام گروهی را ارسال کنید. (برای لغو، چیزی مانند /cancel بفرستید.)"
    )


async def handle_broadcast_text(update: Update, text: str):
    chat_id = update.message.chat_id
    if text.strip().startswith("/cancel"):
        clear_user_state(chat_id, STATE_AWAITING_BROADCAST_TEXT)
        await update.message.reply_text("ارسال پیام گروهی لغو شد.")
        return

    users = get_all_users()
    sent = 0
    for u in users:
        try:
            await update.get_bot().send_message(
                chat_id=u["chat_id"],
                text=text,
            )
            sent += 1
        except Exception as e:
            logger.exception("خطا در ارسال پیام گروهی: %s", e)

    clear_user_state(chat_id, STATE_AWAITING_BROADCAST_TEXT)
    await update.message.reply_text(
        f"پیام گروهی ارسال شد. تعداد دریافت‌کنندگان: {sent}"
    )


# ==================== Feature: Reminder & Recall Jobs ====================

async def reminder_job(context: CallbackContext):
    try:
        conn = get_conn()
        c = conn.cursor()

        now = datetime.now()
        soon = now + timedelta(hours=24)
        c.execute(
            """
            SELECT a.*, u.chat_id
            FROM appointments a
            LEFT JOIN users u ON a.user_id = u.id
            WHERE a.status = 'reserved'
              AND datetime(a.date || ' ' || a.time) BETWEEN ? AND ?
            """,
            (now.strftime("%Y-%m-%d %H:%M"), soon.strftime("%Y-%m-%d %H:%M")),
        )
        rows = c.fetchall()
        conn.close()

        for r in rows:
            msg = (
                "⏰ یادآوری نوبت:\n\n"
                f"خدمت: {r['service_name']}\n"
                f"تاریخ: {r['date']}\n"
                f"ساعت: {r['time']}\n"
                "لطفاً در صورت نیاز به لغو/تغییر، با کلینیک تماس بگیرید."
            )
            try:
                await context.bot.send_message(chat_id=r["chat_id"], text=msg)
            except Exception as e:
                logger.exception("خطا در ارسال یادآوری: %s", e)

    except Exception as e:
        logger.exception("خطای کلی در reminder_job: %s", e)


async def recall_job(context: CallbackContext):
    try:
        conn = get_conn()
        c = conn.cursor()
        today = datetime.now().date().strftime("%Y-%m-%d")
        c.execute(
            """
            SELECT a.*, u.chat_id
            FROM appointments a
            LEFT JOIN users u ON a.user_id = u.id
            WHERE a.recall_date = ?
              AND a.recall_sent = 0
            """,
            (today,),
        )
        rows = c.fetchall()
        conn.close()

        for a in rows:
            try:
                msg = (
                    "🔄 یادآوری دوره درمان:\n\n"
                    f"خدمت: {a['service_name']}\n"
                    f"تاریخ آخرین نوبت: {a['date']}\n\n"
                    "زمان مناسبی برای تمدید یا ادامه جلسات شماست.\n"
                    "در صورت تمایل، می‌توانیم برای تمدید نوبت جدید تنظیم کنیم. 🌿"
                )
                await context.bot.send_message(chat_id=a["chat_id"], text=msg)

                conn2 = get_conn()
                conn2.execute(
                    "UPDATE appointments SET recall_sent = 1 WHERE id = ?",
                    (a["id"],),
                )
                conn2.commit()
                conn2.close()
            except Exception as e:
                logger.exception("recall error: %s", e)
    except Exception as e:
        logger.exception("خطای کلی در recall_job: %s", e)


# ==================== main ====================

def main():
    # راه‌اندازی دیتابیس
    init_db()

    # ساخت اپلیکیشن تلگرام با توکن ربات
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # ثبت هندلرهای اصلی
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # راه‌اندازی JobQueue برای ریمایندرها و Recall (در صورت در دسترس بودن)
    job_queue = application.job_queue
    if job_queue is not None:
        job_queue.run_repeating(reminder_job, interval=600, first=60)
        job_queue.run_repeating(recall_job, interval=3600, first=300)
    else:
        logger.warning(
            "JobQueue در دسترس نیست. برای فعال شدن ریمایندر نوبت‌ها، "
            'پکیج را با "python-telegram-bot[job-queue]" نصب کنید.'
        )

    logger.info("PRO Bot started...")
    application.run_polling()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("❕ ربات با دستور شما متوقف شد.")
    except Exception as e:
        logger.exception("خطای کلی در اجرای ربات: %s", e)
