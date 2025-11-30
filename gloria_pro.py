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
import random
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ==================== CONFIG ====================

CLINIC_NAME = "Gloria Clinic"

# ⚠️ اینجا توکن واقعی ربات را از BotFather قرار بده
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


# کارت برای پرداخت آفلاین
CARD_NUMBER = "6037-XXXX-XXXX-XXXX"
CARD_OWNER = "نام صاحب حساب"

# اطلاعات ورود ادمین (می‌توانی عوضشان کنی)
ADMIN_CREDENTIALS: Dict[str, str] = {
    "admin": "1234",
}

# چند کلینیک (می‌توانی نام‌ها و شهرها را تغییر بدهی/اضافه کنی)
CLINICS: Dict[int, Dict[str, str]] = {
    1: {"name": "کلینیک مرکزی", "city": "تهران"},
    2: {"name": "کلینیک شعبه غرب", "city": "تهران"},
}

# خدمات کلینیک
SERVICES: Dict[str, Dict[str, Any]] = {
    "laser": {"title": "لیزر موهای زائد", "price": 800_000, "tag": "Laser", "recall_days": 30},
    "botox": {"title": "تزریق بوتاکس", "price": 1_500_000, "tag": "Botox", "recall_days": 120},
    "clean": {"title": "پاکسازی پوست حرفه‌ای", "price": 650_000, "tag": "SkinCare", "recall_days": 60},
    "meso": {"title": "مزوتراپی پوست", "price": 1_200_000, "tag": "Meso", "recall_days": 90},
}

# پکیج‌ها
PACKAGES: Dict[str, Dict[str, Any]] = {
    "pkg_young_3": {
        "title": "پکیج جوانسازی ۳ جلسه‌ای",
        "service_code": "meso",
        "total_sessions": 3,
        "price": 3_000_000,
    },
    "pkg_laser_6": {
        "title": "پکیج لیزر ۶ جلسه‌ای",
        "service_code": "laser",
        "total_sessions": 6,
        "price": 4_200_000,
    },
}

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
STATE_AWAITING_BROADCAST_TEXT = "awaiting_broadcast_text"
STATE_AWAITING_REFERRAL_CODE = "awaiting_referral_code"

DB_PATH = "clinic_pro.db"

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
            created_at TEXT,
            FOREIGN KEY(clinic_id) REFERENCES clinics(id)
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
            service_code TEXT,
            service_title TEXT,
            doctor_name TEXT,
            date TEXT,
            time TEXT,
            status TEXT,
            package_code TEXT,
            package_session INTEGER,
            created_at TEXT,
            pre24_sent INTEGER DEFAULT 0,
            pre3_sent INTEGER DEFAULT 0,
            postcare_sent INTEGER DEFAULT 0,
            rating_sent INTEGER DEFAULT 0,
            recall_sent INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(clinic_id) REFERENCES clinics(id)
        )
        """
    )

    # payments
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            clinic_id INTEGER,
            appointment_id INTEGER,
            amount INTEGER,
            currency TEXT DEFAULT 'IRT',
            method TEXT,
            status TEXT,
            receipt_file_id TEXT,
            online_authority TEXT,
            online_ref_id TEXT,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(appointment_id) REFERENCES appointments(id),
            FOREIGN KEY(clinic_id) REFERENCES clinics(id)
        )
        """
    )

    # consultations
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            clinic_id INTEGER,
            skin_type TEXT,
            problem TEXT,
            sensitivity TEXT,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(clinic_id) REFERENCES clinics(id)
        )
        """
    )

    # crm notes
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            clinic_id INTEGER,
            admin_chat_id INTEGER,
            note TEXT,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(clinic_id) REFERENCES clinics(id)
        )
        """
    )

    # ratings
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            clinic_id INTEGER,
            appointment_id INTEGER,
            score INTEGER,
            comment TEXT,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(appointment_id) REFERENCES appointments(id),
            FOREIGN KEY(clinic_id) REFERENCES clinics(id)
        )
        """
    )

    # user_packages
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS user_packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            clinic_id INTEGER,
            package_code TEXT,
            total_sessions INTEGER,
            used_sessions INTEGER DEFAULT 0,
            status TEXT,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(clinic_id) REFERENCES clinics(id)
        )
        """
    )

    conn.commit()

    # insert clinics if missing
    for cid, info in CLINICS.items():
        c.execute("SELECT id FROM clinics WHERE id = ?", (cid,))
        if not c.fetchone():
            c.execute(
                "INSERT INTO clinics (id, name, city) VALUES (?, ?, ?)",
                (cid, info["name"], info["city"]),
            )
    conn.commit()
    conn.close()


