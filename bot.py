import asyncio
import logging
import os
import shlex
import html
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, 
    ReplyKeyboardRemove, BotCommand
)
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
import validators
import strings
import qr_generator
import qr_reader
from middlewares import ThrottlingMiddleware
from aiogram.fsm.context import FSMContext
from states import TextQRStates, UrlQRStates, WifiQRStates, VCardQRStates, EncodeQRStates, GeoQRStates, ColorQRStates, QRReaderStates
import admin
import notifications
import time

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SENTINEL_KEY = os.getenv("SENTINEL_KEY")
MAINTENANCE_TZ_NAME = os.getenv("MAINTENANCE_TIMEZONE", "Asia/Kuala_Lumpur")
try:
    MAINTENANCE_HOUR = int(os.getenv("MAINTENANCE_HOUR", "8"))
except ValueError:
    MAINTENANCE_HOUR = 8
if not 0 <= MAINTENANCE_HOUR <= 23:
    MAINTENANCE_HOUR = 8

try:
    MAINTENANCE_MINUTE = int(os.getenv("MAINTENANCE_MINUTE", os.getenv("DAILY_LOG_MINUTE", "0")))
except ValueError:
    MAINTENANCE_MINUTE = 0
if not 0 <= MAINTENANCE_MINUTE <= 59:
    MAINTENANCE_MINUTE = 0

try:
    MAINTENANCE_TZ = ZoneInfo(MAINTENANCE_TZ_NAME)
except Exception:
    logger = logging.getLogger(__name__)
    logger.warning(
        "Invalid MAINTENANCE_TIMEZONE=%s. Falling back to UTC+08:00.",
        MAINTENANCE_TZ_NAME
    )
    MAINTENANCE_TZ = timezone(timedelta(hours=8))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.WARNING,
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Bot and Dispatcher
dp = Dispatcher()
dp.message.middleware(ThrottlingMiddleware(limit_light=2.0, limit_heavy=10.0))
dp.include_router(admin.router)

def parse_args(text):
    """
    Parses arguments from text, handling quotes.
    Returns a list of arguments.
    """
    try:
        if not text: return []
        # Remove command (first word)
        command_removed = text.split(' ', 1)[1] if ' ' in text else ''
        if not command_removed:
            return []
        return shlex.split(command_removed)
    except ValueError:
        return None # Malformed quotes

