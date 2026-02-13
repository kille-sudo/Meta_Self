#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import sys
import os

# بررسی نسخه پایتون
if sys.version_info >= (3, 13):
    print("⚠️ Python 3.13 پشتیبانی نمی‌شود. لطفا Python 3.11 یا 3.12 استفاده کنید.")
    sys.exit(1)

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
from threading import Thread
import time
import sqlite3
import json
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, timedelta
import html
import random

# --- Flask Imports (Web Panel) ---
from flask import Flask, render_template_string, jsonify, request as flask_request

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
from pyrogram import Client, filters as pyro_filters
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
#  تنظیمات لاگینگ
# =======================================================

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

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

# =======================================================
#  متغیرهای سراسری
# =======================================================

# Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN", "8230272382:AAFkPmzMn30b462DJYCP7gAnCdPOMQsCduA")
API_ID = os.getenv("API_ID", "9536480")
API_HASH = os.getenv("API_HASH", "4e52f6f12c47a0da918009260b6e3d44")
OWNER_ID = int(os.getenv("OWNER_ID", "5789565027"))
TEHRAN_TIMEZONE = ZoneInfo("Asia/Tehran")

# Database
DB_NAME = "bot_database.db"

# In-Memory Cache
GLOBAL_USERS = {}
GLOBAL_SETTINGS = {}
GLOBAL_TRANSACTIONS = {}
GLOBAL_BETS = {}
GLOBAL_CHANNELS = {}

# Active Bots
ACTIVE_BOTS = {}
TX_ID_COUNTER = 1
BET_ID_COUNTER = 1
BOT_USERNAME = ""

# Application instance (برای کنترل از پنل وب)
telegram_app = None

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

# Constants
FONT_STYLES = {
    "cursive":      {'0':'𝟎','1':'𝟏','2':'𝟐','3':'𝟑','4':'𝟒','5':'𝟓','6':'𝟔','7':'𝟕','8':'𝟖','9':'𝟗',':':':'},
    "stylized":     {'0':'𝟬','1':'𝟭','2':'𝟮','3':'𝟯','4':'𝟰','5':'𝟱','6':'𝟲','7':'𝟳','8':'𝟴','9':'𝟵',':':':'},
    "doublestruck": {'0':'𝟘','1':'𝟙','2':'𝟚','3':'𝟛','4':'𝟜','5':'𝟝','6':'𝟞','7':'𝟟','8':'𝟠','9':'𝟡',':':':'},
    "monospace":    {'0':'𝟶','1':'𝟷','2':'𝟸','3':'𝟹','4':'𝟺','5':'𝟻','6':'𝟼','7':'𝟽','8':'𝟾','9':'𝟿',':':':'},
    "normal":       {'0':'0','1':'1','2':'2','3':'3','4':'4','5':'5','6':'6','7':'7','8':'8','9':'9',':':':'},
}
FONT_KEYS_ORDER = ["cursive", "stylized", "doublestruck", "monospace", "normal"]
ALL_CLOCK_CHARS = "".join(set(char for font in FONT_STYLES.values() for char in font.values()))
CLOCK_CHARS_REGEX_CLASS = f"[{re.escape(ALL_CLOCK_CHARS)}]"

ENEMY_REPLIES = ["ببخشید متوجه نشدم؟", "داری فشار میخوری؟", "برو پیش بزرگترت", "سطحت پایینه", "😂😂", "اوکی بای"]
SECRETARY_REPLY_MESSAGE = "سلام! در حال حاضر آفلاین هستم و پیام شما را دریافت کردم. در اولین فرصت پاسخ خواهم داد. ممنون از پیامتون."
COMMAND_REGEX = r"^(راهنما|ذخیره|تکرار \d+|حذف \d+|ریاکشن .*|ریاکشن خاموش|کپی روشن|کپی خاموش|لیست دشمن|تاس|تاس \d+|بولینگ|تنظیم عکس|حذف عکس|پنل|panel)$"

