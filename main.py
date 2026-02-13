#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import streamlit as st
import asyncio
import sys
import os

# بررسی نسخه پایتون
if sys.version_info >= (3, 13):
    st.error("⚠️ Python 3.13 پشتیبانی نمی‌شود. لطفا Python 3.11 استفاده کنید.")
    st.stop()

# ==== FIX: Event Loop ====
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
from threading import Thread
import time
import sqlite3
import json
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, timedelta
import html
import random

# تنظیمات صفحه
st.set_page_config(
    page_title="🤖 ربات سلف من",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS سفارشی
st.markdown("""
<style>
    .main { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
    .stButton>button {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        color: white;
        font-weight: bold;
        border: none;
        border-radius: 10px;
        padding: 10px 20px;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(16, 185, 129, 0.4);
    }
    .metric-card {
        background: white;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin: 10px 0;
    }
    .status-online {
        color: #10b981;
        font-weight: bold;
    }
    .status-offline {
        color: #ef4444;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# --- Telegram Bot Imports ---
from telegram import (Update, ReplyKeyboardMarkup, KeyboardButton,
                      InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove,
                      InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultCachedPhoto)
from telegram.constants import ParseMode
from telegram.ext import (Application, CommandHandler, MessageHandler,
                          ConversationHandler, filters, ContextTypes, CallbackQueryHandler,
                          ApplicationHandlerStop, TypeHandler, InlineQueryHandler)
from telegram.request import HTTPXRequest
import telegram.error

# --- Pyrogram Imports ---
try:
    from pyrogram import Client, filters as pyro_filters
    from pyrogram.handlers import MessageHandler as PyroMessageHandler
    from pyrogram.enums import ChatType, ChatAction
    from pyrogram.raw import functions
    from pyrogram.errors import (
        SessionPasswordNeeded, UserDeactivated, AuthKeyUnregistered,
        ChatSendInlineForbidden
    )
    import pyrogram.utils
    PYROGRAM_AVAILABLE = True
except ImportError:
    PYROGRAM_AVAILABLE = False
    st.warning("⚠️ Pyrogram نصب نیست - سلف بات غیرفعال است")

def patch_peer_id_validation():
    if not PYROGRAM_AVAILABLE:
        return
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

# =======================================================
#  متغیرهای سراسری
# =======================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8481431417:AAEB4dNawnyCQBH8KHtkKaFaQu_AcbmlHu0")
API_ID = os.getenv("API_ID", "9536480")
API_HASH = os.getenv("API_HASH", "4e52f6f12c47a0da918009260b6e3d44")
OWNER_ID = int(os.getenv("OWNER_ID", "5789565027"))
TEHRAN_TIMEZONE = ZoneInfo("Asia/Tehran")

DB_NAME = "bot_database.db"

GLOBAL_USERS = {}
GLOBAL_SETTINGS = {}
GLOBAL_TRANSACTIONS = {}
GLOBAL_BETS = {}
GLOBAL_CHANNELS = {}

ACTIVE_BOTS = {}
TX_ID_COUNTER = 1
BET_ID_COUNTER = 1
BOT_USERNAME = ""

# Conversation States
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

# Self Bot States
ACTIVE_ENEMIES = {}
USER_FONT_CHOICES = {}
CLOCK_STATUS = {}
SECRETARY_MODE_STATUS = {}
AUTO_SEEN_STATUS = {}

# Session State
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False
if 'bot_app' not in st.session_state:
    st.session_state.bot_app = None
if 'start_time' not in st.session_state:
    st.session_state.start_time = None

# =======================================================
#  دیتابیس
# =======================================================

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    global TX_ID_COUNTER, BET_ID_COUNTER
    logging.info("🗄️ Initializing database...")
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, data TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (tx_id INTEGER PRIMARY KEY, data TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS bets (bet_id INTEGER PRIMARY KEY, data TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS channels (username TEXT PRIMARY KEY, data TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (phone TEXT PRIMARY KEY, session_string TEXT, user_id INTEGER, real_owner_id INTEGER, settings TEXT)''')
    conn.commit()
    
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
        logging.error(f"Error loading data: {e}")
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

async def get_setting_async(name): 
    return GLOBAL_SETTINGS.get(name)

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

# =======================================================
#  توابع کمکی
# =======================================================

def get_user_display_name(user):
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
    [KeyboardButton("👤 تنظیم صاحب کارت"), KeyboardButton("📈 تنظیم قیمت الماس")],
    [KeyboardButton("➕ افزایش الماس کاربر"), KeyboardButton("➖ کسر الماس کاربر")],
    [KeyboardButton("⬅️ بازگشت به منوی اصلی")]
], resize_keyboard=True)

# =======================================================
#  Handler های ربات (کامل)
# =======================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_user_async(update.effective_user.id)
    await update.message.reply_text(
        f"سلام {get_user_display_name(update.effective_user)} عزیز!\n\n✨ خوش اومدی به ربات سلف من!",
        reply_markup=get_main_keyboard(user_doc)
    )

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_user_async(update.effective_user.id)
    await update.message.reply_text(f"💰 موجودی شما: **{user_doc['balance']}** الماس", parse_mode=ParseMode.MARKDOWN)

async def get_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_name = context.bot.username
    link = f"https://t.me/{bot_name}?start={user_id}"
    await update.message.reply_text(f"🎁 لینک دعوت شما:\n{link}\n\nبا دعوت هر نفر الماس رایگان بگیرید!")

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_user_async(update.effective_user.id)
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=get_main_keyboard(user_doc))
    return ConversationHandler.END

# Admin Handlers
async def admin_panel_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_user_async(update.effective_user.id)
    if not user_doc.get('is_owner'):
        await update.message.reply_text("⛔️ دسترسی محدود!")
        return ConversationHandler.END
    await update.message.reply_text("👑 پنل ادمین:", reply_markup=admin_keyboard)
    return ADMIN_MENU

async def process_admin_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    
    if choice == "📊 آمار کلی":
        total_users = len(GLOBAL_USERS)
        pending_tx = sum(1 for tx in GLOBAL_TRANSACTIONS.values() if tx.get('status') == 'pending')
        await update.message.reply_text(
            f"📊 **آمار کلی:**\n\n"
            f"👥 کاربران: {total_users}\n"
            f"🧾 تراکنش‌های معلق: {pending_tx}\n"
            f"🤖 سلف‌های فعال: {len(ACTIVE_BOTS)}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_keyboard
        )
        return ADMIN_MENU
    
    elif choice == "⬅️ بازگشت به منوی اصلی":
        user_doc = await get_user_async(update.effective_user.id)
        await update.message.reply_text("منوی اصلی:", reply_markup=get_main_keyboard(user_doc))
        return ConversationHandler.END
    
    return ADMIN_MENU

# Deposit Handlers
async def deposit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا تعداد الماسی که می‌خواهید بخرید را وارد کنید:", reply_markup=ReplyKeyboardRemove())
    return AWAIT_DEPOSIT_AMOUNT

async def process_deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount <= 0: raise ValueError
        
        price = int(GLOBAL_SETTINGS.get('credit_price', '1000'))
        total_cost = amount * price
        context.user_data['deposit_amount'] = amount
        
        card_number = GLOBAL_SETTINGS.get('card_number', 'تنظیم نشده')
        card_holder = GLOBAL_SETTINGS.get('card_holder', 'تنظیم نشده')
        
        await update.message.reply_text(
            f"💳 **اطلاعات پرداخت:**\n\n"
            f"💰 مبلغ: {total_cost:,} تومان\n"
            f"💎 الماس: {amount}\n\n"
            f"📌 شماره کارت: `{card_number}`\n"
            f"👤 صاحب حساب: {card_holder}\n\n"
            f"لطفا رسید پرداخت را ارسال کنید:",
            parse_mode=ParseMode.MARKDOWN
        )
        return AWAIT_DEPOSIT_RECEIPT
    except:
        await update.message.reply_text("❌ لطفا یک عدد صحیح وارد کنید.")
        return AWAIT_DEPOSIT_AMOUNT

async def process_deposit_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TX_ID_COUNTER
    if not update.message.photo:
        await update.message.reply_text("❌ لطفا عکس رسید را ارسال کنید.")
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
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
    TX_ID_COUNTER += 1
    
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO transactions (tx_id, data) VALUES (?, ?)', (tx_id, json.dumps(GLOBAL_TRANSACTIONS[tx_id])))
    conn.commit()
    conn.close()
    
    # ارسال به ادمین
    try:
        caption = f"🧾 **درخواست شارژ جدید**\n\nکاربر: {user.mention_html()}\nID: `{user.id}`\nالماس: {amount}"
        reply_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ تایید", callback_data=f"tx_approve_{tx_id}"),
            InlineKeyboardButton("❌ رد", callback_data=f"tx_reject_{tx_id}")
        ]])
        await context.bot.send_photo(
            chat_id=OWNER_ID,
            photo=receipt_file_id,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.warning(f"Could not send to owner: {e}")
    
    user_doc = await get_user_async(user.id)
    await update.message.reply_text("✅ رسید شما ارسال شد. پس از تایید، الماس شما شارژ می‌شود.", reply_markup=get_main_keyboard(user_doc))
    return ConversationHandler.END

# Support Handlers
async def support_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا پیام خود را برای پشتیبانی بنویسید:", reply_markup=ReplyKeyboardRemove())
    return AWAIT_SUPPORT_MESSAGE

async def process_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_doc = await get_user_async(user.id)
    text = f"📨 **پیام پشتیبانی**\n\nکاربر: {user.mention_html()}\nID: `{user.id}`\n\n{update.message.text}"
    
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.warning(f"Could not send support message: {e}")
    
    await update.message.reply_text("✅ پیام شما ارسال شد.", reply_markup=get_main_keyboard(user_doc))
    return ConversationHandler.END

# Callback Handler
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("tx_"):
        parts = data.split('_')
        action = parts[1]
        tx_id = int(parts[2])
        tx = GLOBAL_TRANSACTIONS.get(tx_id)
        
        if not tx:
            await query.answer("تراکنش یافت نشد!", show_alert=True)
            return
        
        if tx['status'] != 'pending':
            await query.answer("قبلاً پردازش شده!", show_alert=True)
            return
        
        if action == "approve":
            tx['status'] = 'approved'
            u_doc = await get_user_async(tx['user_id'])
            u_doc['balance'] += tx['amount']
            save_user_immediate(tx['user_id'])
            
            conn = get_db_connection()
            conn.execute('INSERT OR REPLACE INTO transactions (tx_id, data) VALUES (?, ?)', (tx_id, json.dumps(tx)))
            conn.commit()
            conn.close()
            
            await context.bot.send_message(tx['user_id'], f"✅ شارژ {tx['amount']} الماس انجام شد!")
            await query.edit_message_caption(caption=query.message.caption + "\n\n✅ تایید شد")
        
        elif action == "reject":
            tx['status'] = 'rejected'
            conn = get_db_connection()
            conn.execute('INSERT OR REPLACE INTO transactions (tx_id, data) VALUES (?, ?)', (tx_id, json.dumps(tx)))
            conn.commit()
            conn.close()
            
            await context.bot.send_message(tx['user_id'], "❌ درخواست شارژ رد شد.")
            await query.edit_message_caption(caption=query.message.caption + "\n\n❌ رد شد")

# =======================================================
#  کنترل ربات از Streamlit
# =======================================================

def run_telegram_bot():
    """اجرای ربات تلگرام"""
    try:
        request = HTTPXRequest(connection_pool_size=8)
        
        app = Application.builder() \
            .token(BOT_TOKEN) \
            .request(request) \
            .build()
        
        # Handler ها
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(MessageHandler(filters.Regex("^💰 موجودی$"), show_balance))
        app.add_handler(MessageHandler(filters.Regex("^🎁 الماس رایگان$"), get_referral_link))
        
        # Deposit Conversation
        deposit_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^💳 افزایش الماس$"), deposit_entry)],
            states={
                AWAIT_DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_deposit_amount)],
                AWAIT_DEPOSIT_RECEIPT: [MessageHandler(filters.PHOTO, process_deposit_receipt)]
            },
            fallbacks=[CommandHandler('cancel', cancel_conversation)],
            allow_reentry=True
        )
        app.add_handler(deposit_conv)
        
        # Support Conversation
        support_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^💬 پشتیبانی$"), support_entry)],
            states={
                AWAIT_SUPPORT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_support_message)]
            },
            fallbacks=[CommandHandler('cancel', cancel_conversation)],
            allow_reentry=True
        )
        app.add_handler(support_conv)
        
        # Admin Panel
        admin_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^👑 پنل ادمین$"), admin_panel_entry)],
            states={
                ADMIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_admin_choice)],
            },
            fallbacks=[CommandHandler('cancel', cancel_conversation)],
            allow_reentry=True
        )
        app.add_handler(admin_conv)
        
        # Callback Handler
        app.add_handler(CallbackQueryHandler(callback_query_handler))
        
        st.session_state.bot_app = app
        
        logging.info("✅ ربات شروع به کار کرد!")
        
        # اجرای polling
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logging.error(f"❌ خطا در اجرای ربات: {e}")
        st.session_state.bot_running = False

def start_bot():
    """شروع ربات"""
    if st.session_state.bot_running:
        return False, "⚠️ ربات از قبل در حال اجرا است!"
    
    try:
        bot_thread = Thread(target=run_telegram_bot, daemon=True)
        bot_thread.start()
        
        st.session_state.bot_running = True
        st.session_state.start_time = time.time()
        
        time.sleep(2)
        return True, "✅ ربات با موفقیت روشن شد!"
        
    except Exception as e:
        return False, f"❌ خطا: {str(e)}"

async def stop_bot():
    """خاموش کردن ربات"""
    if not st.session_state.bot_running:
        return False, "⚠️ ربات از قبل خاموش است!"
    
    try:
        if st.session_state.bot_app:
            await st.session_state.bot_app.stop()
            await st.session_state.bot_app.shutdown()
        
        st.session_state.bot_running = False
        st.session_state.bot_app = None
        st.session_state.start_time = None
        
        return True, "✅ ربات خاموش شد!"
        
    except Exception as e:
        return False, f"❌ خطا: {str(e)}"

# =======================================================
#  UI اصلی
# =======================================================

def format_uptime(seconds):
    if not seconds:
        return "0s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"

def main():
    init_db()
    
    # Sidebar
    with st.sidebar:
        st.title("⚙️ تنظیمات")
        
        st.markdown("### 🔧 پیکربندی")
        new_price = st.number_input("قیمت الماس (تومان)", value=int(GLOBAL_SETTINGS.get('credit_price', '1000')), step=100)
        if st.button("💾 ذخیره قیمت"):
            asyncio.run(set_setting_async('credit_price', new_price))
            st.success("✅ ذخیره شد!")
        
        st.markdown("---")
        st.markdown("### 📊 آمار سریع")
        st.metric("👥 کاربران", len(GLOBAL_USERS))
        st.metric("🤖 سلف فعال", len(ACTIVE_BOTS))
        st.metric("🧾 تراکنش معلق", sum(1 for tx in GLOBAL_TRANSACTIONS.values() if tx.get('status') == 'pending'))
    
    # Main Panel
    st.markdown("""
    <div style='text-align: center; background: white; padding: 30px; border-radius: 20px; margin-bottom: 20px;'>
        <h1 style='font-size: 50px; margin: 0;'>🤖</h1>
        <h2 style='color: #333;'>ربات سلف من - پنل کنترل</h2>
        <p style='color: #666;'>مدیریت کامل ربات تلگرام شما</p>
    </div>
    """, unsafe_allow_html=True)
    
    # وضعیت
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status_emoji = "🟢" if st.session_state.bot_running else "🔴"
        status_text = "در حال اجرا" if st.session_state.bot_running else "خاموش"
        st.markdown(f"""
        <div class='metric-card'>
            <h3>{status_emoji} وضعیت ربات</h3>
            <p style='font-size: 20px; font-weight: bold; color: {"#10b981" if st.session_state.bot_running else "#ef4444"};'>{status_text}</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        uptime = format_uptime(time.time() - st.session_state.start_time) if st.session_state.start_time else "0s"
        st.markdown(f"""
        <div class='metric-card'>
            <h3>⏱️ زمان اجرا</h3>
            <p style='font-size: 20px; font-weight: bold; color: #667eea;'>{uptime}</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class='metric-card'>
            <h3>💰 قیمت الماس</h3>
            <p style='font-size: 20px; font-weight: bold; color: #f59e0b;'>{GLOBAL_SETTINGS.get('credit_price', '1000')} تومان</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # کنترل‌ها
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        if st.button("▶️ روشن کردن ربات", disabled=st.session_state.bot_running, use_container_width=True, type="primary"):
            with st.spinner("در حال روشن کردن..."):
                success, message = start_bot()
                if success:
                    st.success(message)
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(message)
    
    with col2:
        if st.button("⏹️ خاموش کردن ربات", disabled=not st.session_state.bot_running, use_container_width=True):
            with st.spinner("در حال خاموش کردن..."):
                success, message = asyncio.run(stop_bot())
                if success:
                    st.success(message)
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(message)
    
    with col3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    # جداول داده
    st.markdown("---")
    
    tab1, tab2, tab3 = st.tabs(["👥 کاربران", "🧾 تراکنش‌ها", "📊 آمار تفصیلی"])
    
    with tab1:
        if GLOBAL_USERS:
            st.markdown("### 👥 لیست کاربران")
            users_data = []
            for uid, udata in GLOBAL_USERS.items():
                users_data.append({
                    "ID": uid,
                    "نام": udata.get('first_name', 'N/A'),
                    "موجودی": udata.get('balance', 0),
                    "ادمین": "✅" if udata.get('is_admin') else "❌"
                })
            st.dataframe(users_data, use_container_width=True)
        else:
            st.info("هنوز کاربری ثبت نشده")
    
    with tab2:
        if GLOBAL_TRANSACTIONS:
            st.markdown("### 🧾 تراکنش‌های اخیر")
            tx_data = []
            for tx_id, tx in list(GLOBAL_TRANSACTIONS.items())[-10:]:
                tx_data.append({
                    "ID": tx_id,
                    "کاربر": tx.get('user_id'),
                    "مقدار": tx.get('amount'),
                    "وضعیت": tx.get('status'),
                    "زمان": tx.get('timestamp', 'N/A')[:19]
                })
            st.dataframe(tx_data, use_container_width=True)
        else:
            st.info("هنوز تراکنشی ثبت نشده")
    
    with tab3:
        st.markdown("### 📊 آمار کلی")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("مجموع الماس در سیستم", sum(u.get('balance', 0) for u in GLOBAL_USERS.values()))
            st.metric("تراکنش‌های تایید شده", sum(1 for tx in GLOBAL_TRANSACTIONS.values() if tx.get('status') == 'approved'))
        
        with col2:
            st.metric("تراکنش‌های رد شده", sum(1 for tx in GLOBAL_TRANSACTIONS.values() if tx.get('status') == 'rejected'))
            st.metric("کانال‌های عضویت اجباری", len(GLOBAL_CHANNELS))
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: white; padding: 20px;'>
        <p>ساخته شده با ❤️ | Auto-refresh: 5s</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Auto-refresh
    if st.session_state.bot_running:
        time.sleep(5)
        st.rerun()

if __name__ == "__main__":
    main()