async def send_photo_with_retry(message: types.Message, photo: types.BufferedInputFile, retries: int = 3):
    """Sends a photo with exponential backoff for network errors."""
    import aiohttp
    from aiogram.exceptions import TelegramNetworkError
    
    for attempt in range(retries):
        try:
            await message.reply_photo(photo)
            return
        except (TelegramNetworkError, aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError) as e:
            if attempt == retries - 1:
                raise e
            wait_time = (attempt + 1) * 2
            logger.warning(f"Network error sending photo (attempt {attempt+1}/{retries}): {e}. Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
        except Exception as e:
             logger.error(f"Unexpected error sending photo: {e}")
             raise e
    
    # If we get here, all retries failed
    logger.error(f"Failed to send photo after {retries} attempts.")
    raise TelegramNetworkError("Failed to send photo after multiple retries.")

@dp.message(Command("start"))
async def start(message: types.Message):
    """Send a message when the command /start is issued."""
    welcome_text = strings.WELCOME_MSG
    await message.reply(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(Command("help"))
async def help_command(message: types.Message):
    """Send a message when the command /help is issued."""
    help_text = strings.HELP_MSG
    await message.reply(help_text, parse_mode='Markdown')

@dp.message(Command("about"))
async def about_command(message: types.Message):
    """Send a message when the command /about is issued."""
    await message.reply(strings.ABOUT_MSG, parse_mode='Markdown')

@dp.message(Command("textqr"))
async def text_qr(message: types.Message, state: FSMContext, bot: Bot):
    """Generate QR from text."""
    args = parse_args(message.text)
    if not args:
        await state.set_state(TextQRStates.waiting_for_text)
        await message.reply(strings.PROMPT_TEXT_QR)
        return
    text = " ".join(args)
    
    await generate_text_qr(message, bot, text)

@dp.message(TextQRStates.waiting_for_text)
async def process_text_qr(message: types.Message, state: FSMContext, bot: Bot):
    """Process text from state."""
    await state.clear()
    await generate_text_qr(message, bot, message.text)

async def generate_text_qr(message: types.Message, bot: Bot, text: str):
    """Helper to generate text QR."""
    from database import db
    status_msg = await message.reply(strings.STATUS_GENERATING)
    
    try:
        start_time = time.time()
        
        # Get user's custom QR style
        user_style = db.get_user_qr_style(message.from_user.id)
        style = None
        
        if user_style:
            from qr_generator import QRStyle, QRColor
            fg_color, bg_color = user_style
            style = QRStyle(
                fg_color=QRColor(*fg_color),
                bg_color=QRColor(*bg_color)
            )
        
        # Run in process pool to avoid blocking event loop
        loop = asyncio.get_running_loop()
        bio = await loop.run_in_executor(bot.process_pool, qr_generator.generate_qr, text, style)
        
        # Record performance
        db.record_performance(time.time() - start_time)

        # Aiogram expects a file-like object or path
        input_file = BufferedInputFile(bio.getvalue(), filename="qr.png")
        
        await message.reply(strings.SUCCESS_GENERATE)
        await send_photo_with_retry(message, input_file)
    except qr_generator.QRGenerationError as e:
        logger.warning(f"User:{message.from_user.id} | QR Generation Error in text_qr: {e}")
        db.record_error("QRGenerationError")
        await message.reply(str(e))
    except TelegramNetworkError as e:
        logger.error(f"User:{message.from_user.id} | Network Error in text_qr: {e}")
        db.record_error("TelegramNetworkError")
        await message.reply("⚠️ Network error. The request timed out. Please try again.")
    except Exception as e:
        logger.error(f"User:{message.from_user.id} | Error in text_qr: {e}")
        db.record_error("GenericError")
        await message.reply(strings.ERROR_GENERIC)
    finally:
        await status_msg.delete()

@dp.message(Command("urlqr"))
async def url_qr(message: types.Message, state: FSMContext, bot: Bot):
    """Generate QR from URL."""
    args = parse_args(message.text)
    if not args:
        await state.set_state(UrlQRStates.waiting_for_url)
        await message.reply(strings.PROMPT_URL_QR)
        return

    url = args[0]
    await generate_url_qr(message, bot, url)

@dp.message(UrlQRStates.waiting_for_url)
async def process_url_qr(message: types.Message, state: FSMContext, bot: Bot):
    """Process URL from state."""
    await state.clear()
    await generate_url_qr(message, bot, message.text)

async def generate_url_qr(message: types.Message, bot: Bot, url: str):
    """Helper to generate URL QR."""
    if not validators.url(url):
        await message.reply("⚠️ Invalid URL! Please include http:// or https://.", parse_mode='Markdown')
        return

    if len(url) > 500:
        await message.reply("⚠️ *Warning:* Your URL is very long (>500 chars). This may result in a dense QR code that is difficult to scan.", parse_mode='Markdown')

    status_msg = await message.reply(strings.STATUS_GENERATING)

    try:
        start_time = time.time()
        
        # Get user's custom QR style
        from database import db
        user_style = db.get_user_qr_style(message.from_user.id)
        style = None
        
        if user_style:
            from qr_generator import QRStyle, QRColor
            fg_color, bg_color = user_style
            style = QRStyle(
                fg_color=QRColor(*fg_color),
                bg_color=QRColor(*bg_color)
            )
        
        # Run in process pool
        loop = asyncio.get_running_loop()
        bio = await loop.run_in_executor(bot.process_pool, qr_generator.generate_qr, url, style)
        
        from database import db
        db.record_performance(time.time() - start_time)

        input_file = BufferedInputFile(bio.getvalue(), filename="qr.png")
        await message.reply(strings.SUCCESS_GENERATE)
        await send_photo_with_retry(message, input_file)
    except qr_generator.QRGenerationError as e:
        logger.warning(f"User:{message.from_user.id} | QR Generation Error in url_qr: {e}")
        from database import db
        db.record_error("QRGenerationError")
        await message.reply(str(e))
    except TelegramNetworkError as e:
        logger.error(f"User:{message.from_user.id} | Network Error in url_qr: {e}")
        from database import db
        db.record_error("TelegramNetworkError")
        await message.reply("⚠️ Network error. The request timed out. Please try again.")
    except Exception as e:
        logger.error(f"User:{message.from_user.id} | Error in url_qr: {e}")
        from database import db
        db.record_error("GenericError")
        await message.reply(strings.ERROR_GENERIC)
    finally:
        await status_msg.delete()

# WiFi QR handlers
@dp.message(Command("wifiqr"))
async def wifi_qr(message: types.Message, state: FSMContext):
    """Generate WiFi QR."""
    args = parse_args(message.text)
    
    if not args or len(args) < 3:
        await state.set_state(WifiQRStates.waiting_for_ssid)
        await message.reply(strings.PROMPT_WIFI_SSID)
        return

    ssid, password, auth_type = args[0], args[1], args[2]
    await generate_wifi_qr(message, message.bot, ssid, password, auth_type)

@dp.message(WifiQRStates.waiting_for_ssid)
async def process_wifi_ssid(message: types.Message, state: FSMContext):
    await state.update_data(ssid=message.text)
    await state.set_state(WifiQRStates.waiting_for_password)
    await message.reply(strings.PROMPT_WIFI_PASSWORD)

@dp.message(WifiQRStates.waiting_for_password)
async def process_wifi_password(message: types.Message, state: FSMContext):
    await state.update_data(password=message.text)
    await state.set_state(WifiQRStates.waiting_for_auth_type)
    
    kb = [
        [KeyboardButton(text="WPA"), KeyboardButton(text="WEP")],
        [KeyboardButton(text="nopass")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
    await message.reply(strings.PROMPT_WIFI_AUTH, reply_markup=keyboard)

@dp.message(WifiQRStates.waiting_for_auth_type)
async def process_wifi_auth(message: types.Message, state: FSMContext, bot: Bot):
    auth_type = message.text
    data = await state.get_data()
    await state.clear()
    
    status_msg = await message.reply(strings.STATUS_GENERATING, reply_markup=ReplyKeyboardRemove())
    await generate_wifi_qr(message, bot, data['ssid'], data['password'], auth_type, status_msg)

async def generate_wifi_qr(message: types.Message, bot: Bot, ssid, password, auth_type, status_msg: types.Message = None):
    if not status_msg:
        status_msg = await message.reply(strings.STATUS_GENERATING)

    try:
        start_time = time.time()
        
        # Get user's custom QR style
        from database import db
        user_style = db.get_user_qr_style(message.from_user.id)
        style = None
        
        if user_style:
            from qr_generator import QRStyle, QRColor
            fg_color, bg_color = user_style
            style = QRStyle(
                fg_color=QRColor(*fg_color),
                bg_color=QRColor(*bg_color)
            )
        
        loop = asyncio.get_running_loop()
        bio = await loop.run_in_executor(bot.process_pool, qr_generator.generate_wifi_qr, ssid, password, auth_type, style)
        
        db.record_performance(time.time() - start_time)

        input_file = BufferedInputFile(bio.getvalue(), filename="qr.png")
        await message.reply(strings.SUCCESS_GENERATE)
        await send_photo_with_retry(message, input_file)
    except Exception as e:
        logger.error(f"Error generating WiFi QR: {e}")
        from database import db
        db.record_error("GenericError")
        await message.reply(strings.ERROR_GENERIC)
    finally:
        await status_msg.delete()

# VCard QR handlers
@dp.message(Command("vcardqr"))
async def vcard_qr(message: types.Message, state: FSMContext):
    """Generate vCard QR."""
    args = parse_args(message.text)
    
    if not args or len(args) < 3:
        await state.set_state(VCardQRStates.waiting_for_name)
        await message.reply(strings.PROMPT_VCARD_NAME)
        return

    name, phone, email = args[0], args[1], args[2]
    await generate_vcard_qr(message, message.bot, name, phone, email)

@dp.message(VCardQRStates.waiting_for_name)
async def process_vcard_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(VCardQRStates.waiting_for_phone)
    await message.reply(strings.PROMPT_VCARD_PHONE)

@dp.message(VCardQRStates.waiting_for_phone)
async def process_vcard_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(VCardQRStates.waiting_for_email)
    await message.reply(strings.PROMPT_VCARD_EMAIL)

@dp.message(VCardQRStates.waiting_for_email)
async def process_vcard_email(message: types.Message, state: FSMContext, bot: Bot):
    email = message.text
    data = await state.get_data()
    await state.clear()
    await generate_vcard_qr(message, bot, data['name'], data['phone'], email)

async def generate_vcard_qr(message: types.Message, bot: Bot, name, phone, email):
    status_msg = await message.reply(strings.STATUS_GENERATING)

    try:
        start_time = time.time()
        
        # Get user's custom QR style
        from database import db
        user_style = db.get_user_qr_style(message.from_user.id)
        style = None
        
        if user_style:
            from qr_generator import QRStyle, QRColor
            fg_color, bg_color = user_style
            style = QRStyle(
                fg_color=QRColor(*fg_color),
                bg_color=QRColor(*bg_color)
            )
        
        loop = asyncio.get_running_loop()
        bio = await loop.run_in_executor(bot.process_pool, qr_generator.generate_vcard_qr, name, phone, email, style)
        
        db.record_performance(time.time() - start_time)

        input_file = BufferedInputFile(bio.getvalue(), filename="qr.png")
        await message.reply(strings.SUCCESS_GENERATE)
        await send_photo_with_retry(message, input_file)
    except Exception as e:
        logger.error(f"Error generating vCard QR: {e}")
        from database import db
        db.record_error("GenericError")
        await message.reply(strings.ERROR_GENERIC)
    finally:
        await status_msg.delete()

# Encode QR handlers
@dp.message(Command("encodeqr"))
async def encode_qr(message: types.Message, state: FSMContext):
    """Generate encoded QR."""
    args = parse_args(message.text)
    
    if not args or len(args) < 2:
        await state.set_state(EncodeQRStates.waiting_for_text)
        await message.reply(strings.PROMPT_ENCODE_TEXT)
        return

    method = args[-1]
    text = " ".join(args[:-1])
    await generate_encode_qr(message, message.bot, text, method)

@dp.message(EncodeQRStates.waiting_for_text)
async def process_encode_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(EncodeQRStates.waiting_for_method)
    
    kb = [
        [KeyboardButton(text="base64"), KeyboardButton(text="hex")],
        [KeyboardButton(text="rot13"), KeyboardButton(text="Sentinel QR")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
    await message.reply(strings.PROMPT_ENCODE_METHOD, parse_mode='Markdown', reply_markup=keyboard)

@dp.message(EncodeQRStates.waiting_for_method)
async def process_encode_method(message: types.Message, state: FSMContext, bot: Bot):
    method = message.text
    if method == "Sentinel QR":
        await state.update_data(method=method)
        await state.set_state(EncodeQRStates.waiting_for_sentinel_password)
        await message.reply("🔒 *Security Check*\n\nPlease enter a password", parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
        return

    data = await state.get_data()
    await state.clear()
    
    status_msg = await message.reply(strings.STATUS_GENERATING, reply_markup=ReplyKeyboardRemove())
    await generate_encode_qr(message, bot, data['text'], method, status_msg)

@dp.message(EncodeQRStates.waiting_for_sentinel_password)
async def process_sentinel_password(message: types.Message, state: FSMContext, bot: Bot):
    password = message.text
    data = await state.get_data()
    await state.clear()
    
    status_msg = await message.reply(strings.STATUS_GENERATING)
    
    try:
        start_time = time.time()
        
        # Get user's custom QR style
        from database import db
        user_style = db.get_user_qr_style(message.from_user.id)
        style = None
        
        if user_style:
            from qr_generator import QRStyle, QRColor
            fg_color, bg_color = user_style
            style = QRStyle(
                fg_color=QRColor(*fg_color),
                bg_color=QRColor(*bg_color)
            )
        
        loop = asyncio.get_running_loop()
        bio = await loop.run_in_executor(bot.process_pool, qr_generator.generate_sentinel_qr, data['text'], password, style)
        
        db.record_performance(time.time() - start_time)

        input_file = BufferedInputFile(bio.getvalue(), filename="qr.png")
        await message.reply(strings.SUCCESS_GENERATE)
        await send_photo_with_retry(message, input_file)
    except Exception as e:
        logger.error(f"Error generating Sentinel QR: {e}")
        from database import db
        db.record_error("GenericError")
        await message.reply(strings.ERROR_GENERIC)
    finally:
        await status_msg.delete()

async def generate_encode_qr(message: types.Message, bot: Bot, text, method, status_msg: types.Message = None):
    if not status_msg:
        status_msg = await message.reply(strings.STATUS_GENERATING)

    try:
        start_time = time.time()
        
        # Get user's custom QR style
        from database import db
        user_style = db.get_user_qr_style(message.from_user.id)
        style = None
        
        if user_style:
            from qr_generator import QRStyle, QRColor
            fg_color, bg_color = user_style
            style = QRStyle(
                fg_color=QRColor(*fg_color),
                bg_color=QRColor(*bg_color)
            )
        
        loop = asyncio.get_running_loop()
        if method == "Sentinel QR":
            # This path is now handled by process_sentinel_password
            # But if called directly without state, we need a password.
            # However, the bot command flow ensures we go through states.
            # If `text` and `password` are provided in args? 
            # The current generate_encode_qr signature only has text and method.
            # Use generate_sentinel_qr directly instead.
            pass
        else:
            bio = await loop.run_in_executor(bot.process_pool, qr_generator.generate_encoded_qr, text, method, style)
        
        if bio is None and method != "Sentinel QR":
            await message.reply("⚠️ Invalid method! Choose: *base64*, *hex*, *rot13*, *Sentinel QR*", parse_mode='Markdown')
            return
        
        db.record_performance(time.time() - start_time)

        input_file = BufferedInputFile(bio.getvalue(), filename="qr.png")
        await message.reply(strings.SUCCESS_GENERATE)
        await send_photo_with_retry(message, input_file)
    except Exception as e:
        logger.error(f"Error generating encode QR: {e}")
        from database import db
        db.record_error("GenericError")
        await message.reply(strings.ERROR_GENERIC)
    finally:
        await status_msg.delete()

# Geo QR handlers
@dp.message(Command("geoqr"))
async def geo_qr(message: types.Message, state: FSMContext):
    """Generate Geo QR."""
    await state.set_state(GeoQRStates.waiting_for_location)
    
    kb = [[KeyboardButton(text="📍 Share Location", request_location=True)]]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
    
    await message.reply(strings.PROMPT_GEO_LOCATION, reply_markup=keyboard)

@dp.message(GeoQRStates.waiting_for_location)
async def process_geo_location(message: types.Message, state: FSMContext):
    if message.location:
        await state.update_data(latitude=message.location.latitude, longitude=message.location.longitude)
    elif message.text:
        # Try to parse text location (basic)
        try:
            lat, lon = map(float, message.text.split(','))
            await state.update_data(latitude=lat, longitude=lon)
        except ValueError:
            await message.reply("⚠️ Invalid format! Please send a location or enter coordinates (lat,lon).")
            return
    else:
        await message.reply("⚠️ Please send a location!")
        return
        
    await state.set_state(GeoQRStates.waiting_for_platform)
    
    kb = [
        [KeyboardButton(text="Google Maps"), KeyboardButton(text="Waze")],
        [KeyboardButton(text="Apple Maps"), KeyboardButton(text="Geo URI")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
    await message.reply(strings.PROMPT_GEO_PLATFORM, reply_markup=keyboard)

@dp.message(GeoQRStates.waiting_for_platform)
async def process_geo_platform(message: types.Message, state: FSMContext, bot: Bot):
    platform = message.text
    data = await state.get_data()
    await state.clear()
    
    status_msg = await message.reply(strings.STATUS_GENERATING, reply_markup=ReplyKeyboardRemove())
    await generate_geo_qr(message, bot, data['latitude'], data['longitude'], platform, status_msg)

async def generate_geo_qr(message: types.Message, bot: Bot, lat, lon, platform, status_msg: types.Message = None):
    if not status_msg:
        status_msg = await message.reply(strings.STATUS_GENERATING)

    try:
        start_time = time.time()
        
        # Get user's custom QR style
        from database import db
        user_style = db.get_user_qr_style(message.from_user.id)
        style = None
        
        if user_style:
            from qr_generator import QRStyle, QRColor
            fg_color, bg_color = user_style
            style = QRStyle(
                fg_color=QRColor(*fg_color),
                bg_color=QRColor(*bg_color)
            )
        
        loop = asyncio.get_running_loop()
        bio = await loop.run_in_executor(bot.process_pool, qr_generator.generate_geo_qr, lat, lon, platform, style)
        
        db.record_performance(time.time() - start_time)

        input_file = BufferedInputFile(bio.getvalue(), filename="qr.png")
        await message.reply(strings.SUCCESS_GENERATE)
        await send_photo_with_retry(message, input_file)
    except Exception as e:
        logger.error(f"Error generating Geo QR: {e}")
        from database import db
        db.record_error("GenericError")
        await message.reply(strings.ERROR_GENERIC)
    finally:
        await status_msg.delete()

@dp.message(Command("readerqr"))
async def qr_reader_command(message: types.Message, state: FSMContext):
    """Start QR Reader conversation."""
    await state.set_state(QRReaderStates.waiting_for_image)
    await message.reply(strings.PROMPT_UPLOAD_QR, parse_mode='Markdown')

@dp.message(QRReaderStates.waiting_for_image, F.photo | F.document)
async def process_qr_image(message: types.Message, state: FSMContext, bot: Bot):
    """Handle image upload for QR Reader."""
    await state.clear()
    await qr_reader_handler(message, bot, state)

@dp.message((F.photo | F.document) & F.caption.startswith('/readerqr'))
async def qr_reader_handler(message: types.Message, bot: Bot, state: FSMContext):
    """Handle image messages to read QR codes."""
    try:
        status_msg = await message.reply(strings.STATUS_SCANNING)

        image_file = None
        file_size = None
        if message.photo:
            image_file = message.photo[-1]
            file_size = image_file.file_size
        elif message.document:
            mime_type = message.document.mime_type or ""
            file_name = (message.document.file_name or "").lower()
            image_extensions = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".jxl")
            if not mime_type.startswith("image/") and not file_name.endswith(image_extensions):
                await message.reply(strings.ERROR_QR_READ_FAILED)
                return
            image_file = message.document
            file_size = image_file.file_size
        
        # Check file size (Limit: 5MB)
        if file_size and file_size > 5 * 1024 * 1024:
            await message.reply(strings.ERROR_FILE_TOO_LARGE)
            return

        # Download file to memory
        # In aiogram 3.x, bot.download returns a BytesIO object if destination is not specified
        # But we need to use the bot instance to download
        from io import BytesIO
        bio = BytesIO()
        await bot.download(image_file, destination=bio)
        bio.seek(0)
        
        # Read QR in a separate process
        loop = asyncio.get_running_loop()
        status, content = await loop.run_in_executor(bot.process_pool, qr_reader.read_qr, bio.read())
        
        if status == 'success':
            # Check for Sentinel QR (Old or New)
            # New format: starts with SENTINEL:
            if content.startswith("SENTINEL:"):
                # It's a password-protected Sentinel QR
                await state.set_state(QRReaderStates.waiting_for_password)
                await state.update_data(sentinel_content=content)
                await message.reply("🔒 *Sentinel QR Detected*\n\nPlease enter the password", parse_mode='Markdown')
                return
            
            # Legacy check or global key check (optional, but requested to make changes)
            # Try to decrypt with global key only if it doesn't have SENTINEL prefix (backward compat attempt)
            # But the user said "bot will ask for password". 
            # If we want to support old ones, we can try decrypting with SENTINEL_KEY if it fails password check?
            # Or just assume all Sentinel QRs now require this flow.
            # Let's check if it decodes with the old method first for backward compat silently?
            # User specifically asked for password flow.
            
            qr_type = qr_reader.detect_type(content)
            response = qr_reader.format_response(content, qr_type)
            
            # Auto-decode check
            fmt, decoded = qr_reader.try_detect_and_decode(content)
            if fmt and decoded:
                safe_fmt = html.escape(fmt)
                safe_decoded = html.escape(decoded if len(decoded) <= 1000 else decoded[:1000] + "... [truncated]")
                response += f"\n\n🔓 <b>Auto-Decoded ({safe_fmt})</b>:\n<code>{safe_decoded}</code>"
                
            await message.reply(response, parse_mode='HTML', disable_web_page_preview=True)

        elif status == 'multiple':
            await message.reply(strings.ERROR_MULTIPLE_QR)
        elif status == 'error':
            await message.reply(strings.ERROR_QR_READ_FAILED)
        else: # none
            await message.reply(strings.ERROR_NO_QR_FOUND)

    except TelegramNetworkError as e:
        logger.error(f"User:{message.from_user.id} | Network Error in qr_reader_handler: {e}")
        await message.reply("⚠️ Network error. The request timed out. Please try again.")
    except Exception as e:
        logger.error(f"User:{message.from_user.id} | Error in qr_reader_handler: {e}")
        await message.reply(strings.ERROR_GENERIC)
    finally:
        try:
            await status_msg.delete()
        except:
            pass

@dp.message(QRReaderStates.waiting_for_password)
async def process_reader_password(message: types.Message, state: FSMContext):
    """Process password for Sentinel QR."""
    password = message.text
    data = await state.get_data()
    content = data.get('sentinel_content')
    await state.clear()
    
    decrypted = qr_reader.try_decrypt_sentinel(content, password)
    
    if decrypted:
        safe_decrypted = html.escape(decrypted if len(decrypted) <= 1500 else decrypted[:1500] + "... [truncated]")
        await message.reply(
            f"🛡️ <b>Sentinel QR Detected</b>\n\n🔓 <b>Decrypted Content:</b> <code>{safe_decrypted}</code>",
            parse_mode='HTML'
        )
    else:
        await message.reply("❌ *Decryption Failed*\n\nIncorrect password or corrupted data.", parse_mode='Markdown')

async def scheduled_maintenance(bot: Bot):
    """Runs daily maintenance at configured local time (default 08:00 Asia/Kuala_Lumpur)."""
    from database import db
    while True:
        try:
            now = datetime.now(MAINTENANCE_TZ)
            report_date = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")
            last_maintenance_date = db.get_last_maintenance_date()
            current_clock = (now.hour, now.minute)
            maintenance_clock = (MAINTENANCE_HOUR, MAINTENANCE_MINUTE)

            due_now = current_clock >= maintenance_clock
            if due_now and last_maintenance_date != report_date:
                ok = await perform_maintenance(bot, report_date)
                if ok:
                    db.set_last_maintenance_date(report_date)
                    # After success, sleep until tomorrow's exact maintenance time.
                    next_run = (now + timedelta(days=1)).replace(
                        hour=MAINTENANCE_HOUR, minute=MAINTENANCE_MINUTE, second=0, microsecond=0
                    )
                    sleep_seconds = max((next_run - datetime.now(MAINTENANCE_TZ)).total_seconds(), 1)
                    await asyncio.sleep(sleep_seconds)
                    continue
                else:
                    logger.warning("Daily maintenance failed for %s; will retry.", report_date)
                    await asyncio.sleep(300)
                    continue

            # Not due yet: sleep straight to the exact maintenance time today.
            if current_clock < maintenance_clock:
                next_run = now.replace(hour=MAINTENANCE_HOUR, minute=MAINTENANCE_MINUTE, second=0, microsecond=0)
                sleep_seconds = max((next_run - now).total_seconds(), 1)
                await asyncio.sleep(sleep_seconds)
            else:
                # Already due but already completed for this report_date.
                next_run = (now + timedelta(days=1)).replace(
                    hour=MAINTENANCE_HOUR, minute=MAINTENANCE_MINUTE, second=0, microsecond=0
                )
                sleep_seconds = max((next_run - now).total_seconds(), 1)
                await asyncio.sleep(sleep_seconds)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in scheduled maintenance task: {e}")
            await asyncio.sleep(60)

async def database_flush_task():
    """Periodically flushes database to disk."""
    from database import db
    while True:
        await asyncio.sleep(5) # Save every 5 seconds
        db.flush()

async def perform_maintenance(bot: Bot, report_date: str):
    """Exports activity log to admins and clears it after a successful send."""
    from database import db
    from admin import ADMIN_IDS
    from aiogram.types import FSInputFile
    import os

    log_targets = []
    log_file = os.path.abspath(db.activity_log_file)
    if os.path.exists(log_file) and os.path.getsize(log_file) > 0:
        log_targets.append(
            (log_file, f"activity_report_{report_date}.log", f"Daily Activity Log - {report_date}")
        )

    if not ADMIN_IDS:
        if log_targets:
            logger.warning("Daily maintenance skipped: no admins configured in ADMIN_IDS or ADMIN_ID.")
            return False
        return True

    if not log_targets:
        logger.info("Daily maintenance found no log files to send.")
        return True

    for log_file, filename, caption in log_targets:
        sent_count = 0
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_document(
                    admin_id,
                    FSInputFile(log_file, filename=filename),
                    caption=caption
                )
                sent_count += 1
            except Exception as e:
                logger.error("Failed to send %s to %s: %s", log_file, admin_id, e)

        if sent_count == 0:
            return False

    for log_file, _, _ in log_targets:
        try:
            _clear_log_file(log_file)
        except Exception as e:
            logger.error("Failed to clear log file %s: %s", log_file, e)
            return False

    return True


def _clear_log_file(log_file: str):
    """Truncate a log file."""
    with open(os.path.abspath(log_file), "w", encoding="utf-8"):
        pass


# Color QR - Button-based flow
@dp.message(Command("colorqr"))
async def color_qr_command(message: types.Message, state: FSMContext):
    """Start custom QR color setup with buttons."""
    await state.set_state(ColorQRStates.waiting_for_bg_choice)
    
    kb = [
        [KeyboardButton(text="☀️ Light Mode"), KeyboardButton(text="🌙 Dark Mode")],
        [KeyboardButton(text="🎨 Custom")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
    
    await message.reply(
        "🎨 *Step 1: Choose Background*\n\n"
        "Select a background color mode:",
        parse_mode='Markdown',
        reply_markup=keyboard
    )

# Background choice handlers
@dp.message(ColorQRStates.waiting_for_bg_choice, F.text.in_(["☀️ Light Mode", "🌙 Dark Mode"]))
async def process_bg_preset(message: types.Message, state: FSMContext):
    """Handle preset background choices."""
    if message.text == "☀️ Light Mode":
        bg_color = "#FFFFFF"  # White
    else:  # Dark Mode
        bg_color = "#000000"  # Black
    
    await state.update_data(bg_color=bg_color)
    await show_fg_color_menu(message, state)

@dp.message(ColorQRStates.waiting_for_bg_choice, F.text == "🎨 Custom")
async def request_custom_bg(message: types.Message, state: FSMContext):
    """Request custom background color."""
    await state.set_state(ColorQRStates.waiting_for_bg_custom)
    await message.reply(
        "Enter custom background color in hex format:\n"
        "Example: `#FFFFFF` for white",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(ColorQRStates.waiting_for_bg_custom)
async def process_custom_bg(message: types.Message, state: FSMContext):
    """Process custom background color."""
    import re
    bg_color = message.text.strip()
    
    if not re.match(r'^#[0-9A-Fa-f]{6}$', bg_color):
        await message.reply("❌ Invalid format! Use hex like `#FFFFFF`", parse_mode='Markdown')
        return
    
    await state.update_data(bg_color=bg_color)
    await show_fg_color_menu(message, state)

async def show_fg_color_menu(message: types.Message, state: FSMContext):
    """Show foreground color selection menu."""
    await state.set_state(ColorQRStates.waiting_for_fg_choice)
    
    kb = [
        [KeyboardButton(text="🔴 Red"), KeyboardButton(text="🔵 Blue"), KeyboardButton(text="🟡 Yellow")],
        [KeyboardButton(text="🟢 Green"), KeyboardButton(text="🟠 Orange"), KeyboardButton(text="🟣 Purple")],
        [KeyboardButton(text="🩷 Pink"), KeyboardButton(text="🟤 Brown"), KeyboardButton(text="⚫ Black")],
        [KeyboardButton(text="⚪ White"), KeyboardButton(text="⚪ Grey"), KeyboardButton(text="🎨 Custom")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
    
    data = await state.get_data()
    await message.reply(
        f"✅ Background: `{data['bg_color']}`\n\n"
        "🎨 *Step 2: Choose Foreground*\n\n"
        "Select the QR code module color:",
        parse_mode='Markdown',
        reply_markup=keyboard
    )

# Foreground color mapping
FG_COLORS = {
    "🔴 Red": "#FF0000",
    "🔵 Blue": "#0000FF",
    "🟡 Yellow": "#FFFF00",
    "🟢 Green": "#00FF00",
    "🟠 Orange": "#FFA500",
    "🟣 Purple": "#800080",
    "🩷 Pink": "#FFC0CB",
    "🟤 Brown": "#A52A2A",
    "⚫ Black": "#000000",
    "⚪ White": "#FFFFFF",
    "⚪ Grey": "#808080"
}

@dp.message(ColorQRStates.waiting_for_fg_choice, F.text.in_(list(FG_COLORS.keys())))
async def process_fg_preset(message: types.Message, state: FSMContext):
    """Handle preset foreground choices."""
    fg_color = FG_COLORS[message.text]
    await state.update_data(fg_color=fg_color)
    await show_confirmation(message, state)

@dp.message(ColorQRStates.waiting_for_fg_choice, F.text == "🎨 Custom")
async def request_custom_fg(message: types.Message, state: FSMContext):
    """Request custom foreground color."""
    await state.set_state(ColorQRStates.waiting_for_fg_custom)
    await message.reply(
        "Enter custom foreground color in hex format:\n"
        "Example: `#000000` for black",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(ColorQRStates.waiting_for_fg_custom)
async def process_custom_fg(message: types.Message, state: FSMContext):
    """Process custom foreground color."""
    import re
    fg_color = message.text.strip()
    
    if not re.match(r'^#[0-9A-Fa-f]{6}$', fg_color):
        await message.reply("❌ Invalid format! Use hex like `#000000`", parse_mode='Markdown')
        return
    
    await state.update_data(fg_color=fg_color)
    await show_confirmation(message, state)

async def show_confirmation(message: types.Message, state: FSMContext):
    """Show confirmation screen."""
    await state.set_state(ColorQRStates.waiting_for_confirmation)
    data = await state.get_data()
    
    kb = [
        [KeyboardButton(text="✅ Confirm"), KeyboardButton(text="❌ Cancel")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
    
    await message.reply(
        f"🎨 *Step 3: Confirm Your Colors*\n\n"
        f"• Background: `{data['bg_color']}`\n"
        f"• Foreground: `{data['fg_color']}`\n\n"
        "Save these colors for all your QR codes?",
        parse_mode='Markdown',
        reply_markup=keyboard
    )

@dp.message(ColorQRStates.waiting_for_confirmation, F.text == "✅ Confirm")
async def confirm_colors(message: types.Message, state: FSMContext, bot: Bot):
    """Save colors and show preview."""
    data = await state.get_data()
    await state.clear()
    
    from database import db
    
    # Parse hex to RGB
    fg_hex = data['fg_color'].lstrip('#')
    bg_hex = data['bg_color'].lstrip('#')
    
    fg_rgb = tuple(int(fg_hex[i:i+2], 16) for i in (0, 2, 4))
    bg_rgb = tuple(int(bg_hex[i:i+2], 16) for i in (0, 2, 4))
    
    # Save to database
    db.set_user_qr_style(message.from_user.id, fg_rgb, bg_rgb)
    
    await message.reply(
        f"✅ *Colors Saved!*\n\n"
        f"• Background: `{data['bg_color']}`\n"
        f"• Foreground: `{data['fg_color']}`\n\n"
        "Generating preview...",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Generate preview QR
    try:
        from qr_generator import QRStyle, QRColor
        
        style = QRStyle(
            fg_color=QRColor(*fg_rgb),
            bg_color=QRColor(*bg_rgb)
        )
        
        loop = asyncio.get_running_loop()
        qr_bio = await loop.run_in_executor(bot.process_pool, qr_generator.generate_qr, "Preview QR Code", style)
        
        await send_photo_with_retry(
            message,
            photo=BufferedInputFile(qr_bio.getvalue(), filename="preview_qr.png")
        )
        await message.reply(
            "👆 Preview of your custom QR style!\n\n"
            "All future QR codes will use these colors.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        await message.reply("Preview generation failed, but colors are saved!")

@dp.message(ColorQRStates.waiting_for_confirmation, F.text == "❌ Cancel")
async def cancel_colors(message: types.Message, state: FSMContext):
    """Cancel color customization."""
    await state.clear()
    await message.reply(
        "❌ Cancelled. Your previous settings remain unchanged.",
        reply_markup=ReplyKeyboardRemove()
    )



# Temporary command for verification


def warmup_task():
    """
    Dummy task for process pool warmup.
    Forces loading of heavy libraries (PIL, qrcode) in the worker process.
    """
    try:
        import qr_generator
        # Generate a small QR to force imports
        qr_generator.generate_qr("warmup")
    except Exception as e:
        logger.warning("Worker warmup failed: %s", e)

async def main() -> None:
    """Start the bot."""
    if not TOKEN or TOKEN == "your_telegram_bot_token_here":
        print("Error: TELEGRAM_BOT_TOKEN not found in .env file.")
        return

# Increase session timeout to handle slow connections/uploads
# Configure TCPConnector for better stability
import aiohttp
from aiogram.client.session.aiohttp import AiohttpSession

class CustomAiohttpSession(AiohttpSession):
    def __init__(self, connector: aiohttp.TCPConnector = None, **kwargs):
        super().__init__(**kwargs)
        self._connector = connector

    async def create_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                json_serialize=self.json_dumps,
            )
        return self._session


async def main() -> None:
    """Start the bot."""
    if not TOKEN or TOKEN == "your_telegram_bot_token_here":
        print("Error: TELEGRAM_BOT_TOKEN not found in .env file.")
        return

    # Initialize Bot
    connector = aiohttp.TCPConnector(
        limit=100, 
        limit_per_host=20, 
        enable_cleanup_closed=True
    )
    session = CustomAiohttpSession(timeout=120.0, connector=connector)
    bot = Bot(token=TOKEN, session=session)

    # Start background tasks
    asyncio.create_task(scheduled_maintenance(bot)) 
    
    # Start database flush task
    asyncio.create_task(database_flush_task())
    
    # Initialize ProcessPoolExecutor for CPU-bound tasks
    from concurrent.futures import ProcessPoolExecutor
    process_pool = ProcessPoolExecutor()
    
    # Attach pool to bot instance for easy access (monkey-patching for convenience)
    bot.process_pool = process_pool
    
    # Warmup: Submit a dummy task to start a worker process immediately
    # This reduces latency for the first user request
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(process_pool, warmup_task)
    
    # Initialize Notifications
    notifications.notify = notifications.NotificationManager(bot)

    try:
        # Set bot commands
        commands = [
            BotCommand(command="start", description="Start & bot info"),
            BotCommand(command="help", description="View full command list"),
            BotCommand(command="textqr", description="Text to QR code"),
            BotCommand(command="urlqr", description="URL to QR code"),
            BotCommand(command="wifiqr", description="WiFi to QR code"),
            BotCommand(command="vcardqr", description="Contact to QR code"),
            BotCommand(command="geoqr", description="Location to QR code"),
            BotCommand(command="encodeqr", description="Encoded text to QR code"),
            BotCommand(command="readerqr", description="Scan QR from image"),
            BotCommand(command="colorqr", description="Custom QR colors"),
            BotCommand(command="about", description="Bot & developer info")
        ]
        await bot.set_my_commands(commands)

        # Start polling
        await dp.start_polling(bot)
    finally:
        from database import db
        db.flush()
        process_pool.shutdown(wait=True)
        notifications.notify = None

if __name__ == "__main__":
    asyncio.run(main())