# Self Bot States
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
#  HTML Template برای پنل وب
# =======================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 پنل کنترل ربات</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            padding: 40px;
            max-width: 500px;
            width: 100%;
            animation: fadeIn 0.5s ease-in;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 {
            color: #333;
            font-size: 28px;
            margin-bottom: 10px;
        }
        .header .emoji {
            font-size: 60px;
            animation: bounce 2s infinite;
        }
        @keyframes bounce {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-10px); }
        }
        .status-card {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            text-align: center;
        }
        .status-indicator {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            display: inline-block;
            margin-left: 10px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .status-indicator.online {
            background-color: #10b981;
            box-shadow: 0 0 10px #10b981;
        }
        .status-indicator.offline {
            background-color: #ef4444;
            box-shadow: 0 0 10px #ef4444;
        }
        .status-text {
            font-size: 24px;
            font-weight: bold;
            color: #333;
            margin: 10px 0;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin-top: 15px;
        }
        .stat-item {
            background: white;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        .stat-label {
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
        }
        .stat-value {
            font-size: 20px;
            font-weight: bold;
            color: #667eea;
        }
        .button-group {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
        }
        button {
            flex: 1;
            padding: 15px 25px;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s ease;
            color: white;
            position: relative;
            overflow: hidden;
        }
        button:before {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 0;
            height: 0;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.3);
            transform: translate(-50%, -50%);
            transition: width 0.6s, height 0.6s;
        }
        button:active:before {
            width: 300px;
            height: 300px;
        }
        .btn-start {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        }
        .btn-start:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(16, 185, 129, 0.4);
        }
        .btn-stop {
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        }
        .btn-stop:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(239, 68, 68, 0.4);
        }
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .message {
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            text-align: center;
            display: none;
            animation: slideIn 0.3s ease;
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .message.success {
            background-color: #d1fae5;
            color: #065f46;
            border: 2px solid #10b981;
        }
        .message.error {
            background-color: #fee2e2;
            color: #991b1b;
            border: 2px solid #ef4444;
        }
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            color: #666;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="emoji">🤖</div>
            <h1>پنل کنترل ربات تلگرام</h1>
        </div>

        <div class="status-card">
            <div>
                <span class="status-indicator" id="statusIndicator"></span>
                <span class="status-text" id="statusText">در حال بارگذاری...</span>
            </div>
            
            <div class="stats">
                <div class="stat-item">
                    <div class="stat-label">کاربران</div>
                    <div class="stat-value" id="totalUsers">0</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">سلف‌های فعال</div>
                    <div class="stat-value" id="activeBots">0</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">تراکنش‌های معلق</div>
                    <div class="stat-value" id="pendingTx">0</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">زمان اجرا</div>
                    <div class="stat-value" id="uptime">--</div>
                </div>
            </div>
        </div>

        <div class="button-group">
            <button class="btn-start" id="btnStart" onclick="startBot()">
                ▶️ روشن کردن
            </button>
            <button class="btn-stop" id="btnStop" onclick="stopBot()">
                ⏹️ خاموش کردن
            </button>
        </div>

        <div class="message" id="message"></div>

        <div class="footer">
            Made with ❤️ | Auto-refresh: 3s
        </div>
    </div>

    <script>
        let startTime = null;

        async function getStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                updateUI(data);
            } catch (error) {
                console.error('خطا در دریافت وضعیت:', error);
            }
        }

        function formatUptime(seconds) {
            if (!seconds) return '--';
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = seconds % 60;
            
            if (hours > 0) return `${hours}h ${minutes}m`;
            if (minutes > 0) return `${minutes}m ${secs}s`;
            return `${secs}s`;
        }

        function updateUI(status) {
            const indicator = document.getElementById('statusIndicator');
            const statusText = document.getElementById('statusText');
            const btnStart = document.getElementById('btnStart');
            const btnStop = document.getElementById('btnStop');
            
            document.getElementById('totalUsers').textContent = status.total_users || 0;
            document.getElementById('activeBots').textContent = status.active_bots || 0;
            document.getElementById('pendingTx').textContent = status.pending_tx || 0;

            if (status.running) {
                indicator.className = 'status-indicator online';
                statusText.textContent = '🟢 ربات در حال اجرا';
                btnStart.disabled = true;
                btnStop.disabled = false;
                
                if (!startTime) startTime = Date.now();
                const uptime = Math.floor((Date.now() - startTime) / 1000);
                document.getElementById('uptime').textContent = formatUptime(uptime);
            } else {
                indicator.className = 'status-indicator offline';
                statusText.textContent = '🔴 ربات خاموش است';
                btnStart.disabled = false;
                btnStop.disabled = true;
                startTime = null;
                document.getElementById('uptime').textContent = '--';
            }
        }

        function showMessage(text, type) {
            const messageEl = document.getElementById('message');
            messageEl.textContent = text;
            messageEl.className = `message ${type}`;
            messageEl.style.display = 'block';
            setTimeout(() => {
                messageEl.style.display = 'none';
            }, 5000);
        }

        async function startBot() {
            const btn = document.getElementById('btnStart');
            const originalText = btn.innerHTML;
            btn.innerHTML = '<span class="loading"></span> در حال روشن کردن...';
            btn.disabled = true;

            try {
                const response = await fetch('/api/start', { method: 'POST' });
                const data = await response.json();
                showMessage(data.message, data.success ? 'success' : 'error');
                setTimeout(getStatus, 1000);
            } catch (error) {
                showMessage('❌ خطا در ارتباط با سرور', 'error');
            }

            btn.innerHTML = originalText;
        }

        async function stopBot() {
            const btn = document.getElementById('btnStop');
            const originalText = btn.innerHTML;
            btn.innerHTML = '<span class="loading"></span> در حال خاموش کردن...';
            btn.disabled = true;

            try {
                const response = await fetch('/api/stop', { method: 'POST' });
                const data = await response.json();
                showMessage(data.message, data.success ? 'success' : 'error');
                setTimeout(getStatus, 1000);
            } catch (error) {
                showMessage('❌ خطا در ارتباط با سرور', 'error');
            }

            btn.innerHTML = originalText;
        }

        getStatus();
        setInterval(getStatus, 3000);
    </script>
