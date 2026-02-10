import asyncio
import sys
import os

# ==== FIX: Event Loop for Python 3.10+ and Pyrogram ====
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
else:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

import logging
import re
import secrets
import contextlib
from threading import Thread
import time
import sqlite3
import json
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, timedelta
import html
import traceback
import random

# --- Telegram Bot Imports (PTB) ---
from telegram import (Update, ReplyKeyboardMarkup, KeyboardButton,
                      InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove,
                      InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultCachedPhoto)
from telegram.constants import ParseMode, ChatAction as PTBChatAction
from telegram.ext import (Application, CommandHandler, MessageHandler,
                          ConversationHandler, filters, ContextTypes, CallbackQueryHandler,
                          ApplicationHandlerStop, TypeHandler, InlineQueryHandler)
import telegram.error

# --- Pyrogram Imports (Self Bot) ---
from pyrogram import Client, filters as pyro_filters, idle
from pyrogram.handlers import MessageHandler as PyroMessageHandler
from pyrogram.enums import ChatType, ChatAction
from pyrogram.raw import functions
from pyrogram.errors import (
    SessionPasswordNeeded, PhoneCodeInvalid, PasswordHashInvalid,
    PhoneNumberInvalid, PhoneCodeExpired, UserDeactivated, AuthKeyUnregistered,
    ChatSendInlineForbidden
)
import pyrogram.utils

# =======================================================
#  بخش ۱: تنظیمات اولیه و پیکربندی
# =======================================================

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

def patch_peer_id_validation():
    original_get_peer_type = pyrogram.utils.get_peer_type
    def patched_get_peer_type(peer_id: int) -> str:
        try:
            return original_get_peer_type(peer_id)
        except ValueError:
            if str(peer_id).startswith("-100"):
                return "channel"
            raise
    pyrogram.utils.get_peer_type = patched_get_peer_type

patch_peer_id_validation()

# --- Environment Variables (SECURE) ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8481431417:AAEB4dNawnyCQBH8KHtkKaFaQu_AcbmlHu0")
API_ID = int(os.getenv("API_ID", "9536480"))
API_HASH = os.getenv("API_HASH", "4e52f6f12c47a0da918009260b6e3d44")
OWNER_ID = int(os.getenv("OWNER_ID", "5789565027"))
TEHRAN_TIMEZONE = ZoneInfo("Asia/Tehran")

# --- SQLite Database Configuration ---
DB_NAME = "bot_database.db"

# --- In-Memory Cache (For Performance, synced with DB) ---
GLOBAL_USERS = {}
GLOBAL_SETTINGS = {}
GLOBAL_TRANSACTIONS = {}
GLOBAL_BETS = {}
GLOBAL_CHANNELS = {}

# Active Pyrogram Clients
ACTIVE_BOTS = {}
LOGIN_STATES = {}

TX_ID_COUNTER = 1
BET_ID_COUNTER = 1
BOT_USERNAME = ""

# --- Conversation States ---
(ADMIN_MENU, AWAIT_ADMIN_REPLY,
 AWAIT_ADMIN_SET_CARD_NUMBER, AWAIT_ADMIN_SET_CARD_HOLDER,
 AWAIT_NEW_CHANNEL, AWAIT_BET_PHOTO,
 AWAIT_ADMIN_SET_BALANCE_ID, AWAIT_ADMIN_SET_BALANCE,
 AWAIT_ADMIN_ADD_BALANCE_ID, AWAIT_ADMIN_ADD_BALANCE_AMOUNT,
 AWAIT_ADMIN_DEDUCT_BALANCE_ID, AWAIT_ADMIN_DEDUCT_BALANCE_AMOUNT,
 AWAIT_ADMIN_TAX, AWAIT_ADMIN_CREDIT_PRICE, AWAIT_ADMIN_REFERRAL_PRICE,
 AWAIT_MANAGE_USER_ID, AWAIT_MANAGE_USER_ROLE,
 AWAIT_BROADCAST_MESSAGE,
 AWAIT_SELF_CONTACT, AWAIT_SELF_CODE, AWAIT_SELF_PASSWORD,
 AWAIT_ADMIN_SELF_COST, AWAIT_ADMIN_SELF_MIN, AWAIT_ADMIN_SELF_PHOTO,
 AWAIT_DEPOSIT_AMOUNT, AWAIT_DEPOSIT_RECEIPT,
 AWAIT_SUPPORT_MESSAGE, AWAIT_ADMIN_SUPPORT_REPLY
) = range(28)

# --- Constants ---
FONT_STYLES = {
    "cursive":      {'0':'𝟎','1':'𝟏','2':'𝟐','3':'𝟑','4':'𝟒','5':'𝟓','6':'𝟔','7':'𝟕','8':'𝟖','9':'𝟗',':':':'},
    "stylized":     {'0':'𝟬','1':'𝟭','2':'𝟮','3':'𝟯','4':'𝟰','5':'𝟱','6':'𝟲','7':'𝟳','8':'𝟴','9':'𝟵',':':':'},
    "doublestruck": {'0':'𝟘','1':'𝟙','2':'𝟚','3':'𝟛','4':'𝟜','5':'𝟝','6':'𝟞','7':'𝟟','8':'𝟠','9':'𝟡',':':':'},
    "monospace":    {'0':'𝟶','1':'𝟷','2':'𝟸','3':'𝟹','4':'𝟺','5':'𝟻','6':'𝟼','7':'𝟽','8':'𝟾','9':'𝟿',':':':'},
    "normal":       {'0':'0','1':'1','2':'2','3':'3','4':'4','5':'5','6':'6','7':'7','8':'8','9':'9',':':':'},
    "circled":      {'0':'⓪','1':'①','2':'②','3':'③','4':'④','5':'⑤','6':'⑥','7':'⑦','8':'⑧','9':'⑨',':':'∶'},
    "fullwidth":    {'0':'０','1':'１','2':'２','3':'３','4':'４','5':'５','6':'６','7':'７','8':'۸','9':'۹',':':'：'},
    "filled":       {'0':'⓿','1':'❶','2':'❷','3':'❸','4':'❹','5':'❺','6':'❻','7':'❼','8':'❽','9':'❾',':':':'},
    "sans":         {'0':'𝟢','1':'𝟣','2':'𝟤','3':'𝟥','4':'𝟦','5':'𝟧','6':'𝟨','7':'𝟩','8':'𝟪','9':'𝟫',':':':'},
    "inverted":     {'0':'0','1':'Ɩ','2':'ᄅ','3':'Ɛ','4':'ㄣ','5':'ϛ','6':'9','7':'ㄥ','8':'8','9':'6',':':':'},
}
FONT_KEYS_ORDER = ["cursive", "stylized", "doublestruck", "monospace", "normal", "circled", "fullwidth", "filled", "sans", "inverted"]
ALL_CLOCK_CHARS = "".join(set(char for font in FONT_STYLES.values() for char in font.values()))
CLOCK_CHARS_REGEX_CLASS = f"[{re.escape(ALL_CLOCK_CHARS)}]"

ENEMY_REPLIES = ["ببخشید متوجه نشدم؟", "داری فشار میخوری؟", "برو پیش بزرگترت", "سطحت پایینه", "😂😂", "اوکی بای"]
SECRETARY_REPLY_MESSAGE = "سلام! در حال حاضر آفلاین هستم و پیام شما را دریافت کردم. در اولین فرصت پاسخ خواهم داد. ممنون از پیامتون."
HELP_TEXT = """
**[ 🛠 دستورات دستی و ریپلای سلف ]**
━━━━━━━━━━━━━━━━━━━━
⚠️ تنظیمات اصلی (ساعت، فونت، منشی و...) فقط از طریق دستور **`پنل`** در اکانت خودتان قابل دسترسی هستند.

**✦ مدیریت پیام و چت**
  » `حذف [تعداد]` 
  » `ذخیره` (ریپلای روی پیام)
  » `تکرار [تعداد]` (ریپلای روی پیام)
  » `کپی روشن` | `کپی خاموش` (ریپلای روی کاربر)

**✦ دفاعی و امنیتی**
  » `دشمن روشن` | `خاموش` (ریپلای روی کاربر)
  » `لیست دشمن`
  » `بلاک روشن` | `بلاک خاموش` (ریپلای روی کاربر)
  » `سکوت روشن` | `سکوت خاموش` (ریپلای روی کاربر)
  » `ریاکشن [شکلک]` | `خاموش` (ریپلای روی کاربر)

**✦ سرگرمی**
  » `تاس` | `تاس [عدد]`
  » `بولینگ`

**✦ سایر**
  » `پنل` (نمایش منوی تنظیمات)
━━━━━━━━━━━━━━━━━━━━
"""
COMMAND_REGEX = r"^(راهنما|ذخیره|تکرار \d+|حذف \d+|ریاکشن .*|ریاکشن خاموش|کپی روشن|کپی خاموش|لیست دشمن|تاس|تاس \d+|بولینگ|تنظیم عکس|حذف عکس|پنل|panel)$"

# --- Self Bot State Dictionaries ---
ACTIVE_ENEMIES = {}
ENEMY_REPLY_QUEUES = {}
SECRETARY_MODE_STATUS = {}
USERS_REPLIED_IN_SECRETARY = {}
MUTED_USERS = {}
USER_FONT_CHOICES = {}
CLOCK_STATUS = {}
BOLD_MODE_STATUS = {}
AUTO_SEEN_STATUS = {}
AUTO_REACTION_TARGETS = {}
AUTO_TRANSLATE_TARGET = {}
ANTI_LOGIN_STATUS = {}
COPY_MODE_STATUS = {}
ORIGINAL_PROFILE_DATA = {}
GLOBAL_ENEMY_STATUS = {}
TYPING_MODE_STATUS = {}
PLAYING_MODE_STATUS = {}
PV_LOCK_STATUS = {}

