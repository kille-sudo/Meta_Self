import asyncio
import logging
from datetime import datetime
import pytz
from telethon import TelegramClient, events, functions, errors

# ----------------------------------------------------------------
# تنظیمات (این‌ها را پر کنید)
# ----------------------------------------------------------------
API_ID = 9536480        # ای‌پی‌آی آیدی شما
API_HASH = '4e52f6f12c47a0da918009260b6e3d44'  # ای‌پی‌آی هش شما
BOT_TOKEN = '7844919947:AAEle_-4PIXt9P-byCd8YEEJcCV8zAWj7jI'  # توکن رباتی که از BotFather گرفتید را اینجا بگذارید

# متن ثابت بیوگرافی (همان تنظیمات قبلی شما)
BIO_TEMPLATE = "Time in Iran: {time} | 🇮🇷"

# تنظیمات لاگینگ برای دیدن خطاها
logging.basicConfig(format='[%(levelname)s] %(message)s', level=logging.INFO)

# دیکشنری برای ذخیره وضعیت کاربران و کلاینت‌ها
user_sessions = {}

# وضعیت‌ها
STATE_WAITING_PHONE = 'WAITING_PHONE'
STATE_WAITING_CODE = 'WAITING_CODE'
STATE_WAITING_PASSWORD = 'WAITING_PASSWORD'
STATE_LOGGED_IN = 'LOGGED_IN'

# کلاینت ربات (تعریف اولیه بدون استارت)
# تغییر مهم: اینجا دیگر .start() را صدا نمی‌زنیم تا خطا ندهد
bot = TelegramClient('bot_session', API_ID, API_HASH)

# ----------------------------------------------------------------
# بخش 1: لاجیک ساعت
# ----------------------------------------------------------------
async def start_bio_clock(user_client, chat_id):
    """این تابع وظیفه تغییر ساعت بیوگرافی را دارد"""
    print(f"⏳ شروع پروسه تغییر ساعت برای کاربر {chat_id}...")
    try:
        await bot.send_message(chat_id, "✅ ورود موفقیت‌آمیز بود! ساعت بیوگرافی فعال شد.")
    except:
        pass

    last_time = ""
    
    while True:
        try:
            if not user_client.is_connected():
                await user_client.connect()

            # 1. گرفتن زمان فعلی ایران
            iran_timezone = pytz.timezone('Asia/Tehran')
            now = datetime.now(iran_timezone)
            current_time = now.strftime("%H:%M")

            # 2. جلوگیری از آپدیت تکراری
            if current_time != last_time:
                new_bio = BIO_TEMPLATE.format(time=current_time)
                
                # درخواست تغییر پروفایل
                await user_client(functions.account.UpdateProfileRequest(
                    about=new_bio
                ))
                
                logging.info(f"User {chat_id}: Bio updated to {new_bio}")
                last_time = current_time

            # 3. محاسبه زمان خواب دقیق
            seconds_to_wait = 60 - now.second
            await asyncio.sleep(seconds_to_wait)

        except errors.FloodWaitError as e:
            logging.warning(f"FloodWait: Sleeping for {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logging.error(f"Error in clock loop: {e}")
            await asyncio.sleep(60)

# ----------------------------------------------------------------
# بخش 2: هندلرهای ربات
# ----------------------------------------------------------------

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    chat_id = event.chat_id
    if chat_id in user_sessions and user_sessions[chat_id].get('client'):
        await user_sessions[chat_id]['client'].disconnect()
    
    user_sessions[chat_id] = {'state': STATE_WAITING_PHONE}
    
    await event.respond(
        "👋 سلام!\n"
        "برای فعال‌سازی ساعت روی اکانت خود، لطفا شماره موبایل خود را ارسال کنید.\n"
        "مثال: `+989123456789`"
    )

@bot.on(events.NewMessage)
async def message_handler(event):
    chat_id = event.chat_id
    text = event.raw_text.strip()
    
    if text == '/start':
        return

    if chat_id not in user_sessions:
        await event.respond("لطفا ابتدا دستور /start را بزنید.")
        return

    session_data = user_sessions[chat_id]
    state = session_data.get('state')

    # --- مرحله 1: دریافت شماره تلفن ---
    if state == STATE_WAITING_PHONE:
        if not text.startswith('+'):
            await event.respond("شماره باید با + شروع شود. مثال: +98...")
            return

        await event.respond("⏳ در حال اتصال به سرور تلگرام و درخواست کد...")
        
        # ساخت کلاینت جدید برای کاربر (بدون استفاده از حلقه سراسری)
        user_client = TelegramClient(f'session_{chat_id}', API_ID, API_HASH)
        await user_client.connect()

        try:
            send_code = await user_client.send_code_request(text)
            
            session_data['client'] = user_client
            session_data['phone'] = text
            session_data['phone_code_hash'] = send_code.phone_code_hash
            session_data['state'] = STATE_WAITING_CODE
            
            await event.respond(
                "✅ کد تایید به تلگرام (یا SMS) شما ارسال شد.\n"
                "لطفا کد را وارد کنید (فقط اعداد):"
            )
            
        except Exception as e:
            await event.respond(f"❌ خطا در ارسال کد: {str(e)}\nمجدد تلاش کنید: /start")
            await user_client.disconnect()

    # --- مرحله 2: دریافت کد تایید ---
    elif state == STATE_WAITING_CODE:
        if not text.isdigit():
            await event.respond("کد فقط باید شامل اعداد باشد.")
            return

        user_client = session_data['client']
        phone = session_data['phone']
        phone_code_hash = session_data['phone_code_hash']

        try:
            await event.respond("⏳ در حال بررسی کد...")
            await user_client.sign_in(phone=phone, code=text, phone_code_hash=phone_code_hash)
            
            session_data['state'] = STATE_LOGGED_IN
            asyncio.create_task(start_bio_clock(user_client, chat_id))
            
        except errors.SessionPasswordNeededError:
            session_data['state'] = STATE_WAITING_PASSWORD
            await event.respond("🔒 این اکانت دارای تایید دو مرحله‌ای است.\nلطفا رمز عبور (Password) خود را وارد کنید:")
            
        except errors.PhoneCodeInvalidError:
            await event.respond("❌ کد وارد شده اشتباه است. لطفا دوباره کد صحیح را بفرستید.")
        except Exception as e:
            await event.respond(f"❌ خطا: {str(e)}\nمجدد تلاش کنید: /start")

    # --- مرحله 3: دریافت پسورد ---
    elif state == STATE_WAITING_PASSWORD:
        user_client = session_data['client']
        try:
            await event.respond("⏳ در حال بررسی رمز عبور...")
            await user_client.sign_in(password=text)
            
            session_data['state'] = STATE_LOGGED_IN
            asyncio.create_task(start_bio_clock(user_client, chat_id))
            
        except errors.PasswordHashInvalidError:
            await event.respond("❌ رمز عبور اشتباه است. دوباره تلاش کنید:")
        except Exception as e:
            await event.respond(f"❌ خطا: {str(e)}\nمجدد تلاش کنید: /start")

# ----------------------------------------------------------------
# اجرای برنامه (اصلاح شده برای رفع ارور Loop)
# ----------------------------------------------------------------
async def main():
    # استارت کردن ربات در داخل تابع async
    await bot.start(bot_token=BOT_TOKEN)
    print("🤖 Bot started and running...")
    
    # اجرای ربات تا زمانی که قطع شود
    await bot.run_until_disconnected()

if __name__ == '__main__':
    # استفاده از asyncio.run برای مدیریت صحیح Event Loop در پایتون جدید
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Critical Error: {e}")