</body>
</html>
"""

# =======================================================
#  بخش دیتابیس
# =======================================================

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
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
#  توابع کمکی (فقط ضروری‌ترین‌ها)
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

# =======================================================
#  Handler های ربات (ساده‌شده)
# =======================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_user_async(update.effective_user.id)
    await update.message.reply_text(
        f"سلام {get_user_display_name(update.effective_user)} عزیز!\n\n🤖 ربات سلف من آماده کار هستم!",
        reply_markup=get_main_keyboard(user_doc)
    )

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_user_async(update.effective_user.id)
    await update.message.reply_text(f"💰 موجودی شما: {user_doc['balance']} الماس")

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = await get_user_async(update.effective_user.id)
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=get_main_keyboard(user_doc))
    return ConversationHandler.END

# =======================================================
#  Flask Web Panel
# =======================================================

web_app = Flask(__name__)
bot_running = False

@web_app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@web_app.route('/api/status')
def api_status():
    return jsonify({
        'running': bot_running,
        'total_users': len(GLOBAL_USERS),
        'active_bots': len(ACTIVE_BOTS),
        'pending_tx': sum(1 for tx in GLOBAL_TRANSACTIONS.values() if tx.get('status') == 'pending')
    })

@web_app.route('/api/start', methods=['POST'])
def api_start():
    global bot_running, telegram_app
    
    if bot_running:
        return jsonify({'success': False, 'message': '⚠️ ربات از قبل در حال اجرا است!'})
    
    try:
        # شروع ربات در thread جدید
        def run_bot():
            global bot_running, telegram_app
            
            from telegram.request import HTTPXRequest
            request = HTTPXRequest(connection_pool_size=8)
            
            telegram_app = Application.builder() \
                .token(BOT_TOKEN) \
                .request(request) \
                .build()
            
            # اضافه کردن handler ها
            telegram_app.add_handler(CommandHandler("start", start_command))
            telegram_app.add_handler(MessageHandler(filters.Regex("^💰 موجودی$"), show_balance))
            
            bot_running = True
            logging.info("✅ ربات روشن شد!")
            
            telegram_app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
        
        bot_thread = Thread(target=run_bot, daemon=True)
        bot_thread.start()
        
        time.sleep(2)  # صبر برای اطمینان از شروع
        return jsonify({'success': True, 'message': '✅ ربات با موفقیت روشن شد!'})
        
    except Exception as e:
        logging.error(f"خطا در روشن کردن ربات: {e}")
        return jsonify({'success': False, 'message': f'❌ خطا: {str(e)}'})

@web_app.route('/api/stop', methods=['POST'])
async def api_stop():
    global bot_running, telegram_app
    
    if not bot_running:
        return jsonify({'success': False, 'message': '⚠️ ربات از قبل خاموش است!'})
    
    try:
        if telegram_app:
            await telegram_app.stop()
            await telegram_app.shutdown()
        
        bot_running = False
        telegram_app = None
        
        logging.info("🔴 ربات خاموش شد!")
        return jsonify({'success': True, 'message': '✅ ربات با موفقیت خاموش شد!'})
        
    except Exception as e:
        logging.error(f"خطا در خاموش کردن ربات: {e}")
        return jsonify({'success': False, 'message': f'❌ خطا: {str(e)}'})

# =======================================================
#  Main Function
# =======================================================

def main():
    print("""
╔═══════════════════════════════════════════╗
║     🤖 ربات سلف من + پنل وب              ║
║     📡 در حال راه‌اندازی...              ║
╚═══════════════════════════════════════════╝
    """)
    
    # راه‌اندازی دیتابیس
    init_db()
    
    # راه‌اندازی وب سرور
    print("🌐 پنل وب در حال اجرا...")
    print("📍 آدرس: http://localhost:5000")
    print("━" * 47)
    
    web_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