# =======================================================
#  بخش ۲: مدیریت دیتابیس SQLite
# =======================================================

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    global TX_ID_COUNTER, BET_ID_COUNTER
    logging.info("Initializing SQLite database...")
    conn = get_db_connection()
    c = conn.cursor()
    
    # Create Tables
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id INTEGER PRIMARY KEY,
                 data TEXT
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                 tx_id INTEGER PRIMARY KEY,
                 data TEXT
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS bets (
                 bet_id INTEGER PRIMARY KEY,
                 data TEXT
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS channels (
                 username TEXT PRIMARY KEY,
                 data TEXT
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
                 phone TEXT PRIMARY KEY,
                 session_string TEXT,
                 user_id INTEGER,
                 real_owner_id INTEGER,
                 settings TEXT
                 )''')
    conn.commit()
    
    # Load Data into Memory
    try:
        for row in c.execute('SELECT * FROM settings'):
            GLOBAL_SETTINGS[row['key']] = row['value']
        
        for row in c.execute('SELECT * FROM users'):
            GLOBAL_USERS[row['user_id']] = json.loads(row['data'])
            
        max_tx_id = 0
        for row in c.execute('SELECT * FROM transactions'):
            tx_data = json.loads(row['data'])
            tx_id = tx_data['tx_id']
            GLOBAL_TRANSACTIONS[tx_id] = tx_data
            if tx_id > max_tx_id: max_tx_id = tx_id
        TX_ID_COUNTER = max_tx_id + 1
        
        max_bet_id = 0
        for row in c.execute('SELECT * FROM bets'):
            bet_data = json.loads(row['data'])
            bet_id = bet_data['bet_id']
            GLOBAL_BETS[bet_id] = bet_data
            if bet_id > max_bet_id: max_bet_id = bet_id
        BET_ID_COUNTER = max_bet_id + 1
        
        for row in c.execute('SELECT * FROM channels'):
            GLOBAL_CHANNELS[row['username']] = json.loads(row['data'])
            
    except Exception as e:
        logging.error(f"Error loading data from DB: {e}")
    finally:
        conn.close()

    defaults = {
        'credit_price': '1000', 'initial_balance': '10', 'referral_reward': '5',
        'bet_tax_rate': '2', 'card_number': 'تنظیم نشده', 'card_holder': 'تنظیم نشده',
        'bet_photo_file_id': 'None', 'forced_channel_lock': 'false',
        'self_bot_hourly_cost': '1', 'self_bot_min_balance': '10', 'self_panel_photo': 'None'
    }
    for k, v in defaults.items():
        if k not in GLOBAL_SETTINGS: GLOBAL_SETTINGS[k] = v

def save_user_immediate(user_id):
    if user_id not in GLOBAL_USERS: return
    conn = get_db_connection()
    try:
        data_json = json.dumps(GLOBAL_USERS[user_id])
        conn.execute('INSERT OR REPLACE INTO users (user_id, data) VALUES (?, ?)', (user_id, data_json))
        conn.commit()
    except Exception as e:
        logging.error(f"Save User Error: {e}")
    finally:
        conn.close()

async def get_setting_async(name): return GLOBAL_SETTINGS.get(name)
async def set_setting_async(name, value):
    GLOBAL_SETTINGS[name] = str(value)
    conn = get_db_connection()
    try:
        conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (name, str(value)))
        conn.commit()
    finally:
        conn.close()

async def get_user_async(user_id):
    if user_id in GLOBAL_USERS:
        u = GLOBAL_USERS[user_id]
        if 'vip_balance' not in u: u['vip_balance'] = 0
        if 'self_active' not in u: u['self_active'] = False
        if 'self_last_payment' not in u: u['self_last_payment'] = 0
        return u
    
    try: bal = int(GLOBAL_SETTINGS.get('initial_balance', '10'))
    except: bal = 10
    is_owner = (user_id == OWNER_ID)
    start_bal = 1000000000 if is_owner else bal
    
    new_u = {
        'user_id': user_id, 'balance': start_bal, 'vip_balance': 0,
        'is_admin': is_owner, 'is_owner': is_owner, 'referred_by': None,
        'is_moderator': False, 'username': None, 'first_name': None,
        'self_active': False, 'self_last_payment': 0
    }
    GLOBAL_USERS[user_id] = new_u
    save_user_immediate(user_id)
    return new_u

def save_self_settings_to_db(user_id):
    enemies_list = list(ACTIVE_ENEMIES.get(user_id, set()))
    muted_list = list(MUTED_USERS.get(user_id, set()))
    reaction_targets = {str(k): v for k, v in AUTO_REACTION_TARGETS.get(user_id, {}).items()}

    settings = {
        'clock': CLOCK_STATUS.get(user_id, True),
        'font': USER_FONT_CHOICES.get(user_id, 'stylized'),
        'bold': BOLD_MODE_STATUS.get(user_id, False),
        'secretary': SECRETARY_MODE_STATUS.get(user_id, False),
        'seen': AUTO_SEEN_STATUS.get(user_id, False),
        'pv_lock': PV_LOCK_STATUS.get(user_id, False),
        'anti_login': ANTI_LOGIN_STATUS.get(user_id, False),
        'typing': TYPING_MODE_STATUS.get(user_id, False),
        'playing': PLAYING_MODE_STATUS.get(user_id, False),
        'global_enemy': GLOBAL_ENEMY_STATUS.get(user_id, False),
        'translate': AUTO_TRANSLATE_TARGET.get(user_id),
        'enemies': enemies_list,
        'muted': muted_list,
        'reactions': reaction_targets
    }
    
    conn = get_db_connection()
    try:
        conn.execute('UPDATE sessions SET settings = ? WHERE real_owner_id = ?', (json.dumps(settings), user_id))
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to save settings for {user_id}: {e}")
    finally:
        conn.close()

def load_self_settings_from_db(user_id, doc_row):
    settings_json = doc_row['settings']
    if not settings_json: return
    settings = json.loads(settings_json)
    
    CLOCK_STATUS[user_id] = settings.get('clock', True)
    USER_FONT_CHOICES[user_id] = settings.get('font', 'stylized')
    BOLD_MODE_STATUS[user_id] = settings.get('bold', False)
    SECRETARY_MODE_STATUS[user_id] = settings.get('secretary', False)
    AUTO_SEEN_STATUS[user_id] = settings.get('seen', False)
    PV_LOCK_STATUS[user_id] = settings.get('pv_lock', False)
    ANTI_LOGIN_STATUS[user_id] = settings.get('anti_login', False)
    TYPING_MODE_STATUS[user_id] = settings.get('typing', False)
    PLAYING_MODE_STATUS[user_id] = settings.get('playing', False)
    GLOBAL_ENEMY_STATUS[user_id] = settings.get('global_enemy', False)
    AUTO_TRANSLATE_TARGET[user_id] = settings.get('translate')
    
    enemies_raw = settings.get('enemies', [])
    ACTIVE_ENEMIES[user_id] = set(tuple(x) for x in enemies_raw)
    muted_raw = settings.get('muted', [])
    MUTED_USERS[user_id] = set(tuple(x) for x in muted_raw)
    reactions_raw = settings.get('reactions', {})
    AUTO_REACTION_TARGETS[user_id] = {int(k): v for k, v in reactions_raw.items()}

# =======================================================
#  بخش ۳: توابع کمکی ربات
# =======================================================

def get_user_display_name(user):
    if user.id in GLOBAL_USERS:
        GLOBAL_USERS[user.id]['username'] = user.username
        GLOBAL_USERS[user.id]['first_name'] = user.first_name
    return f"@{user.username}" if user.username else html.escape(user.first_name or "User")

def get_main_keyboard(user_doc):
    if user_doc.get('is_owner'):
        return ReplyKeyboardMarkup([
            [KeyboardButton("💰 موجودی"), KeyboardButton("👑 پنل ادمین")],
            [KeyboardButton("🤖 فعال‌سازی سلف")]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup([
            [KeyboardButton("💰 موجودی"), KeyboardButton("💳 افزایش الماس")],
            [KeyboardButton("🎁 الماس رایگان"), KeyboardButton("💬 پشتیبانی")],
            [KeyboardButton("🤖 فعال‌سازی سلف")]
        ], resize_keyboard=True)

admin_keyboard = ReplyKeyboardMarkup([
    [KeyboardButton("📊 آمار کلی"), KeyboardButton("💳 تنظیم شماره کارت")],
    [KeyboardButton("👤 تنظیم صاحب کارت"), KeyboardButton("مدیریت کاربر")],
    [KeyboardButton("➕ افزایش الماس کاربر"), KeyboardButton("➖ کسر الماس کاربر")],
    [KeyboardButton("💰 تنظیم الماس (ست)"), KeyboardButton("📈 تنظیم قیمت الماس")],
    [KeyboardButton("⚙️ هزینه سلف (ساعتی)"), KeyboardButton("💎 حداقل موجودی سلف")],
    [KeyboardButton("🖼 تنظیم عکس پنل سلف"), KeyboardButton("🗑 حذف عکس پنل سلف")],
    [KeyboardButton("🎁 تنظیم پاداش دعوت"), KeyboardButton("📉 تنظیم مالیات (۰-۱۰۰)")],
    [KeyboardButton("➕ افزودن کانال عضویت"), KeyboardButton("➖ حذف کانال عضویت")],
    [KeyboardButton("👁‍🗨 لیست کانال‌های عضویت"), KeyboardButton("🔒 قفل عضویت: روشن"), KeyboardButton("🔓 قفل عضویت: خاموش")],
    [KeyboardButton("🖼 تنظیم عکس شرط"), KeyboardButton("🗑 حذف عکس شرط")],
    [KeyboardButton("📢 پیام همگانی")],
    [KeyboardButton("⬅️ بازگشت به منوی اصلی")]
], resize_keyboard=True)

bet_group_keyboard = ReplyKeyboardMarkup([
    [KeyboardButton("موجودی 💰")],
    [KeyboardButton("شرط 100"), KeyboardButton("شرط 500")],
    [KeyboardButton("شرط 1000"), KeyboardButton("شرط 5000")]
], resize_keyboard=True)

def stylize_time(time_str: str, style: str) -> str:
    font_map = FONT_STYLES.get(style, FONT_STYLES["stylized"])
    return ''.join(font_map.get(char, char) for char in time_str)

async def stop_self_bot_due_to_auth(user_id):
    logging.warning(f"Stopping self-bot for {user_id} due to invalid session.")
    if user_id in ACTIVE_BOTS:
        client, tasks = ACTIVE_BOTS[user_id]
        del ACTIVE_BOTS[user_id] 
        try: await client.stop() 
        except: pass
        for t in tasks: t.cancel()
    
    if user_id in GLOBAL_USERS:
        GLOBAL_USERS[user_id]['self_active'] = False
        save_user_immediate(user_id)
        
    conn = get_db_connection()
    try: conn.execute('DELETE FROM sessions WHERE real_owner_id = ?', (user_id,)); conn.commit()
    except: pass
    finally: conn.close()

async def perform_clock_update_now(client, user_id):
    try:
        if CLOCK_STATUS.get(user_id, True) and not COPY_MODE_STATUS.get(user_id, False):
            current_font_style = USER_FONT_CHOICES.get(user_id, 'stylized')
            me = await client.get_me()
            current_name = me.first_name
            base_name = re.sub(r'(?:\s*' + CLOCK_CHARS_REGEX_CLASS + r'+)+$', '', current_name).strip()
            
            tehran_time = datetime.now(TEHRAN_TIMEZONE)
            current_time_str = tehran_time.strftime("%H:%M")
            stylized_time = stylize_time(current_time_str, current_font_style)
            new_name = f"{base_name} {stylized_time}"
            
            if new_name != current_name:
                await client.update_profile(first_name=new_name)
    except (AuthKeyUnregistered, UserDeactivated):
        await stop_self_bot_due_to_auth(user_id)
    except Exception as e:
        logging.error(f"Immediate clock update failed: {e}")

async def translate_text(text: str, target_lang: str) -> str:
    return text

def get_panel_photo(user_id):
    global_photo = GLOBAL_SETTINGS.get('self_panel_photo')
    if global_photo and global_photo != 'None':
        return global_photo
    return None

async def update_profile_clock(client: Client, user_id: int):
    while user_id in ACTIVE_BOTS:
        try:
            if CLOCK_STATUS.get(user_id, True) and not COPY_MODE_STATUS.get(user_id, False):
                await perform_clock_update_now(client, user_id)
            now = datetime.now(TEHRAN_TIMEZONE)
            await asyncio.sleep(60 - now.second + 0.1)
        except Exception: await asyncio.sleep(60)

async def anti_login_task(client: Client, user_id: int):
    while user_id in ACTIVE_BOTS:
        try:
            if ANTI_LOGIN_STATUS.get(user_id, False):
                auths = await client.invoke(functions.account.GetAuthorizations())
                current_hash = next((a.hash for a in auths.authorizations if a.current), None)
                if current_hash:
                    for auth in auths.authorizations:
                        if auth.hash != current_hash:
                            await client.invoke(functions.account.ResetAuthorization(hash=auth.hash))
                            await client.send_message("me", f"🚨 نشست غیرمجاز حذف شد: {auth.device_model}")
            await asyncio.sleep(60)
        except Exception: await asyncio.sleep(120)

async def status_action_task(client: Client, user_id: int):
    chat_ids = []
    last_fetch = 0
    while user_id in ACTIVE_BOTS:
        try:
            typing = TYPING_MODE_STATUS.get(user_id, False)
            playing = PLAYING_MODE_STATUS.get(user_id, False)
            if not typing and not playing:
                await asyncio.sleep(2)
                continue
            action = ChatAction.TYPING if typing else ChatAction.PLAYING
            now = time.time()
            if not chat_ids or (now - last_fetch > 300):
                new_chats = []
                async for dialog in client.get_dialogs(limit=30):
                    if dialog.chat.type in [ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP]:
                        new_chats.append(dialog.chat.id)
                chat_ids = new_chats
                last_fetch = now
            for chat_id in chat_ids:
                try: await client.send_chat_action(chat_id, action)
                except: pass
            await asyncio.sleep(4)
        except Exception: await asyncio.sleep(60)

async def outgoing_message_modifier(client, message):
    user_id = client.me.id
    if not message.text or re.match(COMMAND_REGEX, message.text.strip(), re.IGNORECASE): return
    original_text = message.text
    modified_text = original_text
    target_lang = AUTO_TRANSLATE_TARGET.get(user_id)
    if target_lang: modified_text = await translate_text(modified_text, target_lang)
    if BOLD_MODE_STATUS.get(user_id, False):
        if not modified_text.startswith(('`', '**', '__', '~~', '||')): modified_text = f"**{modified_text}**"
    if modified_text != original_text:
        try: await message.edit_text(modified_text)
        except: pass

async def enemy_handler(client, message):
    user_id = client.me.id
    if not ENEMY_REPLIES: return 
    if user_id not in ENEMY_REPLY_QUEUES or not ENEMY_REPLY_QUEUES[user_id]:
        ENEMY_REPLY_QUEUES[user_id] = random.sample(ENEMY_REPLIES, len(ENEMY_REPLIES))
    reply_text = ENEMY_REPLY_QUEUES[user_id].pop(0)
    try: await message.reply_text(reply_text)
    except: pass

async def secretary_auto_reply_handler(client, message):
    owner_id = client.me.id
    if message.from_user and SECRETARY_MODE_STATUS.get(owner_id, False):
        target_id = message.from_user.id
        replied = USERS_REPLIED_IN_SECRETARY.get(owner_id, set())
        if target_id not in replied:
            try:
                await message.reply_text(SECRETARY_REPLY_MESSAGE)
                replied.add(target_id)
                USERS_REPLIED_IN_SECRETARY[owner_id] = replied
            except: pass

async def incoming_message_manager(client, message):
    if not message.from_user: return
    user_id = client.me.id
    if emoji := AUTO_REACTION_TARGETS.get(user_id, {}).get(message.from_user.id):
        try: await client.send_reaction(message.chat.id, message.id, emoji)
        except: pass
    if (message.from_user.id, message.chat.id) in MUTED_USERS.get(user_id, set()):
        try: await message.delete()
        except: pass

async def help_controller(client, message):
    try: await message.edit_text(HELP_TEXT)
    except: await message.reply_text(HELP_TEXT)

def get_self_panel_keyboard_ptb(user_id):
    s_clock = "✅" if CLOCK_STATUS.get(user_id, True) else "❌"
    s_bold = "✅" if BOLD_MODE_STATUS.get(user_id, False) else "❌"
    s_sec = "✅" if SECRETARY_MODE_STATUS.get(user_id, False) else "❌"
    s_seen = "✅" if AUTO_SEEN_STATUS.get(user_id, False) else "❌"
    s_pv = "🔒" if PV_LOCK_STATUS.get(user_id, False) else "🔓"
    s_anti = "✅" if ANTI_LOGIN_STATUS.get(user_id, False) else "❌"
    s_type = "✅" if TYPING_MODE_STATUS.get(user_id, False) else "❌"
    s_game = "✅" if PLAYING_MODE_STATUS.get(user_id, False) else "❌"
    s_enemy = "✅" if GLOBAL_ENEMY_STATUS.get(user_id, False) else "❌"
    t_lang = AUTO_TRANSLATE_TARGET.get(user_id)
    l_en = "✅" if t_lang == "en" else "❌"
    l_ru = "✅" if t_lang == "ru" else "❌"
    l_cn = "✅" if t_lang == "zh-CN" else "❌"
    
    current_font = USER_FONT_CHOICES.get(user_id, 'stylized')
    preview = stylize_time("12:34", current_font)

    keyboard = [
        [InlineKeyboardButton(f"ساعت {s_clock}", callback_data=f"toggle_clock_{user_id}"),
         InlineKeyboardButton(f"بولد {s_bold}", callback_data=f"toggle_bold_{user_id}")],
        [InlineKeyboardButton(f"تغییر فونت: {preview}", callback_data=f"cycle_font_{user_id}")],
        [InlineKeyboardButton(f"منشی {s_sec}", callback_data=f"toggle_sec_{user_id}"),
         InlineKeyboardButton(f"سین {s_seen}", callback_data=f"toggle_seen_{user_id}")],
        [InlineKeyboardButton(f"پیوی {s_pv}", callback_data=f"toggle_pv_{user_id}"),
         InlineKeyboardButton(f"انتی لوگین {s_anti}", callback_data=f"toggle_anti_{user_id}")],
        [InlineKeyboardButton(f"تایپ {s_type}", callback_data=f"toggle_type_{user_id}"),
         InlineKeyboardButton(f"دشمن همگانی {s_enemy}", callback_data=f"toggle_g_enemy_{user_id}")],
        [InlineKeyboardButton(f"بازی {s_game}", callback_data=f"toggle_game_{user_id}")],
        [InlineKeyboardButton(f"🇺🇸 EN {l_en}", callback_data=f"lang_en_{user_id}"),
         InlineKeyboardButton(f"🇷🇺 RU {l_ru}", callback_data=f"lang_ru_{user_id}"),
         InlineKeyboardButton(f"🇨🇳 CN {l_cn}", callback_data=f"lang_cn_{user_id}")],
        [InlineKeyboardButton("بستن پنل ❌", callback_data=f"close_panel_{user_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def panel_command_controller(client, message):
    try:
        user_id = client.me.id
        if not BOT_USERNAME:
            await message.edit_text("❌ خطا: نام کاربری ربات اصلی یافت نشد.")
            return
            
        results = await client.get_inline_bot_results(BOT_USERNAME, "panel")
        if results and results.results:
            await message.delete()
            await client.send_inline_bot_result(message.chat.id, results.query_id, results.results[0].id)
        else:
            await message.edit_text("❌ خطا در دریافت پنل از ربات اصلی. مطمئن شوید Inline Mode در BotFather روشن است.")
            
    except ChatSendInlineForbidden:
        await message.edit_text("🚫 در این چت اجازه ارسال پنل بصورت اینلاین وجود ندارد.")
    except Exception as e:
        await message.edit_text(f"❌ خطا: {e}\nلطفا ابتدا دستور /start را در ربات اصلی بزنید.")

async def reply_based_controller(client, message):
    user_id = client.me.id
    cmd = message.text
    if cmd == "تاس": await client.send_dice(message.chat.id, "🎲")
    elif cmd == "بولینگ": await client.send_dice(message.chat.id, "🎳")
    elif cmd.startswith("تاس "): 
        try: await client.send_dice(message.chat.id, "🎲", reply_to_message_id=message.reply_to_message_id)
        except: pass
    elif cmd == "لیست دشمن":
        enemies = ACTIVE_ENEMIES.get(user_id, set())
        await message.edit_text(f"📜 تعداد دشمنان فعال: {len(enemies)}")
    elif message.reply_to_message:
        target_id = message.reply_to_message.from_user.id if message.reply_to_message.from_user else None
        if cmd.startswith("حذف "):
            try:
                count = int(cmd.split()[1])
                msg_ids = [m.id async for m in client.get_chat_history(message.chat.id, limit=count) if m.from_user and m.from_user.is_self]
                if msg_ids: await client.delete_messages(message.chat.id, msg_ids)
                await message.delete()
            except: pass
        elif cmd == "ذخیره":
            await message.reply_to_message.forward("me")
            await message.edit_text("💾 ذخیره شد.")
        elif cmd.startswith("تکرار "):
            try:
                count = int(cmd.split()[1])
                for _ in range(count): await message.reply_to_message.copy(message.chat.id)
                await message.delete()
            except: pass
        elif target_id:
            if cmd == "کپی روشن":
                user = await client.get_chat(target_id)
                me = await client.get_me()
                ORIGINAL_PROFILE_DATA[user_id] = {'first_name': me.first_name, 'bio': me.bio}
                COPY_MODE_STATUS[user_id] = True
                CLOCK_STATUS[user_id] = False
                save_self_settings_to_db(user_id)
                target_photos = [p async for p in client.get_chat_photos(target_id, limit=1)]
                await client.update_profile(first_name=user.first_name, bio=(user.bio or "")[:70])
                if target_photos: await client.set_profile_photo(photo=target_photos[0].file_id)
                await message.edit_text("👤 هویت جعل شد.")
            elif cmd == "کپی خاموش":
                if user_id in ORIGINAL_PROFILE_DATA:
                    data = ORIGINAL_PROFILE_DATA[user_id]
                    COPY_MODE_STATUS[user_id] = False
                    save_self_settings_to_db(user_id)
                    await client.update_profile(first_name=data.get('first_name'), bio=data.get('bio'))
                    await message.edit_text("👤 هویت بازگردانده شد.")
            elif cmd == "دشمن روشن":
                s = ACTIVE_ENEMIES.get(user_id, set()); s.add((target_id, message.chat.id)); ACTIVE_ENEMIES[user_id] = s
                save_self_settings_to_db(user_id)
                await message.edit_text("⚔️ دشمن اضافه شد.")
            elif cmd == "دشمن خاموش":
                s = ACTIVE_ENEMIES.get(user_id, set()); s.discard((target_id, message.chat.id)); ACTIVE_ENEMIES[user_id] = s
                save_self_settings_to_db(user_id)
                await message.edit_text("🏳️ دشمن حذف شد.")
            elif cmd == "بلاک روشن": await client.block_user(target_id); await message.edit_text("🚫 کاربر بلاک شد.")
            elif cmd == "بلاک خاموش": await client.unblock_user(target_id); await message.edit_text("⭕️ کاربر آنبلاک شد.")
            elif cmd == "سکوت روشن":
                s = MUTED_USERS.get(user_id, set()); s.add((target_id, message.chat.id)); MUTED_USERS[user_id] = s
                save_self_settings_to_db(user_id)
                await message.edit_text("🔇 کاربر ساکت شد.")
            elif cmd == "سکوت خاموش":
                s = MUTED_USERS.get(user_id, set()); s.discard((target_id, message.chat.id)); MUTED_USERS[user_id] = s
                save_self_settings_to_db(user_id)
                await message.edit_text("🔊 کاربر از سکوت خارج شد.")
            elif cmd.startswith("ریاکشن ") and cmd != "ریاکشن خاموش":
                emoji = cmd.split()[1]
                t = AUTO_REACTION_TARGETS.get(user_id, {}); t[target_id] = emoji; AUTO_REACTION_TARGETS[user_id] = t
                save_self_settings_to_db(user_id)
                await message.edit_text(f"👍 واکنش {emoji} تنظیم شد.")
            elif cmd == "ریاکشن خاموش":
                t = AUTO_REACTION_TARGETS.get(user_id, {}); t.pop(target_id, None); AUTO_REACTION_TARGETS[user_id] = t
                save_self_settings_to_db(user_id)
                await message.edit_text("❌ واکنش حذف شد.")

async def start_bot_instance(session_string: str, phone: str, font_style: str, disable_clock: bool = False):
    client = Client(f"bot_{phone}", api_id=API_ID, api_hash=API_HASH, session_string=session_string)
    try:
        await client.start()
        user_id = (await client.get_me()).id
        # Update user_id in sessions table
        conn = get_db_connection()
        conn.execute('UPDATE sessions SET user_id = ? WHERE phone = ?', (user_id, phone))
        conn.commit()
        
        # Load settings
        cursor = conn.execute('SELECT settings FROM sessions WHERE phone = ?', (phone,))
        row = cursor.fetchone()
        if row:
            load_self_settings_from_db(user_id, row)
        conn.close()

    except Exception as e:
        logging.error(f"Failed to start Pyrogram client for phone {phone}: {e}")
        return

    if user_id in ACTIVE_BOTS:
        for t in ACTIVE_BOTS[user_id][1]: t.cancel()
    
    if user_id not in USER_FONT_CHOICES:
        USER_FONT_CHOICES[user_id] = font_style
    if user_id not in CLOCK_STATUS:
        CLOCK_STATUS[user_id] = not disable_clock
    
    client.add_handler(PyroMessageHandler(lambda c, m: m.delete() if PV_LOCK_STATUS.get(c.me.id) else None, pyro_filters.private & ~pyro_filters.me & ~pyro_filters.bot), group=-5)
    client.add_handler(PyroMessageHandler(lambda c, m: c.read_chat_history(m.chat.id) if AUTO_SEEN_STATUS.get(c.me.id) else None, pyro_filters.private & ~pyro_filters.me), group=-4)
    client.add_handler(PyroMessageHandler(incoming_message_manager, pyro_filters.all & ~pyro_filters.me), group=-3)
    client.add_handler(PyroMessageHandler(outgoing_message_modifier, pyro_filters.text & pyro_filters.me & ~pyro_filters.reply), group=-1)
    client.add_handler(PyroMessageHandler(help_controller, pyro_filters.me & pyro_filters.regex("^راهنما$")))
    client.add_handler(PyroMessageHandler(panel_command_controller, pyro_filters.me & pyro_filters.regex(r"^(پنل|panel)$")))
    client.add_handler(PyroMessageHandler(reply_based_controller, pyro_filters.me)) 
    client.add_handler(PyroMessageHandler(enemy_handler, pyro_filters.create(lambda _, c, m: (m.from_user.id, m.chat.id) in ACTIVE_ENEMIES.get(c.me.id, set()) or GLOBAL_ENEMY_STATUS.get(c.me.id)) & ~pyro_filters.me), group=1)
    client.add_handler(PyroMessageHandler(secretary_auto_reply_handler, pyro_filters.private & ~pyro_filters.me), group=1)

    tasks = [
        asyncio.create_task(update_profile_clock(client, user_id)),
        asyncio.create_task(anti_login_task(client, user_id)),
        asyncio.create_task(status_action_task(client, user_id))
    ]
    ACTIVE_BOTS[user_id] = (client, tasks)
    logging.info(f"Self Bot started for {user_id}")

async def stop_self_bot_due_to_balance(user_id):
    if user_id in ACTIVE_BOTS:
        client, tasks = ACTIVE_BOTS[user_id]
        try:
            me = await client.get_me()
            clean_name = re.sub(r'(?:\s*' + CLOCK_CHARS_REGEX_CLASS + r'+)+$', '', me.first_name).strip()
            if clean_name != me.first_name:
                await client.update_profile(first_name=clean_name)
        except: pass
        try: await client.stop()
        except: pass
        for t in tasks: t.cancel()
        del ACTIVE_BOTS[user_id]
    
    if user_id in GLOBAL_USERS:
        GLOBAL_USERS[user_id]['self_active'] = False
        save_user_immediate(user_id)

async def self_bot_activation_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_doc = await get_user_async(user.id)
    min_bal = int(await get_setting_async('self_bot_min_balance') or 10)
    hourly_cost = int(await get_setting_async('self_bot_hourly_cost') or 1)
    if user_doc['balance'] < min_bal:
        await update.message.reply_text(f"⛔️ موجودی شما کمتر از حد مجاز است.\nحداقل موجودی برای فعال‌سازی سلف: {min_bal} الماس", reply_markup=get_main_keyboard(user_doc))
        return ConversationHandler.END
    if user_doc.get('self_active') and user.id in ACTIVE_BOTS:
        await update.message.reply_text("✅ سلف شما هم‌اکنون فعال است.", reply_markup=get_main_keyboard(user_doc))
        return ConversationHandler.END
    kb = ReplyKeyboardMarkup([[KeyboardButton("📱 ارسال شماره تلفن", request_contact=True)], [KeyboardButton("بازگشت")]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(f"🤖 **فعال‌سازی سلف بات**\n\n💎 هزینه ساعتی: {hourly_cost} الماس\n⚠️ اگر موجودی شما تمام شود، سلف به طور خودکار خاموش می‌شود.\n\nلطفا برای شروع شماره خود را ارسال کنید:", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    return AWAIT_SELF_CONTACT

async def process_self_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if update.message.text == "بازگشت":
        await cancel_conversation(update, context)
        return ConversationHandler.END
    if not update.message.contact:
        await update.message.reply_text("لطفا از دکمه ارسال شماره استفاده کنید.")
        return AWAIT_SELF_CONTACT
    phone = update.message.contact.phone_number
    await update.message.reply_text("⏳ در حال اتصال به سرور تلگرام...", reply_markup=ReplyKeyboardRemove())
    temp_client = Client(f"login_temp_{user.id}", api_id=API_ID, api_hash=API_HASH, in_memory=True, no_updates=True)
    await temp_client.connect()
    try:
        sent_code = await temp_client.send_code(phone)
        context.user_data['login_client'] = temp_client
        context.user_data['login_phone'] = phone
        context.user_data['login_hash'] = sent_code.phone_code_hash
        await update.message.reply_text("✅ کد تایید ارسال شد.\nلطفا کد را به صورت اعداد جدا شده با فاصله یا نقطه ارسال کنید (مثلا: 1 2 3 4 5 یا 1.2.3.4.5) تا توسط تلگرام لینک شناسایی نشود.")
        return AWAIT_SELF_CODE
    except Exception as e:
        await temp_client.disconnect()
        await update.message.reply_text(f"❌ خطا در ارسال کد: {e}\nلطفا دوباره تلاش کنید.", reply_markup=get_main_keyboard(await get_user_async(user.id)))
        return ConversationHandler.END

async def process_self_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = re.sub(r"\D+", "", update.message.text)
    temp_client: Client = context.user_data.get('login_client')
    phone = context.user_data.get('login_phone')
    phone_hash = context.user_data.get('login_hash')
    try:
        await temp_client.sign_in(phone, phone_hash, code)
        await finalize_login(update, context, temp_client, phone)
        return ConversationHandler.END
    except SessionPasswordNeeded:
        await update.message.reply_text("🔐 اکانت شما رمز دو مرحله‌ای دارد. لطفا آن را وارد کنید:")
        return AWAIT_SELF_PASSWORD
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {e}\nلطفا مجدد تلاش کنید.")
        await temp_client.disconnect()
        return ConversationHandler.END

async def process_self_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text
    temp_client: Client = context.user_data.get('login_client')
    phone = context.user_data.get('login_phone')
    try:
        await temp_client.check_password(password)
        await finalize_login(update, context, temp_client, phone)
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ رمز اشتباه یا خطا: {e}\nدوباره تلاش کنید.")
        return AWAIT_SELF_PASSWORD

async def finalize_login(update: Update, context: ContextTypes.DEFAULT_TYPE, client: Client, phone: str):
    user_id = update.effective_user.id
    session_str = await client.export_session_string()
    me = await client.get_me()
    await client.disconnect()
    
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO sessions (phone, session_string, user_id, real_owner_id, settings) VALUES (?, ?, ?, ?, ?)',
                 (phone, session_str, me.id, user_id, json.dumps({})))
    conn.commit()
    conn.close()
    
    user_doc = await get_user_async(user_id)
    user_doc['self_active'] = True
    user_doc['self_last_payment'] = time.time()
    
    cost = int(await get_setting_async('self_bot_hourly_cost') or 1)
    if user_doc['balance'] >= cost:
        user_doc['balance'] -= cost
        save_user_immediate(user_id)
        msg = f"✅ سلف بات با موفقیت فعال شد!\n💎 {cost} الماس برای ساعت اول کسر شد."
    else:
        msg = "✅ سلف فعال شد اما موجودی برای کسر هزینه کافی نبود. به زودی غیرفعال می‌شود."
    
    asyncio.create_task(start_bot_instance(session_str, phone, 'stylized'))
    await update.message.reply_text(msg, reply_markup=get_main_keyboard(user_doc))

async def billing_job(context: ContextTypes.DEFAULT_TYPE):
    cost_str = await get_setting_async('self_bot_hourly_cost')
    try: cost = int(cost_str or 1)
    except: cost = 1
    now = time.time()
    for user_id, user_data in list(GLOBAL_USERS.items()):
        if not user_data.get('self_active'): continue
        last_pay = user_data.get('self_last_payment', 0)
        if now - last_pay >= 3600:
            if user_data['balance'] >= cost:
                user_data['balance'] -= cost
                user_data['self_last_payment'] = now
                save_user_immediate(user_id)
            else:
                await stop_self_bot_due_to_balance(user_id)
                try:
                    kb = ReplyKeyboardMarkup([[KeyboardButton("🔄 تمدید و ادامه سرویس")], [KeyboardButton("💰 موجودی")]], resize_keyboard=True)
                    await context.bot.send_message(chat_id=user_id, text="⚠️ **هشدار: موجودی الماس شما به پایان رسید!**\n\nسلف بات شما خاموش شد و تنظیمات (مثل ساعت پروفایل) حذف گردید.\nلطفا حساب خود را شارژ کنید و سپس دکمه تمدید را بزنید.", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
                except Exception as e: logging.warning(f"Failed to send billing alert to {user_id}: {e}")

async def continue_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_doc = await get_user_async(user_id)
    min_bal = int(await get_setting_async('self_bot_min_balance') or 10)
    if user_doc['balance'] < min_bal:
        await update.message.reply_text(f"❌ موجودی کافی نیست. حداقل {min_bal} الماس لازم است.", reply_markup=get_main_keyboard(user_doc))
        return
    
    conn = get_db_connection()
    session_row = conn.execute('SELECT * FROM sessions WHERE real_owner_id = ?', (user_id,)).fetchone()
    conn.close()

    if not session_row:
        await update.message.reply_text("❌ سشن شما یافت نشد. لطفا مجدد فعال‌سازی را انجام دهید.", reply_markup=get_main_keyboard(user_doc))
        return
    user_doc['self_active'] = True
    user_doc['self_last_payment'] = time.time()
    cost = int(await get_setting_async('self_bot_hourly_cost') or 1)
    user_doc['balance'] -= cost
    save_user_immediate(user_id)
    asyncio.create_task(start_bot_instance(session_row['session_string'], session_row['phone'], 'stylized'))
    await update.message.reply_text(f"✅ سرویس مجددا فعال شد.\n💎 {cost} الماس کسر گردید.", reply_markup=get_main_keyboard(user_doc))

async def admin_panel_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_user_async(update.effective_user.id)
    if not user_doc.get('is_owner'):
        await update.message.reply_text("⛔️ دسترسی به تنظیمات پنل فقط برای مالک اصلی مجاز است.")
        return ConversationHandler.END
    await update.message.reply_text("👑 به پنل ادمین خوش آمدید:", reply_markup=admin_keyboard)
    return ADMIN_MENU

async def process_admin_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    context.user_data['admin_choice'] = choice
    prompts = {
        "⚙️ هزینه سلف (ساعتی)": "هزینه هر ساعت استفاده از سلف (به الماس) را وارد کنید:",
        "💎 حداقل موجودی سلف": "حداقل موجودی لازم برای روشن کردن سلف را وارد کنید:",
        "🖼 تنظیم عکس پنل سلف": "لطفا عکس جدید برای پنل سلف را ارسال کنید:",
        "💳 تنظیم شماره کارت": "لطفا شماره کارت جدید را وارد کنید:",
        "👤 تنظیم صاحب کارت": "لطفا نام صاحب حساب جدید را وارد کنید:",
        "💰 تنظیم الماس (ست)": "ابتدا آیدی عددی کاربر را وارد کنید:",
        "➕ افزایش الماس کاربر": "ابتدا آیدی عددی کاربر را برای افزایش الماس وارد کنید:",
        "➖ کسر الماس کاربر": "ابتدا آیدی عددی کاربر را برای کسر الماس وارد کنید:",
        "📉 تنظیم مالیات (۰-۱۰۰)": "درصد مالیات (بین ۰ تا ۱۰۰) را وارد کنید:",
        "📈 تنظیم قیمت الماس": "قیمت جدید هر الماس به تومان را وارد کنید:",
        "🎁 تنظیم پاداش دعوت": "پاداش هر دعوت موفق به الماس را وارد کنید:",
        "➕ افزودن کانال عضویت": "یوزرنیم کانال/گروه با @ (مثل @channel) یا لینک کامل را ارسال کنید:",
        "🖼 تنظیم عکس شرط": "لطفا عکس مورد نظر برای شرط را ارسال کنید.",
        "📢 پیام همگانی": "لطفا پیام خود را ارسال کنید (متن، عکس، فایل و...).",
        "مدیریت کاربر": "آیدی عددی کاربر مورد نظر را وارد کنید:"
    }
    
    if choice in prompts:
        await update.message.reply_text(prompts[choice], reply_markup=ReplyKeyboardRemove())
        if choice == "⚙️ هزینه سلف (ساعتی)": return AWAIT_ADMIN_SELF_COST
        if choice == "💎 حداقل موجودی سلف": return AWAIT_ADMIN_SELF_MIN
        if choice == "🖼 تنظیم عکس پنل سلف": return AWAIT_ADMIN_SELF_PHOTO
        if choice == "💳 تنظیم شماره کارت": return AWAIT_ADMIN_SET_CARD_NUMBER
        if choice == "👤 تنظیم صاحب کارت": return AWAIT_ADMIN_SET_CARD_HOLDER
        if choice == "💰 تنظیم الماس (ست)": return AWAIT_ADMIN_SET_BALANCE_ID
        if choice == "➕ افزایش الماس کاربر": return AWAIT_ADMIN_ADD_BALANCE_ID
        if choice == "➖ کسر الماس کاربر": return AWAIT_ADMIN_DEDUCT_BALANCE_ID
        if choice == "📉 تنظیم مالیات (۰-۱۰۰)": return AWAIT_ADMIN_TAX
        if choice == "📈 تنظیم قیمت الماس": return AWAIT_ADMIN_CREDIT_PRICE
        if choice == "🎁 تنظیم پاداش دعوت": return AWAIT_ADMIN_REFERRAL_PRICE
        if choice == "➕ افزودن کانال عضویت": return AWAIT_NEW_CHANNEL
        if choice == "🖼 تنظیم عکس شرط": return AWAIT_BET_PHOTO
        if choice == "📢 پیام همگانی": return AWAIT_BROADCAST_MESSAGE
        if choice == "مدیریت کاربر": return AWAIT_MANAGE_USER_ID

    # Actions without prompts
    if choice == "➖ حذف کانال عضویت": return await show_channels_for_removal(update, context)
    if choice == "🔒 قفل عضویت: روشن":
        await set_setting_async('forced_channel_lock', 'true')
        await update.message.reply_text("✅ قفل عضویت فعال شد.", reply_markup=admin_keyboard)
        return ADMIN_MENU
    if choice == "🔓 قفل عضویت: خاموش":
        await set_setting_async('forced_channel_lock', 'false')
        await update.message.reply_text("❌ قفل عضویت غیرفعال شد.", reply_markup=admin_keyboard)
        return ADMIN_MENU
    if choice == "👁‍🗨 لیست کانال‌های عضویت":
        channels = list(GLOBAL_CHANNELS.values())
        msg = "لیست کانال‌ها:\n" + "\n".join([f"{c['channel_title']} ({c['channel_username']})" for c in channels]) if channels else "خالی"
        await update.message.reply_text(msg, reply_markup=admin_keyboard)
        return ADMIN_MENU
    if choice == "📊 آمار کلی":
        total_users = len(GLOBAL_USERS)
        pending_tx = sum(1 for tx in GLOBAL_TRANSACTIONS.values() if tx['status'] == 'pending')
        await update.message.reply_text(f"👥 کاربران: {total_users}\n🧾 تراکنش‌های معلق: {pending_tx}", reply_markup=admin_keyboard)
        return ADMIN_MENU
    if choice == "🗑 حذف عکس شرط":
        await set_setting_async('bet_photo_file_id', 'None')
        await update.message.reply_text("✅ عکس حذف شد.", reply_markup=admin_keyboard)
        return ADMIN_MENU
    if choice == "🗑 حذف عکس پنل سلف":
        await set_setting_async('self_panel_photo', 'None')
        await update.message.reply_text("✅ عکس پنل سلف حذف شد.", reply_markup=admin_keyboard)
        return ADMIN_MENU
    if choice == "⬅️ بازگشت به منوی اصلی":
        user_doc = await get_user_async(update.effective_user.id)
        await update.message.reply_text("منوی اصلی:", reply_markup=get_main_keyboard(user_doc))
        return ConversationHandler.END
        
    return AWAIT_ADMIN_REPLY

async def process_admin_self_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = int(update.message.text)
        await set_setting_async('self_bot_hourly_cost', val)
        await update.message.reply_text(f"✅ هزینه ساعتی سلف به {val} الماس تغییر کرد.", reply_markup=admin_keyboard)
    except: await update.message.reply_text("❌ عدد نامعتبر.")
    return ADMIN_MENU

async def process_admin_self_min(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = int(update.message.text)
        await set_setting_async('self_bot_min_balance', val)
        await update.message.reply_text(f"✅ حداقل موجودی سلف به {val} الماس تغییر کرد.", reply_markup=admin_keyboard)
    except: await update.message.reply_text("❌ عدد نامعتبر.")
    return ADMIN_MENU

async def process_admin_self_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ لطفا یک عکس ارسال کنید.", reply_markup=admin_keyboard)
        return AWAIT_ADMIN_SELF_PHOTO
    file_id = update.message.photo[-1].file_id
    await set_setting_async('self_panel_photo', file_id)
    await update.message.reply_text("✅ عکس پنل سلف با موفقیت تنظیم شد.", reply_markup=admin_keyboard)
    return ADMIN_MENU

async def show_channels_for_removal(update, context):
    channels = list(GLOBAL_CHANNELS.values())
    if not channels:
        await update.message.reply_text("هیچ کانالی وجود ندارد.", reply_markup=admin_keyboard); return ADMIN_MENU
    kb = [[InlineKeyboardButton(c['channel_username'], callback_data=f"admin_remove_{c['channel_username']}")] for c in channels]
    kb.append([InlineKeyboardButton("لغو", callback_data="admin_remove_cancel")])
    await update.message.reply_text("انتخاب کنید:", reply_markup=InlineKeyboardMarkup(kb))
    return ADMIN_MENU

async def process_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ انجام شد.", reply_markup=admin_keyboard)
    return ADMIN_MENU

async def process_admin_set_balance_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text)
        context.user_data['target_user_id_balance'] = uid
        await get_user_async(uid)
        await update.message.reply_text(f"مقدار جدید برای {uid}:")
        return AWAIT_ADMIN_SET_BALANCE
    except: await update.message.reply_text("نامعتبر."); return ADMIN_MENU

async def process_admin_set_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = int(update.message.text)
        uid = context.user_data.pop('target_user_id_balance')
        u = await get_user_async(uid)
        u['balance'] = val
        save_user_immediate(uid)
        await update.message.reply_text("✅ انجام شد.", reply_markup=admin_keyboard)
    except: pass
    return ADMIN_MENU

async def process_admin_set_card_number(update, context): await set_setting_async('card_number', update.message.text); await update.message.reply_text("✅", reply_markup=admin_keyboard); return ADMIN_MENU
async def process_admin_set_card_holder(update, context): await set_setting_async('card_holder', update.message.text); await update.message.reply_text("✅", reply_markup=admin_keyboard); return ADMIN_MENU
async def process_new_channel(update, context): 
    ch = update.message.text
    GLOBAL_CHANNELS[ch] = {'channel_username': ch, 'channel_title': ch}
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO channels (username, data) VALUES (?, ?)', (ch, json.dumps(GLOBAL_CHANNELS[ch])))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅", reply_markup=admin_keyboard)
    return ADMIN_MENU
async def process_bet_photo(update, context):
    if update.message.photo: await set_setting_async('bet_photo_file_id', update.message.photo[-1].file_id)
    await update.message.reply_text("✅", reply_markup=admin_keyboard); return ADMIN_MENU
async def process_admin_add_balance_id(update, context): context.user_data['tid_add'] = int(update.message.text); await update.message.reply_text("مقدار افزودن:"); return AWAIT_ADMIN_ADD_BALANCE_AMOUNT
async def process_admin_add_balance_amount(update, context):
    uid = context.user_data.pop('tid_add'); amt = int(update.message.text)
    u = await get_user_async(uid); u['balance'] += amt; save_user_immediate(uid)
    await update.message.reply_text("✅", reply_markup=admin_keyboard); return ADMIN_MENU
async def process_admin_deduct_balance_id(update, context): context.user_data['tid_ded'] = int(update.message.text); await update.message.reply_text("مقدار کسر:"); return AWAIT_ADMIN_DEDUCT_BALANCE_AMOUNT
async def process_admin_deduct_balance_amount(update, context):
    uid = context.user_data.pop('tid_ded'); amt = int(update.message.text)
    u = await get_user_async(uid); u['balance'] -= amt; save_user_immediate(uid)
    await update.message.reply_text("✅", reply_markup=admin_keyboard); return ADMIN_MENU
async def process_admin_tax(update, context): await set_setting_async('bet_tax_rate', update.message.text); await update.message.reply_text("✅", reply_markup=admin_keyboard); return ADMIN_MENU
async def process_admin_credit_price(update, context): await set_setting_async('credit_price', update.message.text); await update.message.reply_text("✅", reply_markup=admin_keyboard); return ADMIN_MENU
async def process_admin_referral_price(update, context): await set_setting_async('referral_reward', update.message.text); await update.message.reply_text("✅", reply_markup=admin_keyboard); return ADMIN_MENU
async def process_manage_user_id(update, context): context.user_data['tid_man'] = int(update.message.text); await update.message.reply_text("نقش (ادمین/مادریتور/کاربر عادی):"); return AWAIT_MANAGE_USER_ROLE
async def process_manage_user_role(update, context): 
    uid = context.user_data.pop('tid_man'); role = update.message.text
    u = await get_user_async(uid)
    if role == "ادمین": u['is_admin']=True; u['is_moderator']=False
    elif role == "مادریتور": u['is_admin']=False; u['is_moderator']=True
    else: u['is_admin']=False; u['is_moderator']=False
    save_user_immediate(uid)
    await update.message.reply_text("✅", reply_markup=admin_keyboard); return ADMIN_MENU
async def process_admin_broadcast(update, context):
    await update.message.reply_text("پیام ارسال شد.", reply_markup=admin_keyboard); return ADMIN_MENU

# --- Deposit Functions ---
async def deposit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا تعداد الماسی که قصد خرید دارید را وارد کنید:", reply_markup=ReplyKeyboardRemove())
    return AWAIT_DEPOSIT_AMOUNT

async def process_deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount <= 0: raise ValueError
        price_str = await get_setting_async('credit_price')
        try: price = int(price_str or 1000)
        except: price = 1000
        total_cost = amount * price
        context.user_data['deposit_amount'] = amount
        card_number = await get_setting_async('card_number') or "تنظیم نشده"
        card_holder = await get_setting_async('card_holder') or "تنظیم نشده"
        await update.message.reply_text(f"هزینه قابل پرداخت برای `{amount}` الماس: `{total_cost:,}` تومان\n\nلطفا مبلغ را به کارت زیر واریز کرده و سپس عکس رسید را ارسال کنید:\nشماره کارت: `{card_number}`\nصاحب حساب: `{card_holder}`", parse_mode=ParseMode.MARKDOWN)
        return AWAIT_DEPOSIT_RECEIPT
    except (ValueError, TypeError):
        await update.message.reply_text("❌ لطفا یک عدد صحیح و مثبت وارد کنید.")
        return AWAIT_DEPOSIT_AMOUNT

async def process_deposit_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TX_ID_COUNTER
    if not update.message.photo:
        await update.message.reply_text("❌ لطفا عکس رسید پرداخت را ارسال کنید.")
        return AWAIT_DEPOSIT_RECEIPT
    user = update.effective_user
    amount = context.user_data['deposit_amount']
    receipt_file_id = update.message.photo[-1].file_id
    tx_id = TX_ID_COUNTER
    GLOBAL_TRANSACTIONS[tx_id] = {
        'tx_id': tx_id,
        'user_id': user.id,
        'amount': amount,
        'receipt_file_id': receipt_file_id,
        'status': 'pending',
        'type': 'diamond',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'admin_messages': []
    }
    TX_ID_COUNTER += 1
    
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO transactions (tx_id, data) VALUES (?, ?)', (tx_id, json.dumps(GLOBAL_TRANSACTIONS[tx_id])))
    conn.commit()
    conn.close()

    caption = (f"🧾 درخواست افزایش الماس جدید (ID: {tx_id})\nکاربر: {user.mention_html()} (ID: {user.id})\nتعداد الماس: `{amount}`")
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("✅ تایید", callback_data=f"tx_approve_{tx_id}"), InlineKeyboardButton("❌ رد", callback_data=f"tx_reject_{tx_id}")]])
    try:
        msg = await context.bot.send_photo(chat_id=OWNER_ID, photo=receipt_file_id, caption=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        GLOBAL_TRANSACTIONS[tx_id]['admin_messages'].append({'chat_id': OWNER_ID, 'message_id': msg.message_id})
    except Exception as e: logging.warning(f"Could not send receipt to owner: {e}")
    user_doc = await get_user_async(user.id)
    await update.message.reply_text("✅ رسید شما برای ادمین ارسال شد. پس از تایید، الماس شما شارژ خواهد شد.", reply_markup=get_main_keyboard(user_doc))
    context.user_data.clear()
    return ConversationHandler.END

# --- Support Functions ---
async def support_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا پیام خود را برای ارسال به پشتیبانی بنویسید:", reply_markup=ReplyKeyboardRemove())
    return AWAIT_SUPPORT_MESSAGE

async def process_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_doc = await get_user_async(user.id)
    text = f"📨 پیام پشتیبانی جدید از کاربر: {user.mention_html()}\n(ID: `{user.id}`)\n\n`{update.message.text}`"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("✍️ پاسخ به کاربر", callback_data=f"reply_support_{user.id}_{update.message.message_id}")]])
    try: await context.bot.send_message(chat_id=OWNER_ID, text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e: logging.warning(f"Could not send support message to owner: {e}")
    await update.message.reply_text("✅ پیام شما با موفقیت برای تیم پشتیبانی ارسال شد.", reply_markup=get_main_keyboard(user_doc))
    return ConversationHandler.END

# --- Admin Reply Functions ---
async def admin_support_reply_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    target_user_id = int(data[2])
    context.user_data['reply_to_user'] = target_user_id
    await query.message.reply_text(f"لطفا پاسخ خود را برای کاربر با آیدی {target_user_id} بنویسید:", reply_markup=ReplyKeyboardRemove())
    return AWAIT_ADMIN_SUPPORT_REPLY

async def process_admin_support_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user_id = context.user_data.get('reply_to_user')
    if not target_user_id: return ConversationHandler.END
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"✉️ پاسخ پشتیبانی:\n\n{update.message.text}")
        await update.message.reply_text("✅ پاسخ شما برای کاربر ارسال شد.", reply_markup=admin_keyboard)
    except Exception as e: await update.message.reply_text(f"❌ ارسال پیام به کاربر ناموفق بود: {e}", reply_markup=admin_keyboard)
    context.user_data.clear()
    return ConversationHandler.END

# --- Callback & Inline Handlers ---
async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if query == "panel":
        user_id = update.effective_user.id
        photo_id = get_panel_photo(user_id)
        markup = get_self_panel_keyboard_ptb(user_id)
        caption = f"⚡️ **مدیریت پیشرفته سلف بات**\n👤 کاربر: `{user_id}`\n\nوضعیت اتصال: ✅ برقرار"
        if photo_id:
            results = [InlineQueryResultCachedPhoto(id=str(secrets.randbelow(99999)), photo_file_id=photo_id, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)]
        else:
            results = [InlineQueryResultArticle(id=str(secrets.randbelow(99999)), title="پنل تنظیمات سلف", input_message_content=InputTextMessageContent(caption, parse_mode=ParseMode.MARKDOWN), reply_markup=markup, thumbnail_url="https://telegra.ph/file/1e3b567786f7800e80816.jpg")]
        await update.inline_query.answer(results, cache_time=0)

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data.startswith("toggle_") or data.startswith("cycle_") or data.startswith("lang_") or data.startswith("close_"):
        if str(user_id) not in data:
             await query.answer("⛔️ این پنل متعلق به شما نیست!", show_alert=True)
             return

        if data.startswith("toggle_clock"):
            CLOCK_STATUS[user_id] = not CLOCK_STATUS.get(user_id, True)
            save_self_settings_to_db(user_id)
            if user_id in ACTIVE_BOTS and CLOCK_STATUS[user_id]:
                 asyncio.create_task(perform_clock_update_now(ACTIVE_BOTS[user_id][0], user_id))
        
        elif data.startswith("cycle_font"):
            cur = USER_FONT_CHOICES.get(user_id, 'stylized')
            idx = (FONT_KEYS_ORDER.index(cur) + 1) % len(FONT_KEYS_ORDER)
            USER_FONT_CHOICES[user_id] = FONT_KEYS_ORDER[idx]
            CLOCK_STATUS[user_id] = True
            save_self_settings_to_db(user_id)
            if user_id in ACTIVE_BOTS:
                 asyncio.create_task(perform_clock_update_now(ACTIVE_BOTS[user_id][0], user_id))

        elif data.startswith("toggle_bold"): BOLD_MODE_STATUS[user_id] = not BOLD_MODE_STATUS.get(user_id, False); save_self_settings_to_db(user_id)
        elif data.startswith("toggle_sec"): SECRETARY_MODE_STATUS[user_id] = not SECRETARY_MODE_STATUS.get(user_id, False); save_self_settings_to_db(user_id)
        elif data.startswith("toggle_seen"): AUTO_SEEN_STATUS[user_id] = not AUTO_SEEN_STATUS.get(user_id, False); save_self_settings_to_db(user_id)
        elif data.startswith("toggle_pv"): PV_LOCK_STATUS[user_id] = not PV_LOCK_STATUS.get(user_id, False); save_self_settings_to_db(user_id)
        elif data.startswith("toggle_anti"): ANTI_LOGIN_STATUS[user_id] = not ANTI_LOGIN_STATUS.get(user_id, False); save_self_settings_to_db(user_id)
        elif data.startswith("toggle_type"):
            TYPING_MODE_STATUS[user_id] = not TYPING_MODE_STATUS.get(user_id, False)
            if TYPING_MODE_STATUS[user_id]: PLAYING_MODE_STATUS[user_id] = False
            save_self_settings_to_db(user_id)
        elif data.startswith("toggle_game"):
            PLAYING_MODE_STATUS[user_id] = not PLAYING_MODE_STATUS.get(user_id, False)
            if PLAYING_MODE_STATUS[user_id]: TYPING_MODE_STATUS[user_id] = False
            save_self_settings_to_db(user_id)
        elif data.startswith("toggle_g_enemy"): GLOBAL_ENEMY_STATUS[user_id] = not GLOBAL_ENEMY_STATUS.get(user_id, False); save_self_settings_to_db(user_id)
        elif data.startswith("lang_"):
            l = data.split("_")[1]
            AUTO_TRANSLATE_TARGET[user_id] = l if AUTO_TRANSLATE_TARGET.get(user_id) != l else None
            save_self_settings_to_db(user_id)
        
        elif data.startswith("close_panel"):
            await query.message.delete()
            return

        try: await query.edit_message_reply_markup(reply_markup=get_self_panel_keyboard_ptb(user_id))
        except: pass
        return

    if data == "check_join_membership":
        await query.message.delete()
        return

    if data.startswith("admin_remove_"):
        ch = data.replace("admin_remove_", "")
        if ch in GLOBAL_CHANNELS: del GLOBAL_CHANNELS[ch]
        
        conn = get_db_connection()
        conn.execute('DELETE FROM channels WHERE username = ?', (ch,))
        conn.commit()
        conn.close()

        await query.edit_message_text(f"حذف شد: {ch}")
        return

    if data.startswith("bet_"):
        bet_id = int(data.split('_')[2])
        if 'join' in data: await query.edit_message_text("✅ شما به شرط پیوستید! (darkself)")
        elif 'cancel' in data: await query.edit_message_text("❌ شرط لغو شد.")
        return

    if data.startswith("tx_"):
        parts = data.split('_')
        action = parts[1]
        tx_id = int(parts[2])
        tx = GLOBAL_TRANSACTIONS.get(tx_id)
        if not tx: await query.answer("تراکنش یافت نشد.", show_alert=True); return
        if tx['status'] != 'pending': await query.answer("قبلا پردازش شده.", show_alert=True); return
        if action == "approve":
            tx['status'] = 'approved'
            u_doc = await get_user_async(tx['user_id'])
            u_doc['balance'] += tx['amount']
            save_user_immediate(tx['user_id'])
            
            conn = get_db_connection()
            conn.execute('INSERT OR REPLACE INTO transactions (tx_id, data) VALUES (?, ?)', (tx_id, json.dumps(tx)))
            conn.commit()
            conn.close()
            
            await context.bot.send_message(tx['user_id'], f"✅ شارژ {tx['amount']} الماس انجام شد.")
            await query.edit_message_caption(caption=query.message.caption + "\n\n✅ تایید شد.")
        elif action == "reject":
            tx['status'] = 'rejected'
            conn = get_db_connection()
            conn.execute('INSERT OR REPLACE INTO transactions (tx_id, data) VALUES (?, ?)', (tx_id, json.dumps(tx)))
            conn.commit()
            conn.close()
            
            await context.bot.send_message(tx['user_id'], f"❌ درخواست شارژ رد شد.")
            await query.edit_message_caption(caption=query.message.caption + "\n\n❌ رد شد.")
        return

async def start_bet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BET_ID_COUNTER
    if not update.message: return
    amount = 100
    try:
        match = re.search(r'(\d+)', update.message.text)
        if match: amount = int(match.group(1))
    except: pass
    text = (f"♦️ — شرط جدید (ID: {BET_ID_COUNTER}) — ♦️\n| 💰 | تعداد الماس : {amount:,}\n| 👤 | سازنده : {get_user_display_name(update.effective_user)}\n♦️ — خدمات مجازی darkself — ♦️")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ پیوستن", callback_data=f"bet_join_{BET_ID_COUNTER}"), InlineKeyboardButton("❌ لغو شرط", callback_data=f"bet_cancel_{BET_ID_COUNTER}")]])
    
    GLOBAL_BETS[BET_ID_COUNTER] = {'id': BET_ID_COUNTER, 'amount': amount, 'creator': update.effective_user.id}
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO bets (bet_id, data) VALUES (?, ?)', (BET_ID_COUNTER, json.dumps(GLOBAL_BETS[BET_ID_COUNTER])))
    conn.commit()
    conn.close()

    BET_ID_COUNTER += 1
    await update.message.reply_text(text, reply_markup=kb)

async def cancel_bet_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    bet_id = job.data['bet_id']
    chat_id = job.data['chat_id']
    message_id = job.data['message_id']
    if bet_id in GLOBAL_BETS and GLOBAL_BETS[bet_id].get('status') == 'pending':
        deleted_bet = GLOBAL_BETS.pop(bet_id)
        conn = get_db_connection()
        conn.execute('DELETE FROM bets WHERE bet_id = ?', (bet_id,))
        conn.commit()
        conn.close()
        try:
            await context.bot.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=f"⏰ شرط‌بندی روی تعداد {deleted_bet['amount']} الماس منقضی شد.", reply_markup=None)
        except:
             try: await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"⏰ شرط‌بندی روی تعداد {deleted_bet['amount']} الماس منقضی شد.", reply_markup=None)
             except: pass

async def membership_check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    query = update.callback_query
    if not user: return
    if chat and chat.type != 'private': return
    if user.id == OWNER_ID: return
    forced_lock_str = await get_setting_async("forced_channel_lock")
    if forced_lock_str != 'true': return
    channels = list(GLOBAL_CHANNELS.values())
    if not channels: return
    not_joined_channels = []
    for channel in channels:
        channel_username = channel['channel_username']
        try:
            member = await context.bot.get_chat_member(channel_username, user.id)
            if member.status not in ['member', 'administrator', 'creator']:
                not_joined_channels.append(channel)
        except Exception:
            not_joined_channels.append(channel)

    if query and query.data == "check_join_membership":
        if not not_joined_channels:
            await query.answer("✅ عضویت تایید شد!")
            await query.message.delete()
            user_doc = await get_user_async(user.id)
            await context.bot.send_message(chat_id=user.id, text="✅ عضویت شما تایید شد. خوش آمدید!", reply_markup=get_main_keyboard(user_doc))
        else:
            await query.answer("❌ شما هنوز در تمام کانال‌ها عضو نشدید!", show_alert=True)
        raise ApplicationHandlerStop

    if not_joined_channels:
        keyboard_buttons = []
        for channel in not_joined_channels:
            link = f"https://t.me/{channel['channel_username'].replace('@', '')}"
            keyboard_buttons.append([InlineKeyboardButton(f"عضویت در {channel['channel_username']}", url=link)])
        keyboard_buttons.append([InlineKeyboardButton("تایید عضویت", callback_data="check_join_membership")])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        text = "🔒 برای استفاده از ربات، لطفا در کانال‌های زیر عضو شوید:"
        if query:
            await query.answer("⛔️ ابتدا باید عضو کانال‌های شوید.", show_alert=True)
            try: await query.message.delete()
            except: pass
            await context.bot.send_message(chat_id=user.id, text=text, reply_markup=keyboard)
        elif update.effective_message:
            await update.effective_message.reply_text(text=text, reply_markup=keyboard)
        raise ApplicationHandlerStop

# =======================================================
#  بخش ۴: توابع اضافه شده
# =======================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_user_async(update.effective_user.id)
    await update.message.reply_text(
        f"سلام {get_user_display_name(update.effective_user)} عزیز!\nخوش اومدی.",
        reply_markup=get_main_keyboard(user_doc)
    )

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_user_async(update.effective_user.id)
    bal = user_doc['balance']
    await update.message.reply_text(f"💰 موجودی شما: {bal} الماس")

async def get_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_name = context.bot.username
    link = f"https://t.me/{bot_name}?start={user_id}"
    await update.message.reply_text(f"🎁 لینک دعوت شما:\n{link}\n\nبا دعوت هر نفر الماس رایگان بگیرید!")

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_user_async(update.effective_user.id)
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=get_main_keyboard(user_doc))
    return ConversationHandler.END

async def show_bet_keyboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("منوی شرط بندی:", reply_markup=bet_group_keyboard)

async def transfer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return
    try:
        sender_id = update.effective_user.id
        receiver_id = update.message.reply_to_message.from_user.id
        amount = int(context.match.group(2))
        
        if sender_id == receiver_id: return
        
        sender_doc = await get_user_async(sender_id)
        if sender_doc['balance'] < amount:
            await update.message.reply_text("موجودی کافی نیست!")
            return
            
        receiver_doc = await get_user_async(receiver_id)
        sender_doc['balance'] -= amount
        receiver_doc['balance'] += amount
        save_user_immediate(sender_id)
        save_user_immediate(receiver_id)
        
        await update.message.reply_text(f"✅ {amount} الماس با موفقیت انتقال یافت.")
    except: pass

async def group_balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_user_async(update.effective_user.id)
    await update.message.reply_text(f"👤 موجودی {update.effective_user.first_name}: {user_doc['balance']} الماس")

async def deduct_balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        target_id = update.message.reply_to_message.from_user.id
        amount = int(re.search(r'\d+', update.message.text).group())
        u = await get_user_async(target_id)
        u['balance'] -= amount
        save_user_immediate(target_id)
        await update.message.reply_text(f"✅ {amount} الماس از کاربر کسر شد.")
    except: pass

# =======================================================
#  بخش ۸: اجرای اصلی
# =======================================================

async def post_init(application: Application):
    global BOT_USERNAME
    init_db()
    try:
        me = await application.bot.get_me()
        BOT_USERNAME = me.username
        logging.info(f"Bot Username: {BOT_USERNAME}")
    except: pass
    
    conn = get_db_connection()
    cursor = conn.execute('SELECT * FROM sessions')
    count = 0
    for row in cursor:
         user_id = row['real_owner_id']
         if user_id:
            u = await get_user_async(user_id)
            if u.get('self_active'):
                asyncio.create_task(start_bot_instance(row['session_string'], row['phone'], 'stylized'))
                count += 1
    conn.close()
    logging.info(f"Restored {count} active self-bots.")
    
    if application.job_queue:
        application.job_queue.run_repeating(billing_job, interval=60, first=10)

def main():
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(connection_pool_size=8)
    application = (Application.builder().token(BOT_TOKEN).request(request).post_init(post_init).build())
    
    # Forced Join Middleware
    application.add_handler(TypeHandler(Update, membership_check_handler), group=-1)

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.Regex("^💰 موجودی$"), show_balance))
    application.add_handler(MessageHandler(filters.Regex("^🎁 الماس رایگان$"), get_referral_link))
    application.add_handler(MessageHandler(filters.Regex("^🔄 تمدید و ادامه سرویس$"), continue_service_handler))
    
    self_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🤖 فعال‌سازی سلف$"), self_bot_activation_entry)],
        states={
            AWAIT_SELF_CONTACT: [MessageHandler(filters.CONTACT, process_self_contact), MessageHandler(filters.Regex("^بازگشت$"), cancel_conversation)],
            AWAIT_SELF_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_self_code)],
            AWAIT_SELF_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_self_password)]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        allow_reentry=True
    )
    application.add_handler(self_conv)

    deposit_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💳 افزایش الماس$"), deposit_entry)],
        states={
            AWAIT_DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_deposit_amount)],
            AWAIT_DEPOSIT_RECEIPT: [MessageHandler(filters.PHOTO, process_deposit_receipt)]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        allow_reentry=True
    )
    application.add_handler(deposit_conv)

    support_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💬 پشتیبانی$"), support_entry)],
        states={
            AWAIT_SUPPORT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_support_message)]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        allow_reentry=True
    )
    application.add_handler(support_conv)

    admin_reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_support_reply_entry, pattern="^reply_support_")],
        states={
            AWAIT_ADMIN_SUPPORT_REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_support_reply)]
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        per_message=False
    )
    application.add_handler(admin_reply_conv)

    admin_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^👑 پنل ادمین$"), admin_panel_entry)],
        states={
            ADMIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_choice),
            ],
            AWAIT_ADMIN_REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_reply)],
            AWAIT_ADMIN_SELF_COST: [MessageHandler(filters.TEXT, process_admin_self_cost)],
            AWAIT_ADMIN_SELF_MIN: [MessageHandler(filters.TEXT, process_admin_self_min)],
            AWAIT_ADMIN_SELF_PHOTO: [MessageHandler(filters.PHOTO, process_admin_self_photo)],
            AWAIT_ADMIN_SET_CARD_NUMBER: [MessageHandler(filters.TEXT, process_admin_set_card_number)],
            AWAIT_ADMIN_SET_CARD_HOLDER: [MessageHandler(filters.TEXT, process_admin_set_card_holder)],
            AWAIT_NEW_CHANNEL: [MessageHandler(filters.TEXT, process_new_channel)],
            AWAIT_BET_PHOTO: [MessageHandler(filters.PHOTO, process_bet_photo)],
            AWAIT_ADMIN_SET_BALANCE_ID: [MessageHandler(filters.TEXT, process_admin_set_balance_id)],
            AWAIT_ADMIN_SET_BALANCE: [MessageHandler(filters.TEXT, process_admin_set_balance)],
            AWAIT_ADMIN_ADD_BALANCE_ID: [MessageHandler(filters.TEXT, process_admin_add_balance_id)],
            AWAIT_ADMIN_ADD_BALANCE_AMOUNT: [MessageHandler(filters.TEXT, process_admin_add_balance_amount)],
            AWAIT_ADMIN_DEDUCT_BALANCE_ID: [MessageHandler(filters.TEXT, process_admin_deduct_balance_id)],
            AWAIT_ADMIN_DEDUCT_BALANCE_AMOUNT: [MessageHandler(filters.TEXT, process_admin_deduct_balance_amount)],
            AWAIT_ADMIN_TAX: [MessageHandler(filters.TEXT, process_admin_tax)],
            AWAIT_ADMIN_CREDIT_PRICE: [MessageHandler(filters.TEXT, process_admin_credit_price)],
            AWAIT_ADMIN_REFERRAL_PRICE: [MessageHandler(filters.TEXT, process_admin_referral_price)],
            AWAIT_MANAGE_USER_ID: [MessageHandler(filters.TEXT, process_manage_user_id)],
            AWAIT_MANAGE_USER_ROLE: [MessageHandler(filters.TEXT, process_manage_user_role)],
            AWAIT_BROADCAST_MESSAGE: [MessageHandler(filters.ALL, process_admin_broadcast)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        allow_reentry=True
    )
    application.add_handler(admin_conv)
    application.add_handler(InlineQueryHandler(inline_query_handler))
    
    application.add_handler(MessageHandler(filters.Regex(r'^(شرط|بت)$') & filters.ChatType.GROUPS, show_bet_keyboard_handler))
    application.add_handler(MessageHandler(filters.Regex(r'^(شرطبندی|شرط) \d+$') & filters.ChatType.GROUPS, start_bet_handler))
    application.add_handler(MessageHandler(filters.Regex(r'^(انتقال|transfer)\s+(\d+)$') & filters.REPLY & filters.ChatType.GROUPS, transfer_handler))
    application.add_handler(MessageHandler(filters.Regex(r'^موجودی$') & filters.ChatType.GROUPS, group_balance_handler))
    application.add_handler(MessageHandler(filters.Regex(r'^(کسر اعتبار|کسر) \d+$') & filters.REPLY & filters.ChatType.GROUPS, deduct_balance_handler))
    application.add_handler(MessageHandler(filters.Regex(r'^موجودی 💰$') & filters.ChatType.GROUPS, group_balance_handler))
    
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
