import logging
import re
import sqlite3
import os
import json
import urllib.parse
import asyncio
import secrets
import string
from datetime import datetime, timedelta
from telegram import (
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove,
    Update
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ContextTypes,
    ConversationHandler
)
import jdatetime

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = "8437924316:AAFysR4_YGYr2HxhxLHWUVAJJdNHSXxNXns"

# حالت‌های مکالمه
(
    NAME, PHONE, 
    CONSULT_SKIN_TYPE, CONSULT_SKIN_PROBLEM, CONSULT_SKIN_SENSITIVITY,
    UPLOAD_RECEIPT,
    ADMIN_LOGIN, ADMIN_REGISTRATION
) = range(8)

# ==================== DATABASE FUNCTIONS ====================

def init_db():
    """مقداردهی اولیه دیتابیس"""
    if os.path.exists('clinic.db'):
        os.remove('clinic.db')
        logger.info("Old database deleted")
    
    conn = sqlite3.connect('clinic.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # ایجاد جدول کاربران
    cursor.execute('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER UNIQUE,
            full_name TEXT,
            phone_number TEXT,
            age INTEGER,
            gender TEXT,
            is_admin BOOLEAN DEFAULT FALSE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # ایجاد جدول خدمات
    cursor.execute('''
        CREATE TABLE services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT,
            base_price INTEGER,
            category TEXT,
            gender TEXT,
            body_part TEXT,
            duration INTEGER,
            popular BOOLEAN DEFAULT FALSE
        )
    ''')
    
    # ایجاد جدول پزشکان
    cursor.execute('''
        CREATE TABLE doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            specialization TEXT,
            bio TEXT,
            experience TEXT,
            services TEXT,
            image TEXT,
            available BOOLEAN DEFAULT TRUE
        )
    ''')
    
    # ایجاد جدول نوبت‌ها
    cursor.execute('''
        CREATE TABLE appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service_id INTEGER,
            doctor_id INTEGER,
            appointment_date DATE,
            appointment_time TIME,
            status TEXT DEFAULT 'pending',
            payment_status TEXT DEFAULT 'pending',
            receipt_photo TEXT,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(service_id) REFERENCES services(id),
            FOREIGN KEY(doctor_id) REFERENCES doctors(id)
        )
    ''')
    
    # ایجاد جدول پرداخت‌ها
    cursor.execute('''
        CREATE TABLE payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            appointment_id INTEGER,
            amount INTEGER,
            payment_method TEXT,
            receipt_photo TEXT,
            status TEXT DEFAULT 'pending',
            transaction_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(appointment_id) REFERENCES appointments(id)
        )
    ''')
    
    # ایجاد جدول مشاوره
    cursor.execute('''
        CREATE TABLE consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            consultation_type TEXT,
            answers TEXT,
            recommendation TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    # ایجاد جدول کدهای دعوت ادمین
    cursor.execute('''
        CREATE TABLE admin_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            role TEXT,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME,
            is_active BOOLEAN DEFAULT TRUE
        )
    ''')
    
    # ایجاد جدول دسترسی‌های ادمین
    cursor.execute('''
        CREATE TABLE admin_access (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            role TEXT,
            permissions TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # ایجاد جدول تنظیمات ادمین
    cursor.execute('''
        CREATE TABLE admin_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_password TEXT,
            support_phone TEXT
        )
    ''')
    
    # اضافه کردن داده‌های اولیه
    add_sample_data(cursor)
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully!")

def add_sample_data(cursor):
    """اضافه کردن داده‌های نمونه"""
    
    # خدمات لیزر
    laser_services = [
        ('لیزر صورت بانوان', 'لیزر کامل صورت و گردن', 800000, 'لیزر', 'زن', 'صورت', 30, True),
        ('لیزر زیربغل بانوان', 'لیزر ناحیه زیربغل', 500000, 'لیزر', 'زن', 'زیربغل', 20, True),
        ('لیزر بازو بانوان', 'لیزر کامل بازوها', 700000, 'لیزر', 'زن', 'بازو', 25, False),
        ('لیزر ساق پا بانوان', 'لیزر ساق پا', 900000, 'لیزر', 'زن', 'ساق پا', 35, True),
        ('لیزر ران بانوان', 'لیزر ران', 1100000, 'لیزر', 'زن', 'ران', 40, False),
        ('لیزر بیکینی بانوان', 'لیزر ناحیه بیکینی', 600000, 'لیزر', 'زن', 'بیکینی', 30, True),
        ('لیزر کامل بدن بانوان', 'لیزر کامل تمام بدن', 3500000, 'لیزر', 'زن', 'کل بدن', 120, True),
        ('لیزر صورت آقایان', 'لیزر صورت و گردن', 1000000, 'لیزر', 'مرد', 'صورت', 40, True),
        ('لیزر سینه آقایان', 'لیزر ناحیه سینه', 1200000, 'لیزر', 'مرد', 'سینه', 45, False),
        ('لیزر شکم آقایان', 'لیزر ناحیه شکم', 900000, 'لیزر', 'مرد', 'شکم', 35, False),
        ('لیزر پشت آقایان', 'لیزر کامل پشت', 1500000, 'لیزر', 'مرد', 'پشت', 50, True),
        ('لیزر بازو آقایان', 'لیزر بازوها', 800000, 'لیزر', 'مرد', 'بازو', 30, True),
        ('لیزر ران آقایان', 'لیزر ران', 1000000, 'لیزر', 'مرد', 'ران', 40, False),
        ('لیزر کامل بدن آقایان', 'لیزر کامل تمام بدن', 4000000, 'لیزر', 'مرد', 'کل بدن', 150, True)
    ]
    
    cursor.executemany('''
        INSERT INTO services (name, description, base_price, category, gender, body_part, duration, popular)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', laser_services)
    
    # خدمات تزریقات زیبایی
    injection_services = [
        ('تزریق بوتاکس پیشانی', 'تزریق بوتاکس برای رفع چین و چروک پیشانی', 1500000, 'تزریقات', 'مشترک', 'پیشانی', 30, True),
        ('تزریق بوتاکس دور چشم', 'تزریق بوتاکس برای خطوط دور چشم', 1200000, 'تزریقات', 'مشترک', 'دور چشم', 25, True),
        ('تزریق فیلر لب', 'تزریق فیلر برای حجم دهی لب', 2500000, 'تزریقات', 'مشترک', 'لب', 45, True),
        ('تزریق فیلر گونه', 'تزریق فیلر برای حجم دهی گونه', 3000000, 'تزریقات', 'مشترک', 'گونه', 50, True),
        ('مزوتراپی صورت', 'مزوتراپی برای جوانسازی پوست صورت', 2000000, 'تزریقات', 'مشترک', 'صورت', 60, False),
        ('تزریق چربی', 'تزریق چربی برای حجم دهی طبیعی', 4500000, 'تزریقات', 'مشترک', 'صورت', 90, False)
    ]
    
    cursor.executemany('''
        INSERT INTO services (name, description, base_price, category, gender, body_part, duration, popular)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', injection_services)
    
    # خدمات پوست
    skin_services = [
        ('پاکسازی پوست صورت', 'پاکسازی عمقی پوست با جدیدترین متدها', 800000, 'پوست', 'مشترک', 'صورت', 60, True),
        ('میکرونیدلینگ', 'میکرونیدلینگ برای جوانسازی پوست', 1200000, 'پوست', 'مشترک', 'صورت', 45, True),
        ('پیلینگ شیمیایی', 'پیلینگ شیمیایی برای روشن شدن پوست', 900000, 'پوست', 'مشترک', 'صورت', 30, False),
        ('لیزر درمانی پوست', 'لیزر برای درمان لک و جوش', 1800000, 'پوست', 'مشترک', 'صورت', 40, True),
        ('آبرسانی پوست', 'آبرسانی عمقی پوست با سرم‌های تخصصی', 600000, 'پوست', 'مشترک', 'صورت', 35, False)
    ]
    
    cursor.executemany('''
        INSERT INTO services (name, description, base_price, category, gender, body_part, duration, popular)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', skin_services)
    
    # خدمات کاشت مو
    hair_services = [
        ('کاشت مو FIT', 'کاشت مو به روش FIT', 15000000, 'کاشت مو', 'مشترک', 'سر', 240, True),
        ('کاشت مو FUE', 'کاشت مو به روش FUE', 12000000, 'کاشت مو', 'مشترک', 'سر', 300, True),
        ('کاشت ابرو', 'کاشت ابرو به روش طبیعی', 5000000, 'کاشت مو', 'مشترک', 'ابرو', 120, True),
        ('کاشت ریش', 'کاشت ریش و سبیل', 8000000, 'کاشت مو', 'مرد', 'ریش', 180, False),
        ('پروتز مو', 'پروتز مو برای پوشش کامل', 7000000, 'کاشت مو', 'مشترک', 'سر', 150, False)
    ]
    
    cursor.executemany('''
        INSERT INTO services (name, description, base_price, category, gender, body_part, duration, popular)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', hair_services)
    
    # پزشکان
    doctors = [
        ('دکتر مریم احمدی', 'پوست و زیبایی', 'متخصص پوست با ۱۲ سال سابقه، فلوشیپ لیزر از آلمان', '۱۲ سال', 'لیزر,پوست,تزریقات', '', True),
        ('دکتر سارا محمدی', 'لیزر و زیبایی', 'متخصص زیبایی با ۱۰ سال سابقه در زمینه لیزر', '۱۰ سال', 'لیزر,پوست', '', True),
        ('دکتر حمید کریمی', 'تزریقات زیبایی', 'متخصص تزریقات زیبایی با ۷ سال سابقه', '۷ سال', 'تزریقات', '', True),
        ('دکتر علی رضایی', 'کاشت مو', 'جراح کاشت مو با ۸ سال سابقه، عضو انجمن کاشت موی ایران', '۸ سال', 'کاشت مو', '', True),
        ('دکتر فاطمه نوروزی', 'پوست و مو', 'متخصص پوست و مو با ۹ سال سابقه', '۹ سال', 'پوست,لیزر', '', True)
    ]
    
    cursor.executemany('''
        INSERT INTO doctors (name, specialization, bio, experience, services, image, available)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', doctors)
    
    # کاربر ادمین اصلی
    cursor.execute('''
        INSERT OR REPLACE INTO users (chat_id, full_name, phone_number, is_admin)
        VALUES (?, ?, ?, ?)
    ''', (123456789, 'مدیر کلینیک', '09123456789', True))
    
    # اضافه کردن دسترسی ادمین
    cursor.execute('SELECT id FROM users WHERE chat_id = ?', (123456789,))
    admin_user_id = cursor.fetchone()[0]
    
    cursor.execute('''
        INSERT OR REPLACE INTO admin_access (user_id, role, permissions)
        VALUES (?, ?, ?)
    ''', (admin_user_id, 'super_admin', 'all'))
    
    # تنظیم رمز عبور اصلی
    cursor.execute('''
        INSERT OR REPLACE INTO admin_settings (id, master_password, support_phone)
        VALUES (1, '1234', '09190432181')
    ''')
    
    # ایجاد یک کد دعوت نمونه
    sample_code = generate_invite_code()
    cursor.execute('''
        INSERT INTO admin_invites (code, role, max_uses, expires_at)
        VALUES (?, 'moderator', 3, datetime('now', '+30 days'))
    ''', (sample_code,))

def get_db_connection():
    return sqlite3.connect('clinic.db', check_same_thread=False)

def is_admin(chat_id, permission=None):
    """بررسی آیا کاربر ادمین است"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if permission == 'manage_invites':
        cursor.execute('''
            SELECT aa.role FROM admin_access aa
            JOIN users u ON aa.user_id = u.id
            WHERE u.chat_id = ? AND aa.role IN ('super_admin', 'admin')
        ''', (chat_id,))
    else:
        cursor.execute('''
            SELECT aa.role FROM admin_access aa
            JOIN users u ON aa.user_id = u.id
            WHERE u.chat_id = ?
        ''', (chat_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    return result is not None

def get_admin_role(chat_id):
    """دریافت نقش ادمین"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT aa.role FROM admin_access aa
        JOIN users u ON aa.user_id = u.id
        WHERE u.chat_id = ?
    ''', (chat_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def generate_invite_code(length=8):
    """تولید کد دعوت تصادفی"""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def verify_invite_code(code):
    """بررسی اعتبار کد دعوت"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, role, max_uses, used_count, expires_at, is_active 
        FROM admin_invites 
        WHERE code = ?
    ''', (code,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return None
    
    invite_id, role, max_uses, used_count, expires_at, is_active = result
    
    # بررسی انقضا
    if expires_at and datetime.strptime(expires_at, '%Y-%m-%d %H:%M:%S') < datetime.now():
        conn.close()
        return None
    
    # بررسی تعداد استفاده
    if used_count >= max_uses:
        conn.close()
        return None
    
    # بررسی فعال بودن
    if not is_active:
        conn.close()
        return None
    
    # افزایش تعداد استفاده
    cursor.execute('''
        UPDATE admin_invites 
        SET used_count = used_count + 1 
        WHERE id = ?
    ''', (invite_id,))
    
    conn.commit()
    conn.close()
    
    return role

def save_user_to_db(chat_id, full_name, phone_number):
    """ذخیره کاربر در دیتابیس"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO users (chat_id, full_name, phone_number)
            VALUES (?, ?, ?)
        ''', (chat_id, full_name, phone_number))
        conn.commit()
        logger.info(f"User saved: {full_name}, {phone_number}")
    except Exception as e:
        logger.error(f"Error saving user: {e}")
    finally:
        conn.close()

def validate_phone_number(phone):
    """اعتبارسنجی شماره تلفن"""
    phone = re.sub(r'\D', '', phone)
    
    if phone.startswith('98'):
        phone = '0' + phone[2:]
    elif phone.startswith('+98'):
        phone = '0' + phone[3:]
    
    if len(phone) == 11 and phone.startswith('09'):
        return phone
    elif len(phone) == 10 and phone.startswith('9'):
        return '0' + phone
    
    return None

# ==================== SIMPLE ADMIN AUTHENTICATION ====================

def verify_admin_simple(username, password):
    """بررسی ساده اعتبار ادمین"""
    admin_credentials = {
        'admin': 'admin123',
        'manager': 'manager123', 
        'clinic': 'clinic2024'
    }
    return username in admin_credentials and admin_credentials[username] == password

# ==================== BOT HANDLERS ====================

async def safe_answer_query(query):
    """پاسخ امن به query بدون ایجاد خطا"""
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Query answer failed: {e}")

async def start(update, context):
    """دستور start"""
    user = update.effective_user
    
    # بررسی ادمین بودن
    if is_admin(user.id):
        keyboard = [
            [InlineKeyboardButton("👨‍💼 پنل مدیریت", callback_data="admin_panel")],
            [InlineKeyboardButton("📅 رزرو نوبت", callback_data="menu_booking")],
            [InlineKeyboardButton("💄 خدمات زیبایی", callback_data="menu_beauty")],
            [InlineKeyboardButton("💬 مشاوره", callback_data="menu_consultation")],
            [InlineKeyboardButton("📖 راهنمای استفاده", callback_data="menu_guide")],
            [InlineKeyboardButton("🔐 دسترسی ادمین", callback_data="admin_access")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        admin_role = get_admin_role(user.id)
        await update.message.reply_text(
            f"👋 سلام {user.first_name}!\n"
            "به کلینیک زیبایی گلوریا خوش آمدید!\n"
            f"🔓 **شما به عنوان {admin_role} وارد شده‌اید.**",
            reply_markup=reply_markup
        )
        return
    
    # بررسی کاربر عادی
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT full_name FROM users WHERE chat_id = ?', (user.id,))
    existing_user = cursor.fetchone()
    conn.close()
    
    if existing_user:
        await show_main_menu(update, context)
        return
    
    # کاربر جدید
    await update.message.reply_text(
        f"👋 سلام {user.first_name}! به کلینیک زیبایی گلوریا خوش آمدید!\n"
        "لطفاً نام و نام خانوادگی خود را وارد کنید:"
    )
    context.user_data.clear()
    context.user_data['awaiting_name'] = True

async def show_main_menu(update, context):
    """نمایش منوی اصلی"""
    user = update.effective_user
    
    keyboard = [
        [InlineKeyboardButton("💄 خدمات زیبایی", callback_data="menu_beauty")],
        [InlineKeyboardButton("📅 رزرو نوبت", callback_data="menu_booking")],
        [InlineKeyboardButton("💬 مشاوره هوشمند", callback_data="menu_consultation")],
        [InlineKeyboardButton("👨‍⚕️ پزشکان ما", callback_data="menu_doctors")],
        [InlineKeyboardButton("💳 پرداخت", callback_data="payment_receipt")],
        [InlineKeyboardButton("📖 راهنمای استفاده", callback_data="menu_guide")],
        [InlineKeyboardButton("📍 تماس با ما", callback_data="menu_contact")]
    ]
    
    # اگر کاربر ادمین است، دکمه پنل مدیریت را اضافه کن
    if is_admin(user.id) or context.user_data.get('admin_logged_in'):
        keyboard.append([InlineKeyboardButton("👨‍💼 پنل مدیریت", callback_data="admin_panel_simple")])
    else:
        keyboard.append([InlineKeyboardButton("🔐 ورود به پنل مدیریت", callback_data="admin_login_simple")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            "🏠 **منوی اصلی کلینیک گلوریا**\n\n"
            "لطفاً گزینه مورد نظر را انتخاب کنید:",
            reply_markup=reply_markup
        )
    else:
        await update.callback_query.edit_message_text(
            "🏠 **منوی اصلی کلینیک گلوریا**\n\n"
            "لطفاً گزینه مورد نظر را انتخاب کنید:",
            reply_markup=reply_markup
        )

# ==================== SIMPLE ADMIN SYSTEM ====================

async def start_admin_login_simple(update, context):
    """شروع ورود ادمین ساده"""
    query = update.callback_query
    await safe_answer_query(query)
    
    # ذخیره اطلاعات برای ردیابی حالت
    context.user_data['awaiting_admin_username'] = True
    
    await query.edit_message_text(
        "🔐 **ورود به پنل مدیریت**\n\n"
        "لطفاً نام کاربری خود را وارد کنید:"
    )

async def handle_admin_username(update, context):
    """دریافت نام کاربری ادمین"""
    if not context.user_data.get('awaiting_admin_username'):
        return
    
    username = update.message.text.strip()
    context.user_data['admin_username'] = username
    context.user_data['awaiting_admin_username'] = False
    context.user_data['awaiting_admin_password'] = True
    
    await update.message.reply_text(
        f"نام کاربری: {username}\n\n"
        "لطفاً رمز عبور خود را وارد کنید:"
    )

async def handle_admin_password(update, context):
    """دریافت رمز عبور ادمین"""
    if not context.user_data.get('awaiting_admin_password'):
        return
    
    password = update.message.text
    username = context.user_data.get('admin_username')
    
    # پاک کردن حالت‌ها
    context.user_data.pop('awaiting_admin_password', None)
    
    if verify_admin_simple(username, password):
        # ورود موفق
        context.user_data['admin_logged_in'] = True
        context.user_data['admin_chat_id'] = update.effective_user.id
        context.user_data['admin_username'] = username
        
        await update.message.reply_text(
            f"✅ **ورود موفقیت‌آمیز**\n\n"
            f"👋 سلام {username}!\n"
            f"به پنل مدیریت کلینیک خوش آمدید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👨‍💼 پنل مدیریت", callback_data="admin_panel_simple")],
                [InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]
            ])
        )
    else:
        await update.message.reply_text(
            "❌ **ورود ناموفق**\n\n"
            "نام کاربری یا رمز عبور اشتباه است.\n"
            "لطفاً دوباره تلاش کنید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔐 تلاش مجدد", callback_data="admin_login_simple")],
                [InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]
            ])
        )

async def show_admin_panel_simple(update, context):
    """نمایش پنل ادمین ساده"""
    query = update.callback_query
    await safe_answer_query(query)
    
    user_chat_id = update.effective_user.id
    
    if not (is_admin(user_chat_id) or context.user_data.get('admin_logged_in')):
        await query.edit_message_text(
            "❌ **دسترسی denied**\n\n"
            "لطفاً ابتدا وارد سیستم شوید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔐 ورود به پنل", callback_data="admin_login_simple")],
                [InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]
            ])
        )
        return
    
    # دریافت آمار ساده
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = FALSE')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM appointments')
    total_appointments = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM appointments WHERE status = "pending"')
    pending_appointments = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM payments WHERE status = "pending"')
    pending_payments = cursor.fetchone()[0]
    
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("📊 مشاهده نوبت‌ها", callback_data="admin_view_appointments")],
        [InlineKeyboardButton("💰 مشاهده پرداخت‌ها", callback_data="admin_view_payments")],
        [InlineKeyboardButton("👥 مشاهده کاربران", callback_data="admin_view_users")],
        [InlineKeyboardButton("📈 آمار کلی", callback_data="admin_view_stats")],
        [InlineKeyboardButton("🚪 خروج", callback_data="admin_logout_simple")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    panel_text = (
        f"👨‍💼 **پنل مدیریت کلینیک**\n\n"
        f"📊 **آمار سریع:**\n"
        f"• 👥 کاربران: {total_users} نفر\n"
        f"• 📅 نوبت‌ها: {total_appointments} نوبت\n"
        f"• ⏳ نوبت‌های در انتظار: {pending_appointments}\n"
        f"• 💰 پرداخت‌های در انتظار: {pending_payments}\n\n"
        f"لطفاً بخش مورد نظر را انتخاب کنید:"
    )
    
    await query.edit_message_text(panel_text, reply_markup=reply_markup)

async def admin_view_appointments(update, context):
    """مشاهده نوبت‌ها"""
    query = update.callback_query
    await safe_answer_query(query)
    
    if not (is_admin(update.effective_user.id) or context.user_data.get('admin_logged_in')):
        await query.edit_message_text("❌ لطفاً ابتدا وارد سیستم شوید.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT a.id, u.full_name, s.name, a.appointment_date, a.appointment_time, a.status
        FROM appointments a
        LEFT JOIN users u ON a.user_id = u.id
        LEFT JOIN services s ON a.service_id = s.id
        ORDER BY a.created_at DESC
        LIMIT 10
    ''')
    
    appointments = cursor.fetchall()
    conn.close()
    
    if not appointments:
        text = "📊 **نوبت‌ها**\n\nهیچ نوبتی ثبت نشده است."
    else:
        text = "📊 **۱۰ نوبت آخر**\n\n"
        for apt in appointments:
            apt_id, user_name, service_name, date, time, status = apt
            status_icon = "✅" if status == 'confirmed' else "⏳" if status == 'pending' else "❌"
            text += f"{status_icon} {user_name} - {service_name}\n📅 {date} ⏰ {time}\n🆔 کد: {apt_id}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel_simple")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def admin_view_payments(update, context):
    """مشاهده پرداخت‌ها"""
    query = update.callback_query
    await safe_answer_query(query)
    
    if not (is_admin(update.effective_user.id) or context.user_data.get('admin_logged_in')):
        await query.edit_message_text("❌ لطفاً ابتدا وارد سیستم شوید.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.id, u.full_name, p.amount, p.status, p.created_at
        FROM payments p
        LEFT JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC
        LIMIT 10
    ''')
    
    payments = cursor.fetchall()
    conn.close()
    
    if not payments:
        text = "💰 **پرداخت‌ها**\n\nهیچ پرداختی ثبت نشده است."
    else:
        text = "💰 **۱۰ پرداخت آخر**\n\n"
        for pay in payments:
            pay_id, user_name, amount, status, created_at = pay
            status_icon = "✅" if status == 'confirmed' else "⏳"
            amount_text = f"{amount:,}" if amount else "0"
            text += f"{status_icon} {user_name} - {amount_text} تومان\n🆔 کد: {pay_id}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel_simple")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def admin_view_users(update, context):
    """مشاهده کاربران"""
    query = update.callback_query
    await safe_answer_query(query)
    
    if not (is_admin(update.effective_user.id) or context.user_data.get('admin_logged_in')):
        await query.edit_message_text("❌ لطفاً ابتدا وارد سیستم شوید.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT full_name, phone_number, created_at
        FROM users 
        WHERE is_admin = FALSE
        ORDER BY created_at DESC
        LIMIT 10
    ''')
    
    users = cursor.fetchall()
    conn.close()
    
    if not users:
        text = "👥 **کاربران**\n\nهیچ کاربری ثبت نشده است."
    else:
        text = "👥 **۱۰ کاربر آخر**\n\n"
        for user in users:
            name, phone, created = user
            text += f"👤 {name}\n📞 {phone}\n📅 {created[:10]}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel_simple")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def admin_view_stats(update, context):
    """مشاهده آمار کلی"""
    query = update.callback_query
    await safe_answer_query(query)
    
    if not (is_admin(update.effective_user.id) or context.user_data.get('admin_logged_in')):
        await query.edit_message_text("❌ لطفاً ابتدا وارد سیستم شوید.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = FALSE')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM appointments')
    total_appointments = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM services')
    total_services = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM doctors')
    total_doctors = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM payments WHERE status = "confirmed"')
    confirmed_payments = cursor.fetchone()[0]
    
    conn.close()
    
    text = (
        "📈 **آمار کلی کلینیک**\n\n"
        f"👥 کاربران: {total_users} نفر\n"
        f"📅 نوبت‌ها: {total_appointments} نوبت\n"
        f"📋 خدمات: {total_services} خدمت\n"
        f"👨‍⚕️ پزشکان: {total_doctors} نفر\n"
        f"💰 پرداخت‌های تأیید شده: {confirmed_payments} تراکنش\n\n"
        f"🕒 تاریخ: {jdatetime.datetime.now().strftime('%Y/%m/%d')}"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel_simple")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def admin_logout_simple(update, context):
    """خروج از پنل مدیریت"""
    query = update.callback_query
    await safe_answer_query(query)
    
    context.user_data.pop('admin_logged_in', None)
    context.user_data.pop('admin_chat_id', None)
    context.user_data.pop('admin_username', None)
    context.user_data.pop('awaiting_admin_username', None)
    context.user_data.pop('awaiting_admin_password', None)
    
    await query.edit_message_text(
        "✅ **خروج موفقیت‌آمیز**\n\n"
        "شما از پنل مدیریت خارج شدید.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]
        ])
    )

# ==================== EXISTING FUNCTIONS ====================

async def show_beauty_services(update, context):
    """نمایش دسته‌بندی خدمات زیبایی"""
    query = update.callback_query
    await safe_answer_query(query)
    
    keyboard = [
        [InlineKeyboardButton("⚡ خدمات لیزر", callback_data="laser_services")],
        [InlineKeyboardButton("💉 تزریقات زیبایی", callback_data="category_تزریقات")],
        [InlineKeyboardButton("✨ خدمات پوست", callback_data="category_پوست")],
        [InlineKeyboardButton("💇 کاشت مو", callback_data="category_کاشت مو")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "💄 **خدمات زیبایی کلینیک گلوریا**\n\n"
        "لطفاً دسته خدمت مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def show_laser_services(update, context):
    """نمایش خدمات لیزر"""
    query = update.callback_query
    await safe_answer_query(query)
    
    keyboard = [
        [InlineKeyboardButton("👩 لیزر بانوان", callback_data="laser_women")],
        [InlineKeyboardButton("👨 لیزر آقایان", callback_data="laser_men")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_beauty")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "⚡ **خدمات لیزر موهای زائد**\n\n"
        "لطفاً جنسیت خود را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def show_laser_by_gender(update, context):
    """نمایش خدمات لیزر بر اساس جنسیت"""
    query = update.callback_query
    await safe_answer_query(query)
    
    gender = "زن" if query.data == "laser_women" else "مرد"
    context.user_data['laser_gender'] = gender
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, base_price, duration 
        FROM services 
        WHERE category = 'لیزر' AND gender = ? AND popular = TRUE
        ORDER BY base_price
    ''', (gender,))
    services = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for service in services:
        price_text = f"{service[2]:,}"
        button_text = f"⚡ {service[1]} - {price_text} تومان"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"book_service_{service[0]}")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="laser_services")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    gender_text = "بانوان" if gender == "زن" else "آقایان"
    
    await query.edit_message_text(
        f"⚡ **لیزر {gender_text}**\n\n"
        "لطفاً خدمت مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def handle_category_selection(update, context):
    """انتخاب دسته خدمت"""
    query = update.callback_query
    await safe_answer_query(query)
    
    category = query.data.replace('category_', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, description, base_price, duration
        FROM services 
        WHERE category = ? AND gender = 'مشترک' AND popular = TRUE
        ORDER BY base_price
    ''', (category,))
    services = cursor.fetchall()
    conn.close()
    
    if not services:
        await query.edit_message_text("❌ خدمتی در این دسته یافت نشد.")
        return
    
    keyboard = []
    for service in services:
        price_text = f"{service[3]:,}"
        button_text = f"📋 {service[1]} - {price_text} تومان"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"book_service_{service[0]}")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu_beauty")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    category_names = {
        'تزریقات': 'تزریقات زیبایی',
        'پوست': 'خدمات پوست',
        'کاشت مو': 'کاشت مو'
    }
    
    await query.edit_message_text(
        f"📋 **خدمات {category_names.get(category, category)}**\n\n"
        "لطفاً خدمت مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def handle_service_selection_booking(update, context):
    """انتخاب خدمت برای رزرو"""
    query = update.callback_query
    await safe_answer_query(query)
    
    service_id = query.data.split('_')[2]
    context.user_data['selected_service'] = service_id
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT name, base_price, description FROM services WHERE id = ?', (service_id,))
    service = cursor.fetchone()
    
    # دریافت پزشکان مرتبط
    doctors = get_doctors_for_service(service_id)
    conn.close()
    
    if not doctors:
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="menu_beauty")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❌ هیچ پزشکی برای این خدمت موجود نیست.", reply_markup=reply_markup)
        return
    
    keyboard = []
    for doctor in doctors:
        keyboard.append([InlineKeyboardButton(
            f"👨‍⚕️ {doctor[1]} - {doctor[2]}", 
            callback_data=f'book_doctor_{doctor[0]}'
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu_beauty")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📅 **رزرو نوبت برای: {service[0]}**\n"
        f"💰 هزینه: {service[1]:,} تومان\n"
        f"📖 توضیحات: {service[2]}\n\n"
        "لطفاً پزشک مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def handle_doctor_selection_calendar(update, context):
    """نمایش تقویم بعد از انتخاب پزشک"""
    query = update.callback_query
    await safe_answer_query(query)
    
    doctor_id = query.data.split('_')[2]
    context.user_data['selected_doctor'] = doctor_id
    
    # نمایش تقویم ساده‌شده
    today = jdatetime.date.today()
    
    keyboard = []
    # ایجاد ۷ روز آینده
    for i in range(7):
        current_date = today + timedelta(days=i)
        date_str = current_date.strftime('%Y-%m-%d')
        date_display = current_date.strftime('%d %B')
        
        callback_data = f"book_date_{date_str}_s{context.user_data['selected_service']}_d{doctor_id}"
        keyboard.append([InlineKeyboardButton(f"📅 {date_display}", callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"book_service_{context.user_data['selected_service']}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📅 **انتخاب تاریخ نوبت**\n\n"
        "لطفاً تاریخ مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def handle_date_selection(update, context):
    """انتخاب تاریخ"""
    query = update.callback_query
    await safe_answer_query(query)
    
    data = query.data.split('_')
    selected_date = data[2]
    
    # استخراج service_id و doctor_id
    service_id = None
    doctor_id = None
    
    for part in data:
        if part.startswith('s'):
            service_id = part[1:]
        elif part.startswith('d'):
            doctor_id = part[1:]
    
    context.user_data['selected_service'] = service_id
    context.user_data['selected_doctor'] = doctor_id
    context.user_data['selected_date'] = selected_date
    
    # دریافت زمان‌های خالی
    available_slots = get_available_time_slots(doctor_id, selected_date)
    
    if not available_slots:
        keyboard = [[InlineKeyboardButton("🔙 انتخاب تاریخ دیگر", callback_data=f"book_doctor_{doctor_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "❌ **در این تاریخ نوبت خالی موجود نیست.**\n\n"
            "لطفاً تاریخ دیگری انتخاب کنید:",
            reply_markup=reply_markup
        )
        return
    
    # نمایش زمان‌های خالی
    keyboard = []
    row = []
    for i, slot in enumerate(available_slots):
        row.append(InlineKeyboardButton(f"⏰ {slot}", callback_data=f'book_time_{slot}'))
        if (i + 1) % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به تاریخ‌ها", callback_data=f"book_doctor_{doctor_id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # نمایش تاریخ به صورت فارسی
    date_obj = jdatetime.datetime.strptime(selected_date, '%Y-%m-%d')
    date_display = date_obj.strftime('%d %B %Y')
    
    await query.edit_message_text(
        f"⏰ **انتخاب زمان برای {date_display}**\n\n"
        "لطفاً زمان مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def handle_time_selection(update, context):
    """انتخاب زمان نوبت"""
    query = update.callback_query
    await safe_answer_query(query)
    
    selected_time = query.data.split('_')[2]
    context.user_data['selected_time'] = selected_time
    
    # ایجاد نوبت
    user_id = get_user_id(update.effective_user.id)
    
    if not user_id:
        await query.edit_message_text("❌ خطا در یافتن اطلاعات کاربر.")
        return
    
    appointment_id = create_appointment(
        user_id,
        context.user_data['selected_service'],
        context.user_data['selected_doctor'],
        context.user_data['selected_date'],
        selected_time
    )
    
    if appointment_id:
        # دریافت اطلاعات خدمت
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.name, s.base_price, d.name 
            FROM services s, doctors d 
            WHERE s.id = ? AND d.id = ?
        ''', (context.user_data['selected_service'], context.user_data['selected_doctor']))
        result = cursor.fetchone()
        conn.close()
        
        service_name, service_price, doctor_name = result
        
        # نمایش تاریخ به صورت فارسی
        date_obj = jdatetime.datetime.strptime(context.user_data['selected_date'], '%Y-%m-%d')
        date_display = date_obj.strftime('%d %B %Y')
        
        success_text = (
            f"🎉 **نوبت شما با موفقیت ثبت شد!**\n\n"
            f"📋 خدمت: {service_name}\n"
            f"👨‍⚕️ پزشک: {doctor_name}\n"
            f"📅 تاریخ: {date_display}\n"
            f"⏰ زمان: {selected_time}\n"
            f"💰 هزینه: {service_price:,} تومان\n"
            f"🆔 کد رهگیری: {appointment_id:04d}\n\n"
            f"💳 **برای پرداخت از منوی پرداخت استفاده کنید.**"
        )
        
        context.user_data['last_appointment_id'] = appointment_id
        
        keyboard = [
            [InlineKeyboardButton("💳 پرداخت", callback_data="payment_receipt")],
            [InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(success_text, reply_markup=reply_markup)
    else:
        await query.edit_message_text("❌ خطا در ثبت نوبت.")

# ==================== PAYMENT SYSTEM ====================

async def start_payment_with_receipt(update, context):
    """شروع فرآیند پرداخت با آپلود فیش"""
    query = update.callback_query
    await safe_answer_query(query)
    
    payment_info = (
        f"💳 **پرداخت با آپلود فیش**\n\n"
        f"💳 **شماره کارت برای واریز:**\n"
        f"`6219-8610-3456-7890`\n\n"
        f"🏛️ **بانک:** پارسیان\n"
        f"👤 **به نام:** کلینیک زیبایی گلوریا\n\n"
        f"📸 لطفاً پس از واریز، عکس فیش واریزی را به همین ربات ارسال کنید.\n"
        f"✅ پس از تأیید فیش، نوبت شما فعال خواهد شد.\n\n"
        f"📞 **پشتیبانی:** ۰۹۱۹۰۴۳۲۱۸۱"
    )
    
    keyboard = [
        [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(payment_info, reply_markup=reply_markup, parse_mode='Markdown')
    
    context.user_data['awaiting_receipt'] = True
    return UPLOAD_RECEIPT

async def handle_receipt_photo(update, context):
    """دریافت عکس فیش واریزی"""
    if not context.user_data.get('awaiting_receipt'):
        return ConversationHandler.END
    
    try:
        photo = update.message.photo[-1]
        file_id = photo.file_id
        
        # ذخیره اطلاعات پرداخت
        user_id = get_user_id(update.effective_user.id)
        
        if user_id:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO payments (user_id, amount, payment_method, receipt_photo, status)
                VALUES (?, 0, 'receipt', ?, 'pending')
            ''', (user_id, file_id))
            
            conn.commit()
            conn.close()
            
            # اطلاع به ادمین
            await notify_admin_new_receipt(context, file_id, update.effective_user.full_name)
        
        context.user_data['awaiting_receipt'] = False
        
        await update.message.reply_text(
            "✅ فیش واریزی شما دریافت شد و در انتظار تأیید می‌باشد.\n"
            "🔔 پس از تأیید، از طریق ربات به شما اطلاع داده خواهد شد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]])
        )
        
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error handling receipt: {e}")
        await update.message.reply_text("❌ خطا در پردازش فیش. لطفاً دوباره تلاش کنید.")

async def notify_admin_new_receipt(context, file_id, user_name):
    """اطلاع به ادمین درباره فیش جدید"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # پیدا کردن ادمین‌ها
        cursor.execute('''
            SELECT u.chat_id FROM users u
            JOIN admin_access aa ON u.id = aa.user_id
        ''')
        admins = cursor.fetchall()
        conn.close()
        
        if admins:
            message_text = (
                f"🔔 **فیش واریزی جدید**\n\n"
                f"👤 کاربر: {user_name}\n"
                f"📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
            
            for admin in admins:
                try:
                    await context.bot.send_photo(
                        chat_id=admin[0],
                        photo=file_id,
                        caption=message_text
                    )
                except Exception as e:
                    logger.error(f"Error notifying admin: {e}")
    except Exception as e:
        logger.error(f"Error in notify_admin: {e}")

# ==================== MESSAGE HANDLERS ====================

async def handle_message(update, context):
    """هندلر پیام‌های متنی"""
    # اول بررسی کن اگر کاربر در حال ورود ادمین است
    if context.user_data.get('awaiting_admin_username'):
        await handle_admin_username(update, context)
        return
    
    if context.user_data.get('awaiting_admin_password'):
        await handle_admin_password(update, context)
        return
    
    if context.user_data.get('in_conversation'):
        return
    
    if context.user_data.get('awaiting_name'):
        full_name = update.message.text
        context.user_data['full_name'] = full_name
        context.user_data['awaiting_name'] = False
        context.user_data['awaiting_phone'] = True
        
        keyboard = [
            [KeyboardButton("📞 اشتراک‌گذاری شماره تماس", request_contact=True)],
            [KeyboardButton("📝 وارد کردن دستی شماره")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text(
            f"ممنون {full_name}!\nلطفاً شماره تماس خود را وارد کنید:",
            reply_markup=reply_markup
        )
        return
    
    elif context.user_data.get('awaiting_phone'):
        phone_text = update.message.text
        
        if phone_text == "📝 وارد کردن دستی شماره":
            await update.message.reply_text("لطفاً شماره تماس خود را وارد کنید:\nمثال: ۰۹۱۲۳۴۵۶۷۸۹")
            return
        
        phone_number = validate_phone_number(phone_text)
        if not phone_number:
            await update.message.reply_text("❌ شماره تماس معتبر نیست! لطفاً دوباره وارد کنید.")
            return
        
        context.user_data['phone_number'] = phone_number
        context.user_data['awaiting_phone'] = False
        
        save_user_to_db(update.effective_user.id, context.user_data['full_name'], phone_number)
        
        remove_keyboard = ReplyKeyboardRemove()
        await update.message.reply_text(
            f"✅ اطلاعات شما ثبت شد!\n📋 نام: {context.user_data['full_name']}\n📞 تلفن: {phone_number}",
            reply_markup=remove_keyboard
        )
        
        await show_main_menu(update, context)
        return
    
    else:
        await update.message.reply_text("لطفاً از منوی اصلی استفاده کنید.")

async def handle_contact(update, context):
    """هندلر اشتراک‌گذاری شماره تماس"""
    if context.user_data.get('awaiting_phone'):
        phone_number = update.message.contact.phone_number
        context.user_data['phone_number'] = phone_number
        context.user_data['awaiting_phone'] = False
        
        save_user_to_db(update.effective_user.id, context.user_data['full_name'], phone_number)
        
        remove_keyboard = ReplyKeyboardRemove()
        await update.message.reply_text(
            f"✅ اطلاعات شما ثبت شد!\n📋 نام: {context.user_data['full_name']}\n📞 تلفن: {phone_number}",
            reply_markup=remove_keyboard
        )
        
        await show_main_menu(update, context)

# ==================== UTILITY FUNCTIONS ====================

def get_available_time_slots(doctor_id, appointment_date):
    """دریافت زمان‌های خالی برای یک پزشک در تاریخ مشخص"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT appointment_time FROM appointments 
            WHERE doctor_id = ? AND appointment_date = ? AND status != 'cancelled'
        ''', (doctor_id, appointment_date))
        
        booked_slots = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        # زمان‌های کاری کلینیک
        all_slots = []
        start_time = datetime.strptime('09:00', '%H:%M')
        end_time = datetime.strptime('21:00', '%H:%M')
        
        current_time = start_time
        while current_time < end_time:
            time_str = current_time.strftime('%H:%M')
            if time_str not in booked_slots:
                all_slots.append(time_str)
            current_time += timedelta(minutes=30)
        
        return all_slots
    except Exception as e:
        logger.error(f"Error getting time slots: {e}")
        return ['10:00', '11:00', '12:00', '14:00', '15:00', '16:00', '17:00', '18:00']

def get_doctors_for_service(service_id):
    """دریافت پزشکان مرتبط با یک خدمت"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT category FROM services WHERE id = ?', (service_id,))
        result = cursor.fetchone()
        if not result:
            return []
        
        service_category = result[0]
        
        cursor.execute('SELECT id, name, specialization FROM doctors WHERE services LIKE ? AND available = TRUE', (f'%{service_category}%',))
        doctors = cursor.fetchall()
        conn.close()
        
        return doctors
    except Exception as e:
        logger.error(f"Error getting doctors: {e}")
        return [(1, 'دکتر مریم احمدی', 'پوست و زیبایی'), (2, 'دکتر سارا محمدی', 'لیزر و زیبایی')]

def get_user_id(chat_id):
    """دریافت ID کاربر از chat_id"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE chat_id = ?', (chat_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Error getting user id: {e}")
        return 1

def create_appointment(user_id, service_id, doctor_id, appointment_date, appointment_time):
    """ایجاد نوبت جدید"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO appointments (user_id, service_id, doctor_id, appointment_date, appointment_time, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        ''', (user_id, service_id, doctor_id, appointment_date, appointment_time))
        
        appointment_id = cursor.lastrowid
        conn.commit()
        logger.info(f"Appointment created: ID {appointment_id}")
        return appointment_id
    except Exception as e:
        logger.error(f"Error creating appointment: {e}")
        return 1000 + user_id
    finally:
        conn.close()

async def show_contact_info(update, context):
    """نمایش اطلاعات تماس"""
    query = update.callback_query
    await safe_answer_query(query)
    
    contact_text = (
        "📍 **اطلاعات تماس کلینیک گلوریا**\n\n"
        "📞 تلفن: ۰۲۱-۸۸۵۶۱۲۳۴\n"
        "📱 واتساپ: ۰۹۱۹۰۴۳۲۱۸۱\n"
        "🏢 آدرس: تهران، خیابان ولیعصر، بالاتر از میدان ونک، پلاک ۲۱۰۰\n\n"
        "🕒 ساعت کاری:\n"
        "شنبه تا پنجشنبه: ۹:۰۰ تا ۲۱:۰۰\n"
        "جمعه: ۱۰:۰۰ تا ۱۸:۰۰"
    )
    
    keyboard = [
        [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(contact_text, reply_markup=reply_markup)

async def show_guide(update, context):
    """نمایش راهنمای استفاده"""
    query = update.callback_query
    await safe_answer_query(query)
    
    guide_text = (
        "📖 **راهنمای استفاده از ربات**\n\n"
        "🎯 **نوبت‌گیری:** از منوی اصلی گزینه رزرو نوبت را انتخاب کنید\n"
        "💬 **مشاوره:** پاسخ سوالات تخصصی پوست و زیبایی\n"
        "💳 **پرداخت:** آپلود فیش واریزی\n"
        "👨‍💼 **ادمین:** مشاهده گزارش‌ها و مدیریت\n\n"
        "📞 **پشتیبانی:** ۰۹۱۹۰۴۳۲۱۸۱"
    )
    
    keyboard = [
        [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(guide_text, reply_markup=reply_markup)

async def show_doctors(update, context):
    """نمایش لیست پزشکان"""
    query = update.callback_query
    await safe_answer_query(query)
    
    doctors_text = "👨‍⚕️ **تیم پزشکی کلینیک گلوریا**\n\n"
    doctors_text += "**۱. دکتر مریم احمدی**\n📋 پوست و زیبایی\n⭐ ۱۲ سال سابقه\n\n"
    doctors_text += "**۲. دکتر سارا محمدی**\n📋 لیزر و زیبایی\n⭐ ۱۰ سال سابقه\n\n"
    doctors_text += "**۳. دکتر حمید کریمی**\n📋 تزریقات زیبایی\n⭐ ۷ سال سابقه\n\n"
    doctors_text += "**۴. دکتر علی رضایی**\n📋 کاشت مو\n⭐ ۸ سال سابقه"
    
    keyboard = [
        [InlineKeyboardButton("📅 رزرو نوبت", callback_data="menu_booking")],
        [InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(doctors_text, reply_markup=reply_markup)

# ==================== MAIN FUNCTION ====================

def main():
    """تابع اصلی"""
    # ابتدا دیتابیس را مقداردهی اولیه کن
    init_db()
    
    # تنظیمات اتصال
    application = Application.builder().token(TOKEN).build()
    
    # هندلرهای اصلی
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # هندلر آپلود فیش
    application.add_handler(MessageHandler(filters.PHOTO, handle_receipt_photo))
    
    # هندلرهای منوی اصلی
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern='^back_to_main$'))
    application.add_handler(CallbackQueryHandler(show_beauty_services, pattern='^menu_beauty$'))
    application.add_handler(CallbackQueryHandler(show_beauty_services, pattern='^menu_booking$'))
    application.add_handler(CallbackQueryHandler(show_contact_info, pattern='^menu_contact$'))
    application.add_handler(CallbackQueryHandler(show_guide, pattern='^menu_guide$'))
    application.add_handler(CallbackQueryHandler(show_doctors, pattern='^menu_doctors$'))
    
    # هندلرهای ادمین ساده
    application.add_handler(CallbackQueryHandler(start_admin_login_simple, pattern='^admin_login_simple$'))
    application.add_handler(CallbackQueryHandler(show_admin_panel_simple, pattern='^admin_panel_simple$'))
    application.add_handler(CallbackQueryHandler(admin_logout_simple, pattern='^admin_logout_simple$'))
    application.add_handler(CallbackQueryHandler(admin_view_appointments, pattern='^admin_view_appointments$'))
    application.add_handler(CallbackQueryHandler(admin_view_payments, pattern='^admin_view_payments$'))
    application.add_handler(CallbackQueryHandler(admin_view_users, pattern='^admin_view_users$'))
    application.add_handler(CallbackQueryHandler(admin_view_stats, pattern='^admin_view_stats$'))
    
    # هندلرهای خدمات زیبایی
    application.add_handler(CallbackQueryHandler(show_laser_services, pattern='^laser_services$'))
    application.add_handler(CallbackQueryHandler(show_laser_by_gender, pattern='^(laser_women|laser_men)$'))
    application.add_handler(CallbackQueryHandler(handle_category_selection, pattern='^category_'))
    
    # هندلرهای رزرو نوبت
    application.add_handler(CallbackQueryHandler(handle_service_selection_booking, pattern='^book_service_'))
    application.add_handler(CallbackQueryHandler(handle_doctor_selection_calendar, pattern='^book_doctor_'))
    application.add_handler(CallbackQueryHandler(handle_date_selection, pattern='^book_date_'))
    application.add_handler(CallbackQueryHandler(handle_time_selection, pattern='^book_time_'))
    
    # هندلر پرداخت
    application.add_handler(CallbackQueryHandler(start_payment_with_receipt, pattern='^payment_receipt$'))
    
    logger.info("Bot is starting with simple admin system...")
    
    try:
        application.run_polling(
            poll_interval=3.0,
            timeout=30,
            drop_pending_updates=True
        )
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        asyncio.run(asyncio.sleep(5))
        main()

if __name__ == '__main__':
    main()