def get_user_by_chat(chat_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    conn.close()
    return row


def get_user_by_id(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row


def get_clinic(clinic_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM clinics WHERE id = ?", (clinic_id,))
    row = c.fetchone()
    conn.close()
    return row


def get_or_create_user(chat_id: int, full_name: Optional[str] = None, clinic_id: Optional[int] = None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    if row:
        conn.close()
        return row

    referral_code = f"GL{chat_id}{random.randint(100, 999)}"
    c.execute(
        """
        INSERT INTO users (chat_id, full_name, clinic_id, referral_code, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (chat_id, full_name or "", clinic_id, referral_code, datetime.utcnow().isoformat()),
    )
    conn.commit()
    c.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    conn.close()
    return row


def update_user_phone(chat_id: int, phone: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET phone_number = ? WHERE chat_id = ?", (phone, chat_id))
    conn.commit()
    conn.close()


def update_user_clinic(chat_id: int, clinic_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET clinic_id = ? WHERE chat_id = ?", (clinic_id, chat_id))
    conn.commit()
    conn.close()


def update_user_allergies(user_id: int, text: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET allergies = ? WHERE id = ?", (text, user_id))
    conn.commit()
    conn.close()


def set_user_tag(chat_id: int, tag: str, add: bool):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT tags FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    tags_str = row["tags"] or ""
    tags = {t.strip() for t in tags_str.split(",") if t.strip()}
    if add:
        tags.add(tag)
    else:
        tags.discard(tag)
    new_tags = ",".join(sorted(tags))
    c.execute("UPDATE users SET tags = ? WHERE chat_id = ?", (new_tags, chat_id))
    conn.commit()
    conn.close()


def add_service_tag_to_user(user_id: int, service_code: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT chat_id FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    chat_id = row["chat_id"]
    conn.close()
    tag = SERVICES.get(service_code, {}).get("tag")
    if tag:
        set_user_tag(chat_id, tag, add=True)


def create_appointment(
    user_id: int,
    clinic_id: int,
    service_code: str,
    doctor: str,
    date: str,
    time: str,
    package_code: Optional[str] = None,
    package_session: Optional[int] = None,
) -> int:
    service_title = SERVICES.get(service_code, {}).get("title", service_code)
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO appointments (
            user_id, clinic_id, service_code, service_title, doctor_name,
            date, time, status, package_code, package_session, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            clinic_id,
            service_code,
            service_title,
            doctor,
            date,
            time,
            "pending_payment",
            package_code,
            package_session,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    appt_id = c.lastrowid
    conn.close()
    return appt_id


def get_appointment_by_id(appt_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM appointments WHERE id = ?", (appt_id,))
    row = c.fetchone()
    conn.close()
    return row


def appointment_slot_taken(doctor: str, date: str, time: str) -> bool:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT COUNT(*) AS cnt FROM appointments
        WHERE doctor_name = ? AND date = ? AND time = ?
          AND status IN ('pending_payment','reserved','paid','package','confirmed')
        """,
        (doctor, date, time),
    )
    row = c.fetchone()
    conn.close()
    return (row["cnt"] or 0) > 0


def update_appointment_status(appt_id: int, status: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE appointments SET status = ? WHERE id = ?", (status, appt_id))
    conn.commit()
    conn.close()


def get_user_appointments(user_id: int, limit: int = 10):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM appointments WHERE user_id = ? ORDER BY date DESC, time DESC LIMIT ?",
        (user_id, limit),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_upcoming_appointment(user_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT * FROM appointments
        WHERE user_id = ? AND date >= ?
        ORDER BY date ASC, time ASC
        LIMIT 1
        """,
        (user_id, today),
    )
    row = c.fetchone()
    conn.close()
    return row


def create_payment(
    user_id: int,
    clinic_id: int,
    appointment_id: int,
    amount: int,
    method: str,
    status: str = "pending",
    receipt_file_id: Optional[str] = None,
    online_authority: Optional[str] = None,
) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO payments (
            user_id, clinic_id, appointment_id, amount, method, status,
            receipt_file_id, online_authority, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            clinic_id,
            appointment_id,
            amount,
            method,
            status,
            receipt_file_id,
            online_authority,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    pay_id = c.lastrowid
    conn.close()
    return pay_id


def update_payment_status(payment_id: int, status: str, ref_id: Optional[str] = None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE payments SET status = ?, online_ref_id = ? WHERE id = ?",
        (status, ref_id, payment_id),
    )
    conn.commit()
    conn.close()


def get_payment_by_id(payment_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    row = c.fetchone()
    conn.close()
    return row


def create_consultation(user_id: int, clinic_id: int, skin: str, problem: str, sens: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO consultations (user_id, clinic_id, skin_type, problem, sensitivity, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, clinic_id, skin, problem, sens, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def create_crm_note(user_id: int, clinic_id: int, admin_chat_id: int, note: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO crm_notes (user_id, clinic_id, admin_chat_id, note, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, clinic_id, admin_chat_id, note, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_crm_notes_for_user(user_id: int, limit: int = 10):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM crm_notes WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_last_users(limit: int = 20):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_last_appointments(limit: int = 20):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT a.*, u.full_name, cl.name AS clinic_name
        FROM appointments a
        LEFT JOIN users u ON a.user_id = u.id
        LEFT JOIN clinics cl ON a.clinic_id = cl.id
        ORDER BY a.date ASC, a.time ASC, a.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_upcoming_appointments(days_ahead: int = 14):
    today = datetime.now().strftime("%Y-%m-%d")
    future = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT a.*, u.full_name, cl.name AS clinic_name
        FROM appointments a
        LEFT JOIN users u ON a.user_id = u.id
        LEFT JOIN clinics cl ON a.clinic_id = cl.id
        WHERE a.date BETWEEN ? AND ?
        ORDER BY a.date ASC, a.time ASC
        """,
        (today, future),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_last_payments(limit: int = 20):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT p.*, u.full_name, cl.name AS clinic_name
        FROM payments p
        LEFT JOIN users u ON p.user_id = u.id
        LEFT JOIN clinics cl ON p.clinic_id = cl.id
        ORDER BY p.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_last_consultations(limit: int = 20):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT c.*, u.full_name, cl.name AS clinic_name
        FROM consultations c
        LEFT JOIN users u ON c.user_id = u.id
        LEFT JOIN clinics cl ON c.clinic_id = cl.id
        ORDER BY c.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_user_packages(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT * FROM user_packages
        WHERE user_id = ? AND status = 'active'
        ORDER BY id DESC
        """,
        (user_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def create_user_package(user_id: int, clinic_id: int, package_code: str):
    pkg = PACKAGES.get(package_code)
    if not pkg:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO user_packages (user_id, clinic_id, package_code, total_sessions, used_sessions, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            clinic_id,
            package_code,
            pkg["total_sessions"],
            0,
            "active",
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def use_session_from_package(user_id: int, package_code: str) -> Optional[int]:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT * FROM user_packages
        WHERE user_id = ? AND package_code = ? AND status = 'active'
        ORDER BY id ASC
        """,
        (user_id, package_code),
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    used = row["used_sessions"] + 1
    total = row["total_sessions"]
    status = "active"
    if used >= total:
        status = "completed"
    c.execute(
        "UPDATE user_packages SET used_sessions = ?, status = ? WHERE id = ?",
        (used, status, row["id"]),
    )
    conn.commit()
    conn.close()
    return used


def insert_rating(user_id: int, clinic_id: int, appointment_id: int, score: int, comment: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO ratings (user_id, clinic_id, appointment_id, score, comment, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, clinic_id, appointment_id, score, comment, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_stats():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS cnt FROM users")
    users_count = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) AS cnt FROM appointments")
    appts_count = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) AS cnt FROM appointments WHERE status IN ('paid','package')")
    appts_done = c.fetchone()["cnt"]
    c.execute("SELECT SUM(amount) AS total FROM payments WHERE status = 'paid'")
    rev_row = c.fetchone()
    revenue = rev_row["total"] or 0

    c.execute(
        """
        SELECT full_name, referral_points
        FROM users
        WHERE referral_points > 0
        ORDER BY referral_points DESC
        LIMIT 5
        """
    )
    top_ref = c.fetchall()

    conn.close()
    return users_count, appts_count, appts_done, revenue, top_ref


def appointment_datetime(appt_row: sqlite3.Row) -> Optional[datetime]:
    try:
        return datetime.strptime(f"{appt_row['date']} {appt_row['time']}", "%Y-%m-%d %H:%M")
    except Exception:
        return None


def add_referral(new_user_id: int, referral_code: str) -> bool:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE referral_code = ?", (referral_code,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    referrer_id = row["id"]
    if referrer_id == new_user_id:
        conn.close()
        return False
    c.execute(
        "UPDATE users SET referred_by_user_id = ? WHERE id = ?",
        (referrer_id, new_user_id),
    )
    c.execute(
        "UPDATE users SET referral_points = referral_points + 1 WHERE id = ?",
        (referrer_id,),
    )
    conn.commit()
    conn.close()
    return True


# ==================== Keyboards ====================

def clinics_keyboard():
    buttons = []
    for cid, info in CLINICS.items():
        buttons.append([InlineKeyboardButton(info["name"], callback_data=f"clinic_{cid}")])
    return InlineKeyboardMarkup(buttons)


def main_menu_kb():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🗓 رزرو نوبت", callback_data="menu_booking")],
            [InlineKeyboardButton("💳 پرداخت", callback_data="menu_payment")],
            [InlineKeyboardButton("🩺 مشاوره پوستی هوشمند", callback_data="menu_consult")],
            [InlineKeyboardButton("👤 پروفایل من", callback_data="menu_profile")],
            [InlineKeyboardButton("👤 نوبت‌های من", callback_data="menu_my_appts")],
            [InlineKeyboardButton("🎁 کد معرف / لینک من", callback_data="menu_referral")],
            [InlineKeyboardButton("❓ سوالات پرتکرار", callback_data="menu_faq")],
            [InlineKeyboardButton("ℹ️ درباره کلینیک", callback_data="menu_about")],
            [InlineKeyboardButton("🔐 پنل مدیریت", callback_data="menu_admin_login")],
        ]
    )


def back_main_kb():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ بازگشت به منوی اصلی", callback_data="back_to_main")]]
    )


def admin_main_kb():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 داشبورد", callback_data="admin_dashboard")],
            [InlineKeyboardButton("👥 کاربران", callback_data="admin_users")],
            [InlineKeyboardButton("🗓 نوبت‌ها", callback_data="admin_appts")],
            [InlineKeyboardButton("📆 تقویم ۱۴ روز آینده", callback_data="admin_calendar")],
            [InlineKeyboardButton("💳 پرداخت‌ها", callback_data="admin_payments")],
            [InlineKeyboardButton("🩺 مشاوره‌ها", callback_data="admin_consults")],
            [InlineKeyboardButton("🎁 پکیج‌ها", callback_data="admin_packages")],
            [InlineKeyboardButton("📣 پیام گروهی", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🚪 خروج از پنل", callback_data="admin_logout")],
        ]
    )


def admin_back_kb():
    return admin_main_kb()


def faq_kb():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("قبل از لیزر چه کنم؟", callback_data="faq_before_laser")],
            [InlineKeyboardButton("بعد از لیزر چه کنم؟", callback_data="faq_after_laser")],
            [InlineKeyboardButton("بعد از مزوتراپی طبیعی است؟", callback_data="faq_after_meso")],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")],
        ]
    )


# ==================== Consultation Logic ====================

def build_consultation_answer(skin: str, problem: str, sens: str) -> str:
    skin_map = {
        "normal": "نرمال",
        "dry": "خشک",
        "oily": "چرب",
        "combo": "مختلط",
    }
    prob_map = {
        "acne": "جوش/آکنه",
        "spots": "لک و تیرگی",
        "aging": "چروک و پیری",
        "sensitive": "حساسیت و قرمزی",
    }
    sens_map = {
        "low": "کم",
        "medium": "متوسط",
        "high": "زیاد",
    }
    skin_t = skin_map.get(skin, skin)
    prob_t = prob_map.get(problem, problem)
    sens_t = sens_map.get(sens, sens)

    lines: List[str] = [
        "✅ نتیجه مشاوره پوستی اختصاصی شما:",
        "",
        f"• نوع پوست: {skin_t}",
        f"• مشکل اصلی: {prob_t}",
        f"• میزان حساسیت: {sens_t}",
        "",
    ]

    lines.append("🌅 روتین پیشنهادی صبح:")

    if skin == "oily":
        lines.append("• شست‌وشو با ژل ملایم مخصوص پوست چرب.")
        lines.append("• مرطوب‌کننده سبک و غیرکومدون‌زا.")
    elif skin == "dry":
        lines.append("• شوینده کرمی و بدون سولفات.")
        lines.append("• سرم آبرسان + کرم مرطوب‌کننده قوی‌تر.")
    elif skin == "combo":
        lines.append("• شوینده ملایم، کنترل چربی در ناحیه T.")
        lines.append("• مرطوب‌کننده سبک، در صورت نیاز روی نواحی خشک قوی‌تر.")
    else:
        lines.append("• شوینده ملایم و مرطوب‌کننده سبک برای پوست نرمال.")

    if problem == "acne":
        lines.append("• محصول حاوی سالیسیلیک‌اسید یا بنزوئیل‌پراکسید (با نظر پزشک).")
    elif problem == "spots":
        lines.append("• سرم روشن‌کننده (ویتامین C، نیاسینامید).")
    elif problem == "aging":
        lines.append("• آنتی‌اکسیدان صبح (ویتامین C) + کرم دور چشم سبک.")
    elif problem == "sensitive":
        lines.append("• فقط محصولات مخصوص پوست حساس، بدون عطر و الکل.")

    if sens == "high":
        lines.append("• هر محصول جدید را ابتدا روی قسمت کوچک تست کنید.")

    lines += ["", "🌙 روتین پیشنهادی شب:"]

    if skin == "oily":
        lines.append("• شست‌وشوی کامل برای حذف چربی و آلودگی.")
    elif skin == "dry":
        lines.append("• شوینده ملایم، سپس کرم یا بالم مغذی.")
    elif skin == "combo":
        lines.append("• شوینده ملایم، سپس آبرسان روی کل صورت.")
    else:
        lines.append("• شوینده ملایم و مرطوب‌کننده مناسب.")

    if problem == "acne":
        lines.append("• در صورت نسخه پزشک، رتینوئید موضعی شب‌ها.")
    elif problem == "spots":
        lines.append("• کرم تخصصی ضدلک شبانه (با نظر پزشک).")
    elif problem == "aging":
        lines.append("• کرم حاوی رتینول یا پپتید (با شروع تدریجی).")
    elif problem == "sensitive":
        lines.append("• تمرکز روی ترمیم‌کننده‌ها و پرهیز از اسیدهای قوی.")

    if sens == "high":
        lines.append("• از استفاده همزمان چند محصول فعال قوی خودداری کنید.")

    if skin == "oily" and problem == "acne":
        lines += [
            "",
            "💡 نکته مخصوص پوست چربِ جوش‌دار:",
            "• از کرم‌های سنگین و روغنی پرهیز کنید.",
            "• روبالشی و گوشی موبایل را مرتب تمیز کنید.",
        ]
    if skin == "dry" and problem == "aging":
        lines += [
            "",
            "💡 نکته مخصوص پوست خشک و چروک:",
            "• کم‌آبی پوست، چروک‌ها را عمیق‌تر نشان می‌دهد؛ آبرسانی منظم ضروری است.",
        ]
    if problem == "spots" and sens == "high":
        lines += [
            "",
            "💡 نکته برای لک همراه با حساسیت:",
            "• از معجون‌های خانگی اسیدی (لیمو، سرکه و...) پرهیز کنید.",
        ]

    lines += [
        "",
        "🔸 پیشنهاد خدمات در کلینیک:",
    ]
    if problem in ("acne", "spots"):
        lines.append("• پاکسازی حرفه‌ای، فیشال، و در صورت نیاز لیزر یا مزوتراپی.")
    if problem == "aging":
        lines.append("• مشاوره بوتاکس، مزوتراپی، جوانسازی غیرتهاجمی.")
    if problem == "sensitive":
        lines.append("• تنظیم روتین فوق‌العاده ملایم + درمان قرمزی در صورت نیاز.")

    lines += [
        "",
        f"در صورت تمایل می‌توانید از منوی «رزرو نوبت» یک مشاوره حضوری در {CLINIC_NAME} رزرو کنید. 🌿",
    ]

    return "\n".join(lines)


# ==================== User Handlers ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args or []
    referral_code = args[0] if args else None

    user = get_user_by_chat(chat_id)
    if not user:
        context.user_data["state"] = STATE_AWAITING_NAME
        context.user_data["pending_referral_code"] = referral_code
        await update.message.reply_text(
            f"سلام 👋\nبه ربات {CLINIC_NAME} خوش آمدید.\n\n"
            "لطفاً نام و نام خانوادگی خود را ارسال کنید.",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await update.message.reply_text(
            f"{user['full_name']} عزیز، خوش آمدید 🌷",
            reply_markup=ReplyKeyboardRemove(),
        )
        await update.message.reply_text("از منوی زیر استفاده کنید:", reply_markup=main_menu_kb())


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()
    state = context.user_data.get("state")
    logger.info("TEXT chat=%s state=%s text=%s", chat_id, state, text)

    # ثبت نام - نام
    if state == STATE_AWAITING_NAME:
        context.user_data["temp_name"] = text
        context.user_data["state"] = STATE_AWAITING_CLINIC
        await update.message.reply_text(
            "خیلی هم عالی 🙏\nحالا لطفاً کلینیک مورد نظر خود را انتخاب کنید:",
            reply_markup=clinics_keyboard(),
        )
        return

    # ثبت نام - شماره
    if state == STATE_AWAITING_PHONE:
        full_name = context.user_data.get("temp_name", "")
        clinic_id = context.user_data.get("temp_clinic_id")
        user = get_or_create_user(chat_id, full_name=full_name, clinic_id=clinic_id)
        update_user_phone(chat_id, text)
        ref_code = context.user_data.get("pending_referral_code")
        if ref_code:
            add_referral(user["id"], ref_code)
        context.user_data["state"] = None
        await update.message.reply_text("✅ ثبت‌نام شما با موفقیت انجام شد.", reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("از منوی زیر استفاده کنید:", reply_markup=main_menu_kb())
        return

    # لاگین ادمین - نام کاربری
    if state == STATE_ADMIN_USERNAME:
        context.user_data["admin_username"] = text
        context.user_data["state"] = STATE_ADMIN_PASSWORD
        await update.message.reply_text("🔑 لطفاً رمز عبور را ارسال کنید:")
        return

    # لاگین ادمین - پسورد
    if state == STATE_ADMIN_PASSWORD:
        username = context.user_data.get("admin_username")
        password = text
        if username in ADMIN_CREDENTIALS and ADMIN_CREDENTIALS[username] == password:
            context.user_data["is_admin"] = True
            context.user_data["state"] = None
            await update.message.reply_text("✅ ورود به پنل مدیریت موفق بود.")
            await update.message.reply_text("📊 پنل مدیریت:", reply_markup=admin_main_kb())
        else:
            context.user_data["state"] = None
            await update.message.reply_text("❌ نام کاربری یا رمز عبور اشتباه است.")
            await update.message.reply_text("منوی اصلی:", reply_markup=main_menu_kb())
        return

    # یادداشت CRM
    if state == STATE_AWAITING_CRM_NOTE:
        target_user_id = context.user_data.get("crm_target_user_id")
        if target_user_id:
            u = get_user_by_id(target_user_id)
            clinic_id = u["clinic_id"] if u else None
            create_crm_note(target_user_id, clinic_id, chat_id, text)
            context.user_data["state"] = None
            await update.message.reply_text("✅ یادداشت CRM ذخیره شد.", reply_markup=admin_back_kb())
        else:
            await update.message.reply_text("❌ کاربر هدف برای CRM یافت نشد.", reply_markup=admin_back_kb())
        return

    # حساسیت‌ها
    if state == STATE_AWAITING_ALLERGIES:
        target_user_id = context.user_data.get("allergy_target_user_id")
        if target_user_id:
            update_user_allergies(target_user_id, text)
            context.user_data["state"] = None
            await update.message.reply_text("✅ حساسیت‌ها/هشدارها ثبت شد.", reply_markup=admin_back_kb())
        else:
            await update.message.reply_text("❌ کاربر هدف یافت نشد.", reply_markup=admin_back_kb())
        return

    # پیام گروهی
    if state == STATE_AWAITING_BROADCAST_TEXT:
        segment = context.user_data.get("broadcast_segment")
        context.user_data["state"] = None
        await do_broadcast(context, chat_id, segment, text)
        return

    # کد معرف
    if state == STATE_AWAITING_REFERRAL_CODE:
        context.user_data["state"] = None
        user = get_user_by_chat(chat_id)
        if not user:
            await update.message.reply_text("ابتدا باید ثبت‌نام کنید. /start", reply_markup=back_main_kb())
            return
        ok = add_referral(user["id"], text)
        if ok:
            await update.message.reply_text(
                "✅ کد معرف با موفقیت ثبت شد. از همراهی شما متشکریم.",
                reply_markup=main_menu_kb(),
            )
        else:
            await update.message.reply_text(
                "❌ کد معرف نامعتبر است یا نمی‌توانید خودتان را به‌عنوان معرف ثبت کنید.",
                reply_markup=main_menu_kb(),
            )
        return

    # امتیازدهی ۱ تا ۵
    try:
        score = int(text)
        if 1 <= score <= 5:
            user = get_user_by_chat(chat_id)
            if user:
                appts = get_user_appointments(user["id"], limit=1)
                if appts:
                    appt = appts[0]
                    insert_rating(user["id"], user["clinic_id"], appt["id"], score, "")
                    await update.message.reply_text("⭐️ ممنون از امتیاز شما.", reply_markup=main_menu_kb())
                    return
    except Exception:
        pass

    # حالت پیش‌فرض
    await update.message.reply_text("لطفاً از منوی زیر انتخاب کنید:", reply_markup=main_menu_kb())


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = context.user_data.get("state")
    if state == STATE_AWAITING_PHONE and update.message.contact:
        full_name = context.user_data.get("temp_name", update.message.from_user.full_name)
        phone = update.message.contact.phone_number
        clinic_id = context.user_data.get("temp_clinic_id")
        user = get_or_create_user(chat_id, full_name=full_name, clinic_id=clinic_id)
        update_user_phone(chat_id, phone)
        ref_code = context.user_data.get("pending_referral_code")
        if ref_code:
            add_referral(user["id"], ref_code)
        context.user_data["state"] = None
        await update.message.reply_text("✅ ثبت‌نام شما کامل شد.", reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("از منوی زیر استفاده کنید:", reply_markup=main_menu_kb())
    else:
        await update.message.reply_text("این شماره را در این مرحله نیاز ندارم. از منو استفاده کنید.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = context.user_data.get("state")
    if state == STATE_AWAITING_RECEIPT_PHOTO:
        appt_id = context.user_data.get("receipt_appt_id")
        user = get_user_by_chat(chat_id)
        if not user or not appt_id:
            await update.message.reply_text("❌ نوبت یا کاربر یافت نشد.", reply_markup=back_main_kb())
            return
        appt = get_appointment_by_id(appt_id)
        if not appt:
            await update.message.reply_text("❌ نوبت یافت نشد.", reply_markup=back_main_kb())
            return
        service_code = appt["service_code"]
        amount = SERVICES.get(service_code, {}).get("price", 500_000)
        photo = update.message.photo[-1]
        file_id = photo.file_id
        create_payment(
            user_id=appt["user_id"],
            clinic_id=appt["clinic_id"],
            appointment_id=appt_id,
            amount=amount,
            method="offline",
            status="pending",
            receipt_file_id=file_id,
        )
        context.user_data["state"] = None
        await update.message.reply_text(
            "✅ تصویر رسید دریافت و برای بررسی ثبت شد.\n"
            "پس از تأیید توسط ادمین، نوبت شما قطعی می‌شود.",
            reply_markup=main_menu_kb(),
        )
    else:
        await update.message.reply_text("این عکس در این مرحله لازم نبود. از منو استفاده کنید.")


# ==================== Broadcast Helper ====================

async def do_broadcast(context: ContextTypes.DEFAULT_TYPE, admin_chat_id: int, segment: str, text: str):
    conn = get_conn()
    c = conn.cursor()
    if segment == "ALL":
        c.execute("SELECT chat_id FROM users")
    else:
        like = f"%{segment}%"
        c.execute("SELECT chat_id FROM users WHERE tags LIKE ?", (like,))
    rows = c.fetchall()
    conn.close()

    app: Application = context.application  # type: ignore
    success = 0
    for r in rows:
        try:
            await app.bot.send_message(chat_id=r["chat_id"], text=text)
            success += 1
        except Exception as e:
            logger.exception("broadcast error to %s: %s", r["chat_id"], e)

    try:
        await app.bot.send_message(
            chat_id=admin_chat_id,
            text=f"پیام برای {success} کاربر در گروه {segment} ارسال شد.",
        )
    except Exception:
        pass


# ==================== Callback Router ====================

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id
    logger.info("CALLBACK data=%s chat=%s", data, chat_id)

    # برگشت به منوی اصلی
    if data == "back_to_main":
        await query.message.reply_text("منوی اصلی:", reply_markup=main_menu_kb())
        return

    # انتخاب کلینیک در ثبت‌نام
    if data.startswith("clinic_"):
        cid = int(data.replace("clinic_", ""))
        context.user_data["temp_clinic_id"] = cid
        context.user_data["state"] = STATE_AWAITING_PHONE
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 ارسال شماره من", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await query.message.reply_text(
            "لطفاً شماره موبایل خود را ارسال کنید یا روی دکمه زیر بزنید:",
            reply_markup=kb,
        )
        return

    # ---------- Booking ----------
    if data == "menu_booking":
        buttons = [
            [InlineKeyboardButton(f"{info['title']} - {info['price']:,} تومان", callback_data=f"svc_{code}")]
            for code, info in SERVICES.items()
        ]
        buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")])
        await query.message.reply_text(
            "لطفاً خدمت مورد نظر را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data.startswith("svc_"):
        service_code = data.replace("svc_", "")
        context.user_data["booking"] = {"service_code": service_code}
        buttons = [
            [InlineKeyboardButton(name, callback_data=f"doc_{i}")]
            for i, name in enumerate(DOCTORS)
        ]
        buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_booking")])
        await query.message.reply_text("پزشک مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("doc_"):
        idx = int(data.replace("doc_", ""))
        if idx < 0 or idx >= len(DOCTORS):
            await query.message.reply_text("❌ پزشک نامعتبر.", reply_markup=back_main_kb())
            return
        booking = context.user_data.get("booking", {})
        booking["doctor"] = DOCTORS[idx]
        context.user_data["booking"] = booking

        buttons = []
        today = datetime.now()
        for i in range(7):
            d = today + timedelta(days=i + 1)
            label = d.strftime("%Y-%m-%d")
            buttons.append([InlineKeyboardButton(label, callback_data=f"date_{label}")])
        buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_booking")])
        await query.message.reply_text("تاریخ را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("date_"):
        date_str = data.replace("date_", "")
        booking = context.user_data.get("booking", {})
        booking["date"] = date_str
        context.user_data["booking"] = booking

        doctor = booking.get("doctor")
        buttons = []
        for t in TIME_SLOTS:
            if appointment_slot_taken(doctor, date_str, t):
                label = f"{t} (پر)"
                buttons.append([InlineKeyboardButton(label, callback_data="noop")])
            else:
                buttons.append([InlineKeyboardButton(t, callback_data=f"time_{t.replace(':','')}")])
        buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_booking")])
        await query.message.reply_text(
            f"تاریخ انتخاب‌شده: {date_str}\n\nلطفاً ساعت را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data == "noop":
        await query.answer("این ساعت پر است.", show_alert=True)
        return

    if data.startswith("time_"):
        time_code = data.replace("time_", "")
        time_str = f"{time_code[:2]}:{time_code[2:]}"
        booking = context.user_data.get("booking", {})
        booking["time"] = time_str
        context.user_data["booking"] = booking

        user = get_user_by_chat(chat_id)
        if not user:
            await query.message.reply_text("ابتدا باید ثبت‌نام کنید. /start", reply_markup=back_main_kb())
            return
        if not user["clinic_id"]:
            await query.message.reply_text(
                "کلینیک شما مشخص نیست. لطفاً دوباره /start را بزنید.",
                reply_markup=back_main_kb(),
            )
            return

        clinic_id = user["clinic_id"]
        service_code = booking.get("service_code")
        doctor = booking.get("doctor")
        date_str = booking.get("date")
        if not (service_code and doctor and date_str):
            await query.message.reply_text(
                "❌ خطا در اطلاعات نوبت، لطفاً از ابتدا رزرو را انجام دهید.",
                reply_markup=back_main_kb(),
            )
            return

        if appointment_slot_taken(doctor, date_str, time_str):
            await query.message.reply_text("❌ این ساعت همین لحظه پر شد. لطفاً ساعت دیگری انتخاب کنید.", reply_markup=back_main_kb())
            return

        # چک پکیج فعال برای این خدمت
        user_packs = get_user_packages(user["id"])
        pkg_for_service = None
        for up in user_packs:
            info = PACKAGES.get(up["package_code"])
            if info and info["service_code"] == service_code and up["status"] == "active":
                pkg_for_service = up["package_code"]
                break

        try:
            appt_id = create_appointment(
                user_id=user["id"],
                clinic_id=clinic_id,
                service_code=service_code,
                doctor=doctor,
                date=date_str,
                time=time_str,
            )
        except Exception as e:
            logger.exception("create_appointment error: %s", e)
            await query.message.reply_text(f"❌ خطا در ثبت نوبت: {e}", reply_markup=back_main_kb())
            return

        service_title = SERVICES.get(service_code, {}).get("title", service_code)
        amount = SERVICES.get(service_code, {}).get("price", 500_000)

        text = (
            "✅ نوبت شما موقتاً ثبت شد.\n\n"
            f"خدمت: {service_title}\n"
            f"پزشک: {doctor}\n"
            f"تاریخ: {date_str}\n"
            f"ساعت: {time_str}\n"
        )

        buttons = []
        if pkg_for_service:
            text += "\nشما یک پکیج فعال برای این خدمت دارید. مایلید از پکیج استفاده کنید یا برای این نوبت پرداخت جداگانه انجام دهید؟"
            buttons.append(
                [
                    InlineKeyboardButton("🎁 استفاده از پکیج", callback_data=f"usepkg_{appt_id}_{pkg_for_service}"),
                    InlineKeyboardButton("💳 پرداخت این نوبت", callback_data=f"pay_appt_{appt_id}"),
                ]
            )
        else:
            text += f"\nمبلغ: {amount:,} تومان\n\nبرای پرداخت، روی دکمه زیر بزنید:"
            buttons.append([InlineKeyboardButton("💳 پرداخت این نوبت", callback_data=f"pay_appt_{appt_id}")])

        buttons.append([InlineKeyboardButton("⬅️ بازگشت به منوی اصلی", callback_data="back_to_main")])

        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("usepkg_"):
        _, appt_id_str, pkg_code = data.split("_", 2)
        appt_id = int(appt_id_str)
        appt = get_appointment_by_id(appt_id)
        if not appt:
            await query.message.reply_text("❌ نوبت یافت نشد.", reply_markup=back_main_kb())
            return
        session_no = use_session_from_package(appt["user_id"], pkg_code)
        if not session_no:
            await query.message.reply_text("❌ پکیج فعال برای این خدمت یافت نشد.", reply_markup=back_main_kb())
            return

        conn = get_conn()
        conn.execute(
            "UPDATE appointments SET status = 'package', package_code = ?, package_session = ? WHERE id = ?",
            (pkg_code, session_no, appt_id),
        )
        conn.commit()
        conn.close()

        add_service_tag_to_user(appt["user_id"], appt["service_code"])

        await query.message.reply_text(
            f"🎁 جلسه {session_no} از پکیج {PACKAGES[pkg_code]['title']} برای این نوبت استفاده شد.\n"
            "نوبت شما بدون پرداخت اضافه ثبت گردید.",
            reply_markup=back_main_kb(),
        )
        return

    # ---------- نوبت‌های من ----------
    if data == "menu_my_appts":
        user = get_user_by_chat(chat_id)
        if not user:
            await query.message.reply_text("ابتدا باید ثبت‌نام کنید. /start", reply_markup=back_main_kb())
            return
        appts = get_user_appointments(user["id"], limit=10)
        if not appts:
            await query.message.reply_text("هیچ نوبتی برای شما ثبت نشده است.", reply_markup=back_main_kb())
            return
        lines = []
        for a in appts:
            pkg_part = ""
            if a["status"] == "package":
                pkg_part = f" (پکیج، جلسه {a['package_session']})"
            lines.append(
                f"#{a['id']} | {a['service_title']}{pkg_part} | {a['date']} {a['time']} | وضعیت: {a['status']}"
            )
        await query.message.reply_text("نوبت‌های شما:\n\n" + "\n".join(lines), reply_markup=back_main_kb())
        return

    # ---------- پروفایل ----------
    if data == "menu_profile":
        user = get_user_by_chat(chat_id)
        if not user:
            await query.message.reply_text("ابتدا باید ثبت‌نام کنید. /start", reply_markup=back_main_kb())
            return
        tags = user["tags"] or ""
        tags_view = tags if tags else "—"
        clinic = get_clinic(user["clinic_id"]) if user["clinic_id"] else None
        clinic_name = clinic["name"] if clinic else "ثبت نشده"
        next_appt = get_upcoming_appointment(user["id"])
        lines = [
            f"👤 نام: {user['full_name']}",
            f"☎️ شماره: {user['phone_number'] or 'ثبت نشده'}",
            f"🏥 کلینیک: {clinic_name}",
            f"🏷 برچسب‌ها: {tags_view}",
            f"🎁 کد معرف اختصاصی شما: {user['referral_code']}",
        ]
        if next_appt:
            lines += [
                "",
                "🗓 نزدیک‌ترین نوبت شما:",
                f"- {next_appt['service_title']} با {next_appt['doctor_name']}",
                f"- تاریخ: {next_appt['date']} ساعت {next_appt['time']}",
                f"- وضعیت: {next_appt['status']}",
            ]
        await query.message.reply_text("\n".join(lines), reply_markup=back_main_kb())
        return

    # ---------- Referral ----------
    if data == "menu_referral":
        user = get_user_by_chat(chat_id)
        if not user:
            await query.message.reply_text("ابتدا باید ثبت‌نام کنید. /start", reply_markup=back_main_kb())
            return

        bot_username = (await query.get_bot()).username
        link = f"https://t.me/{bot_username}?start={user['referral_code']}"

        text = (
            "🎁 سیستم معرف:\n\n"
            f"کد معرف اختصاصی شما:\n`{user['referral_code']}`\n\n"
            "می‌توانید این لینک را برای دوستان خود بفرستید:\n"
            f"{link}\n\n"
            "هر کسی با این لینک یا کد ثبت‌نام کند، برای شما امتیاز معرف ثبت می‌شود. 🌸"
        )

        buttons = [
            [InlineKeyboardButton("ثبت کد معرف که از کسی گرفته‌ام", callback_data="enter_referral")],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")],
        ]

        await query.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown",
        )
        return

    if data == "enter_referral":
        context.user_data["state"] = STATE_AWAITING_REFERRAL_CODE
        await query.message.reply_text(
            "لطفاً کد معرف شخصی که شما را معرفی کرده وارد کنید:\n\n"
            "مثال: GL123456789\n\n"
            "اگر کدی ندارید، می‌توانید به منوی اصلی برگردید.",
            reply_markup=back_main_kb(),
        )
        return

    # ---------- FAQ ----------
    if data == "menu_faq":
        await query.message.reply_text("سوالات پرتکرار را انتخاب کنید:", reply_markup=faq_kb())
        return

    if data.startswith("faq_"):
        if data == "faq_before_laser":
            txt = (
                "❓ قبل از لیزر چه کارهایی انجام دهم؟\n\n"
                "• از آفتاب و سولاریوم حداقل دو هفته قبل خودداری کنید.\n"
                "• از کرم‌های برنزه‌کننده روی ناحیه هدف استفاده نکنید.\n"
                "• ناحیه را ۲۴ ساعت قبل اصلاح کنید (در صورت دستور کلینیک).\n"
                "• بدون کرم و آرایش به جلسه لیزر مراجعه کنید."
            )
        elif data == "faq_after_laser":
            txt = (
                "❓ بعد از لیزر چه مراقبت‌هایی لازم است؟\n\n"
                "• تا ۴۸ ساعت از آفتاب مستقیم، سونا و حمام داغ خودداری کنید.\n"
                "• از کرم ترمیم‌کننده و ضدآفتاب طبق دستور پزشک استفاده کنید.\n"
                "• در صورت قرمزی خفیف، از کمپرس سرد ملایم استفاده کنید."
            )
        else:  # faq_after_meso
            txt = (
                "❓ بعد از مزوتراپی چه عوارضی طبیعی است؟\n\n"
                "• قرمزی خفیف، حساسیت لمس و گاهی کبودی کوچک طبیعی است.\n"
                "• معمولاً طی چند روز برطرف می‌شود.\n"
                "• در صورت درد شدید، تورم زیاد یا علائم غیرعادی حتماً با کلینیک تماس بگیرید."
            )
        await query.message.reply_text(txt, reply_markup=faq_kb())
        return

    # ---------- About ----------
    if data == "menu_about":
        text = (
            f"ℹ️ درباره {CLINIC_NAME}\n\n"
            "این نسخه PRO ربات با امکانات رزرو، CRM، پکیج درمانی، چند شعبه و سیستم معرف است.\n"
        )
        await query.message.reply_text(text, reply_markup=back_main_kb())
        return

    # ---------- Payment menu ----------
    if data == "menu_payment":
        user = get_user_by_chat(chat_id)
        if not user:
            await query.message.reply_text("ابتدا باید ثبت‌نام کنید. /start", reply_markup=back_main_kb())
            return
        appts = get_user_appointments(user["id"], limit=10)
        if not appts:
            await query.message.reply_text("نوبتی برای پرداخت وجود ندارد.", reply_markup=back_main_kb())
            return
        buttons = []
        for a in appts:
            label = f"#{a['id']} - {a['service_title']} - {a['date']} {a['time']} ({a['status']})"
            buttons.append([InlineKeyboardButton(label, callback_data=f"pay_appt_{a['id']}")])
        buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")])
        await query.message.reply_text(
            "نوبت موردنظر برای پرداخت را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data.startswith("pay_appt_"):
        appt_id = int(data.replace("pay_appt_", ""))
        appt = get_appointment_by_id(appt_id)
        if not appt:
            await query.message.reply_text("❌ نوبت یافت نشد.", reply_markup=back_main_kb())
            return
        if appt["status"] == "package":
            await query.message.reply_text(
                "این نوبت از پکیج استفاده کرده و نیازی به پرداخت ندارد.",
                reply_markup=back_main_kb(),
            )
            return
        service_code = appt["service_code"]
        service_title = appt["service_title"]
        amount = SERVICES.get(service_code, {}).get("price", 500_000)
        text = (
            f"نوبت انتخاب‌شده:\n"
            f"خدمت: {service_title}\n"
            f"پزشک: {appt['doctor_name']}\n"
            f"تاریخ: {appt['date']} ساعت {appt['time']}\n"
            f"مبلغ: {amount:,} تومان\n\n"
            "روش پرداخت را انتخاب کنید:\n"
            f"💳 پرداخت آفلاین (کارت به کارت به شماره کارت {CARD_NUMBER} به نام {CARD_OWNER})\n"
            "پس از واریز، رسید را ارسال کنید.\n\n"
            "یا پرداخت آنلاین (فعلاً بدون اتصال مستقیم به درگاه؛ فقط ثبت درخواست پرداخت در سیستم)."
        )
        buttons = [
            [InlineKeyboardButton("📷 ارسال رسید (آفلاین)", callback_data=f"pay_offline_{appt_id}")],
            [InlineKeyboardButton("💳 ثبت پرداخت آنلاین", callback_data=f"pay_online_{appt_id}")],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_payment")],
        ]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("pay_offline_"):
        appt_id = int(data.replace("pay_offline_", ""))
        context.user_data["state"] = STATE_AWAITING_RECEIPT_PHOTO
        context.user_data["receipt_appt_id"] = appt_id
        await query.message.reply_text(
            f"لطفاً مبلغ را به شماره کارت {CARD_NUMBER} به نام {CARD_OWNER} واریز کرده و سپس تصویر رسید را ارسال کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="back_to_main")]]),
        )
        return

    if data.startswith("pay_online_"):
        appt_id = int(data.replace("pay_online_", ""))
        user = get_user_by_chat(chat_id)
        if not user:
            await query.message.reply_text("ابتدا باید ثبت‌نام کنید. /start", reply_markup=back_main_kb())
            return
        appt = get_appointment_by_id(appt_id)
        if not appt:
            await query.message.reply_text("❌ نوبت یافت نشد.", reply_markup=back_main_kb())
            return
        service_code = appt["service_code"]
        amount = SERVICES.get(service_code, {}).get("price", 500_000)

        # فقط ثبت به‌عنوان "درخواست پرداخت آنلاین" با وضعیت pending
        authority = f"AUTH-{random.randint(100000, 999999)}"
        create_payment(
            user_id=appt["user_id"],
            clinic_id=appt["clinic_id"],
            appointment_id=appt_id,
            amount=amount,
            method="online",
            status="pending",
            receipt_file_id=None,
            online_authority=authority,
        )

        await query.message.reply_text(
            "✅ درخواست پرداخت آنلاین شما ثبت شد.\n"
            "در این نسخه‌ی ربات، اتصال مستقیم به درگاه واقعی انجام نشده و پرداخت توسط ادمین در سیستم تأیید می‌شود.\n\n"
            f"کد پیگیری داخلی: {authority}",
            reply_markup=back_main_kb(),
        )
        return

    # ---------- Consultation ----------
    if data == "menu_consult":
        buttons = [
            [
                InlineKeyboardButton("نرمال", callback_data="c_skin_normal"),
                InlineKeyboardButton("خشک", callback_data="c_skin_dry"),
            ],
            [
                InlineKeyboardButton("چرب", callback_data="c_skin_oily"),
                InlineKeyboardButton("مختلط", callback_data="c_skin_combo"),
            ],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")],
        ]
        await query.message.reply_text("نوع پوست خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("c_skin_"):
        skin = data.replace("c_skin_", "")
        context.user_data["c_skin"] = skin
        buttons = [
            [
                InlineKeyboardButton("جوش/آکنه", callback_data="c_prob_acne"),
                InlineKeyboardButton("لک/تیرگی", callback_data="c_prob_spots"),
            ],
            [
                InlineKeyboardButton("چروک/پیری", callback_data="c_prob_aging"),
                InlineKeyboardButton("حساسیت/قرمزی", callback_data="c_prob_sensitive"),
            ],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_consult")],
        ]
        await query.message.reply_text("بیشترین مشکل پوست شما چیست؟", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("c_prob_"):
        prob = data.replace("c_prob_", "")
        context.user_data["c_prob"] = prob
        buttons = [
            [
                InlineKeyboardButton("کم", callback_data="c_sens_low"),
                InlineKeyboardButton("متوسط", callback_data="c_sens_medium"),
                InlineKeyboardButton("زیاد", callback_data="c_sens_high"),
            ],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="menu_consult")],
        ]
        await query.message.reply_text(
            "میزان حساسیت پوست خود را مشخص کنید:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data.startswith("c_sens_"):
        sens = data.replace("c_sens_", "")
        context.user_data["c_sens"] = sens
        user = get_user_by_chat(chat_id)
        skin = context.user_data.get("c_skin", "")
        prob = context.user_data.get("c_prob", "")
        if user:
            create_consultation(user["id"], user["clinic_id"], skin, prob, sens)
        answer = build_consultation_answer(skin, prob, sens)
        await query.message.reply_text(answer, reply_markup=back_main_kb())
        return

    # ---------- Admin login ----------
    if data == "menu_admin_login":
        context.user_data["state"] = STATE_ADMIN_USERNAME
        await query.message.reply_text(
            "👮‍♀️ لطفاً نام کاربری ادمین را ارسال کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_main")]]),
        )
        return

    # ---------- Admin panel ----------
    if data in ("admin_panel", "admin_dashboard"):
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        users_count, appts_count, appts_done, revenue, top_ref = get_stats()
        text = (
            "📊 داشبورد مدیریت:\n\n"
            f"👥 تعداد کاربران: {users_count}\n"
            f"🗓 کل نوبت‌ها: {appts_count}\n"
            f"✅ نوبت‌های نهایی (پرداخت/پکیج): {appts_done}\n"
            f"💰 مجموع پرداخت‌های تأییدشده: {revenue:,} تومان\n"
        )
        if top_ref:
            text += "\n🏆 برترین معرف‌ها:\n"
            for r in top_ref:
                text += f"- {r['full_name']} ({r['referral_points']} امتیاز)\n"
        await query.message.reply_text(text, reply_markup=admin_main_kb())
        return

    if data == "admin_logout":
        context.user_data["is_admin"] = False
        await query.message.reply_text("از پنل مدیریت خارج شدید.", reply_markup=back_main_kb())
        return

    if data == "admin_users":
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        users = get_last_users()
        if not users:
            await query.message.reply_text("هیچ کاربری ثبت نشده است.", reply_markup=admin_back_kb())
            return
        buttons = []
        for u in users:
            label = f"#{u['id']} | {u['full_name']} ({u['phone_number'] or '-'})"
            buttons.append([InlineKeyboardButton(label, callback_data=f"admin_user_{u['id']}")])
        buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_panel")])
        await query.message.reply_text("لیست آخرین کاربران:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("admin_user_"):
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        uid = int(data.replace("admin_user_", ""))
        u = get_user_by_id(uid)
        if not u:
            await query.message.reply_text("کاربر یافت نشد.", reply_markup=admin_back_kb())
            return
        clinic = get_clinic(u["clinic_id"]) if u["clinic_id"] else None
        clinic_name = clinic["name"] if clinic else "ثبت نشده"
        notes = get_crm_notes_for_user(uid)
        tags = u["tags"] or ""
        tag_view = tags if tags else "—"
        lines = [
            f"👤 {u['full_name']}",
            f"☎️ {u['phone_number'] or '-'}",
            f"🏥 کلینیک: {clinic_name}",
            f"🏷 برچسب‌ها: {tag_view}",
            f"🎁 کد معرف: {u['referral_code']}",
            f"⭐️ امتیاز معرف: {u['referral_points']}",
            "",
            f"⚠️ حساسیت‌ها / هشدارها:\n{u['allergies'] or 'ثبت نشده'}",
            "",
            "یادداشت‌های CRM:",
        ]
        if notes:
            for n in notes:
                lines.append(f"- {n['note']}")
        else:
            lines.append("یادداشتی ثبت نشده است.")
        buttons = [
            [
                InlineKeyboardButton("⭐ افزودن VIP", callback_data=f"admin_tag_vip_{u['chat_id']}"),
                InlineKeyboardButton("🚫 بلاک کردن", callback_data=f"admin_tag_block_{u['chat_id']}"),
            ],
            [
                InlineKeyboardButton("✏️ افزودن یادداشت", callback_data=f"crm_add_{uid}"),
                InlineKeyboardButton("⚕️ ثبت حساسیت‌ها", callback_data=f"allergy_{uid}"),
            ],
            [InlineKeyboardButton("📂 پرونده کامل بیمار", callback_data=f"fullrec_{uid}")],
            [InlineKeyboardButton("➕ اختصاص پکیج", callback_data=f"assignpkg_{uid}")],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_users")],
        ]
        await query.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("allergy_"):
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        uid = int(data.replace("allergy_", ""))
        context.user_data["state"] = STATE_AWAITING_ALLERGIES
        context.user_data["allergy_target_user_id"] = uid
        await query.message.reply_text(
            "متن حساسیت‌ها / هشدارهای مهم بیمار را ارسال کنید:",
            reply_markup=admin_back_kb(),
        )
        return

    if data.startswith("crm_add_"):
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        uid = int(data.replace("crm_add_", ""))
        context.user_data["state"] = STATE_AWAITING_CRM_NOTE
        context.user_data["crm_target_user_id"] = uid
        await query.message.reply_text("متن یادداشت CRM را ارسال کنید:", reply_markup=admin_back_kb())
        return

    if data.startswith("fullrec_"):
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        uid = int(data.replace("fullrec_", ""))
        u = get_user_by_id(uid)
        if not u:
            await query.message.reply_text("کاربر یافت نشد.", reply_markup=admin_back_kb())
            return
        clinic = get_clinic(u["clinic_id"]) if u["clinic_id"] else None
        clinic_name = clinic["name"] if clinic else "ثبت نشده"

        appts = get_user_appointments(uid, limit=20)
        cons_list = get_last_consultations(limit=100)
        cons_for_user = [c for c in cons_list if c["user_id"] == uid]
        notes = get_crm_notes_for_user(uid, limit=20)

        lines = [
            f"📂 پرونده کامل بیمار #{u['id']}",
            f"👤 {u['full_name']}",
            f"☎️ {u['phone_number'] or '-'}",
            f"🏥 کلینیک: {clinic_name}",
            f"🏷 برچسب‌ها: {u['tags'] or '—'}",
            f"⚠️ حساسیت‌ها: {u['allergies'] or 'ثبت نشده'}",
            f"🎁 کد معرف: {u['referral_code']}",
            f"⭐️ امتیاز معرف: {u['referral_points']}",
            "",
            "🗓 نوبت‌ها:",
        ]
        if appts:
            for a in appts:
                pkg_part = ""
                if a["status"] == "package":
                    pkg_part = f" (پکیج، جلسه {a['package_session']})"
                lines.append(
                    f"- {a['date']} {a['time']} | {a['service_title']} با {a['doctor_name']} | {a['status']}{pkg_part}"
                )
        else:
            lines.append("هیچ نوبتی ثبت نشده است.")

        lines.append("")
        lines.append("🩺 مشاوره‌های پوستی:")
        if cons_for_user:
            for c in cons_for_user:
                lines.append(
                    f"- پوست: {c['skin_type']} | مشکل: {c['problem']} | حساسیت: {c['sensitivity']}"
                )
        else:
            lines.append("هیچ مشاوره‌ای ثبت نشده است.")

        lines.append("")
        lines.append("📓 یادداشت‌های CRM:")
        if notes:
            for n in notes:
                lines.append(f"- {n['note']}")
        else:
            lines.append("هیچ یادداشتی ثبت نشده است.")

        await query.message.reply_text("\n".join(lines), reply_markup=admin_back_kb())
        return

    if data.startswith("assignpkg_"):
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        uid = int(data.replace("assignpkg_", ""))
        u = get_user_by_id(uid)
        if not u:
            await query.message.reply_text("کاربر یافت نشد.", reply_markup=admin_back_kb())
            return
        buttons = []
        for code, info in PACKAGES.items():
            label = f"{info['title']} ({info['total_sessions']} جلسه)"
            buttons.append([InlineKeyboardButton(label, callback_data=f"assignpkg2_{uid}_{code}")])
        buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data=f"admin_user_{uid}")])
        await query.message.reply_text("پکیج مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("assignpkg2_"):
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kk())
            return
        _, uid_str, code = data.split("_", 2)
        uid = int(uid_str)
        u = get_user_by_id(uid)
        if not u:
            await query.message.reply_text("کاربر یافت نشد.", reply_markup=admin_back_kb())
            return
        create_user_package(uid, u["clinic_id"], code)
        await query.message.reply_text(
            f"✅ پکیج {PACKAGES[code]['title']} برای بیمار ثبت شد.",
            reply_markup=admin_back_kb(),
        )
        return

    if data.startswith("admin_tag_vip_"):
        chat_id_target = int(data.replace("admin_tag_vip_", ""))
        set_user_tag(chat_id_target, "VIP", add=True)
        await query.message.reply_text("✅ کاربر به‌عنوان VIP برچسب‌گذاری شد.", reply_markup=admin_back_kb())
        return

    if data.startswith("admin_tag_block_"):
        chat_id_target = int(data.replace("admin_tag_block_", ""))
        set_user_tag(chat_id_target, "BLOCKED", add=True)
        await query.message.reply_text("✅ کاربر به‌عنوان بلاک‌شده برچسب‌گذاری شد.", reply_markup=admin_back_kb())
        return

    if data == "admin_appts":
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        appts = get_last_appointments()
        if not appts:
            await query.message.reply_text("هیچ نوبتی ثبت نشده است.", reply_markup=admin_back_kb())
            return
        lines = []
        for a in appts:
            pkg_part = ""
            if a["status"] == "package":
                pkg_part = f" (پکیج، جلسه {a['package_session']})"
            lines.append(
                f"#{a['id']} | {a['clinic_name']} | {a['full_name']} | {a['service_title']}{pkg_part} | {a['date']} {a['time']} | {a['status']}"
            )
        await query.message.reply_text("آخرین نوبت‌ها:\n\n" + "\n".join(lines), reply_markup=admin_back_kb())
        return

    if data == "admin_calendar":
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        appts = get_upcoming_appointments(days_ahead=14)
        if not appts:
            await query.message.reply_text("در ۱۴ روز آینده نوبتی ثبت نشده است.", reply_markup=admin_back_kb())
            return
        lines = ["📆 نوبت‌های ۱۴ روز آینده:\n"]
        for a in appts:
            lines.append(
                f"- {a['date']} {a['time']} | {a['clinic_name']} | {a['service_title']} | {a['full_name']} | {a['doctor_name']} (#{a['id']})"
            )
        await query.message.reply_text("\n".join(lines), reply_markup=admin_back_kb())
        return

    if data == "admin_payments":
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        pays = get_last_payments()
        if not pays:
            await query.message.reply_text("هیچ پرداختی ثبت نشده است.", reply_markup=admin_back_kb())
            return
        buttons = []
        for p in pays:
            label = f"#{p['id']} | {p['clinic_name']} | {p['full_name']} | {p['amount']:,} | {p['method']} | {p['status']}"
            buttons.append([InlineKeyboardButton(label, callback_data=f"admin_pay_{p['id']}")])
        buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_panel")])
        await query.message.reply_text("آخرین پرداخت‌ها:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("admin_pay_"):
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        pid = int(data.replace("admin_pay_", ""))
        p = get_payment_by_id(pid)
        if not p:
            await query.message.reply_text("پرداخت یافت نشد.", reply_markup=admin_back_kb())
            return
        u = get_user_by_id(p["user_id"])
        a = get_appointment_by_id(p["appointment_id"]) if p["appointment_id"] else None
        lines = [
            f"پرداخت #{p['id']}",
            f"بیمار: {u['full_name'] if u else '-'}",
            f"کلینیک: {p['clinic_id']}",
            f"مبلغ: {p['amount']:,} تومان",
            f"روش: {p['method']}",
            f"وضعیت: {p['status']}",
        ]
        if p["online_authority"]:
            lines.append(f"کد پیگیری داخلی: {p['online_authority']}")
        if a:
            lines.append(f"نوبت مرتبط: #{a['id']} | {a['service_title']} | {a['date']} {a['time']}")
        buttons = []
        if p["status"] == "pending":
            buttons.append(
                [
                    InlineKeyboardButton("✔ تأیید پرداخت", callback_data=f"admin_pay_ok_{p['id']}"),
                    InlineKeyboardButton("❌ رد پرداخت", callback_data=f"admin_pay_rej_{p['id']}"),
                ]
            )
        buttons.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_payments")])
        await query.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("admin_pay_ok_"):
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        pid = int(data.replace("admin_pay_ok_", ""))
        p = get_payment_by_id(pid)
        if not p:
            await query.message.reply_text("پرداخت یافت نشد.", reply_markup=admin_back_kb())
            return
        update_payment_status(pid, "paid", ref_id=f"ADMIN-{pid}")
        if p["appointment_id"]:
            update_appointment_status(p["appointment_id"], "paid")
            appt = get_appointment_by_id(p["appointment_id"])
            add_service_tag_to_user(appt["user_id"], appt["service_code"])
            user = get_user_by_id(appt["user_id"])
            app: Application = context.application  # type: ignore
            try:
                await app.bot.send_message(
                    chat_id=user["chat_id"],
                    text=(
                        f"✅ پرداخت نوبت شما برای {appt['service_title']} تأیید شد.\n"
                        f"تاریخ: {appt['date']} ساعت {appt['time']}"
                    ),
                )
            except Exception:
                pass
        await query.message.reply_text("✅ پرداخت به‌عنوان «تأیید شده» ثبت شد.", reply_markup=admin_back_kb())
        return

    if data.startswith("admin_pay_rej_"):
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        pid = int(data.replace("admin_pay_rej_", ""))
        p = get_payment_by_id(pid)
        if not p:
            await query.message.reply_text("پرداخت یافت نشد.", reply_markup=admin_back_kb())
            return
        update_payment_status(pid, "rejected", ref_id=None)
        if p["appointment_id"]:
            update_appointment_status(p["appointment_id"], "pending_payment")
            appt = get_appointment_by_id(p["appointment_id"])
            user = get_user_by_id(appt["user_id"])
            app: Application = context.application  # type: ignore
            try:
                await app.bot.send_message(
                    chat_id=user["chat_id"],
                    text=(
                        f"⚠️ پرداخت نوبت شما برای {appt['service_title']} تأیید نشد.\n"
                        "در صورت بروز مشکل با کلینیک تماس بگیرید."
                    ),
                )
            except Exception:
                pass
        await query.message.reply_text("پرداخت به‌عنوان «رد شده» ثبت شد.", reply_markup=admin_back_kb())
        return

    if data == "admin_consults":
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        cons = get_last_consultations()
        if not cons:
            await query.message.reply_text("هیچ مشاوره‌ای ثبت نشده است.", reply_markup=admin_back_kb())
            return
        lines = []
        for c in cons:
            lines.append(
                f"#{c['id']} | {c['clinic_name']} | {c['full_name']} | پوست: {c['skin_type']} | مشکل: {c['problem']} | حساسیت: {c['sensitivity']}"
            )
        await query.message.reply_text("آخرین مشاوره‌ها:\n\n" + "\n".join(lines), reply_markup=admin_back_kb())
        return

    if data == "admin_packages":
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        lines = ["🎁 پکیج‌های تعریف‌شده:\n"]
        for code, info in PACKAGES.items():
            lines.append(
                f"- {info['title']} | خدمت: {SERVICES[info['service_code']]['title']} | جلسات: {info['total_sessions']} | قیمت پیشنهادی: {info['price']:,}"
            )
        await query.message.reply_text("\n".join(lines), reply_markup=admin_back_kb())
        return

    if data == "admin_broadcast":
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        buttons = [
            [InlineKeyboardButton("همه کاربران", callback_data="bc_ALL")],
            [InlineKeyboardButton("فقط VIP", callback_data="bc_VIP")],
            [InlineKeyboardButton("بیماران بوتاکس", callback_data="bc_Botox")],
            [InlineKeyboardButton("بیماران لیزر", callback_data="bc_Laser")],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_panel")],
        ]
        await query.message.reply_text(
            "گروه هدف برای پیام گروهی را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data.startswith("bc_"):
        if not context.user_data.get("is_admin"):
            await query.message.reply_text("شما به پنل مدیریت دسترسی ندارید.", reply_markup=back_main_kb())
            return
        seg = data.replace("bc_", "")
        context.user_data["state"] = STATE_AWAITING_BROADCAST_TEXT
        context.user_data["broadcast_segment"] = "ALL" if seg == "ALL" else seg
        await query.message.reply_text(
            "متن پیامی که می‌خواهید برای این گروه ارسال شود را بفرستید:",
            reply_markup=admin_back_kb(),
        )
        return


# ==================== Reminder Job ====================

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    app: Application = context.application  # type: ignore
    now = datetime.now()

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM appointments")
    rows = c.fetchall()
    conn.close()

    for a in rows:
        appt_dt = appointment_datetime(a)
        if not appt_dt:
            continue
        user = get_user_by_id(a["user_id"])
        if not user:
            continue
        chat_id = user["chat_id"]
        delta = appt_dt - now

        # 24h reminder
        if a["pre24_sent"] == 0 and timedelta(hours=0) < delta <= timedelta(hours=24):
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⏰ یادآوری نوبت فردا:\n"
                        f"{a['service_title']} با {a['doctor_name']}\n"
                        f"تاریخ: {a['date']} ساعت {a['time']}"
                    ),
                )
                conn2 = get_conn()
                conn2.execute("UPDATE appointments SET pre24_sent = 1 WHERE id = ?", (a["id"],))
                conn2.commit()
                conn2.close()
            except Exception as e:
                logger.exception("24h reminder error: %s", e)

        # 3h reminder
        if a["pre3_sent"] == 0 and timedelta(hours=0) < delta <= timedelta(hours=3):
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⏰ یادآوری نوبت چند ساعت دیگر:\n"
                        f"{a['service_title']} با {a['doctor_name']}\n"
                        f"امروز ساعت {a['time']}"
                    ),
                )
                conn2 = get_conn()
                conn2.execute("UPDATE appointments SET pre3_sent = 1 WHERE id = ?", (a["id"],))
                conn2.commit()
                conn2.close()
            except Exception as e:
                logger.exception("3h reminder error: %s", e)

        # Post-care 3h بعد نوبت
        if a["postcare_sent"] == 0 and now >= appt_dt + timedelta(hours=3):
            try:
                txt = f"✨ مراقبت‌های بعد از درمان برای {a['service_title']}:\n"
                if a["service_code"] == "laser":
                    txt += "• تا ۴۸ ساعت از آفتاب مستقیم، سونا و حمام داغ خودداری کنید.\n• از کرم ترمیم‌کننده و ضدآفتاب استفاده کنید."
                elif a["service_code"] == "botox":
                    txt += "• تا ۴ ساعت دراز نکشید و ناحیه را ماساژ ندهید.\n• از فعالیت شدید بدنی تا چند ساعت خودداری کنید."
                elif a["service_code"] == "clean":
                    txt += "• تا ۲۴ ساعت از آرایش سنگین و اسکراب پرهیز کنید.\n• از مرطوب‌کننده و ضدآفتاب ملایم استفاده کنید."
                elif a["service_code"] == "meso":
                    txt += "• ممکن است کمی قرمزی و تورم خفیف داشته باشید که طی چند روز برطرف می‌شود.\n• از آفتاب مستقیم و سونا خودداری کنید."
                else:
                    txt += "• در صورت هرگونه نگرانی یا سوال، با کلینیک تماس بگیرید."
                await app.bot.send_message(chat_id=chat_id, text=txt)
                conn2 = get_conn()
                conn2.execute("UPDATE appointments SET postcare_sent = 1 WHERE id = ?", (a["id"],))
                conn2.commit()
                conn2.close()
            except Exception as e:
                logger.exception("post-care error: %s", e)

        # Rating 1d بعد
        if a["rating_sent"] == 0 and now >= appt_dt + timedelta(days=1):
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⭐️ از ۱ تا ۵، رضایت شما از نوبت {a['service_title']} در تاریخ {a['date']} چقدر بود؟\n"
                        "می‌توانید عدد را برای ما ارسال کنید."
                    ),
                )
                conn2 = get_conn()
                conn2.execute("UPDATE appointments SET rating_sent = 1 WHERE id = ?", (a["id"],))
                conn2.commit()
                conn2.close()
            except Exception as e:
                logger.exception("rating reminder error: %s", e)

        # Recall
        svc = SERVICES.get(a["service_code"], {})
        recall_days = svc.get("recall_days")
        if recall_days and a["recall_sent"] == 0 and now >= appt_dt + timedelta(days=recall_days):
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⏰ یادآوری دوره‌ای:\n"
                        f"از آخرین {a['service_title']} شما مدتی گذشته است.\n"
                        "در صورت تمایل می‌توانیم برای تمدید نوبت جدید تنظیم کنیم. 🌿"
                    ),
                )
                conn2 = get_conn()
                conn2.execute("UPDATE appointments SET recall_sent = 1 WHERE id = ?", (a["id"],))
                conn2.commit()
                conn2.close()
            except Exception as e:
                logger.exception("recall error: %s", e)


# ==================== main ====================

def main():
    init_db()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # JobQueue برای ریمایندرها
    job_queue = application.job_queue
    if job_queue is not None:
        job_queue.run_repeating(reminder_job, interval=600, first=60)
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

