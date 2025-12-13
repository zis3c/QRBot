# English Strings for QRBot

WELCOME_MSG = """
Welcome to *QRBot*! 🤖✨
Use the commands below to start:

/textqr - Text to QR code
/urlqr - URL to QR code
/wifiqr - WiFi to QR code
/vcardqr - Contact to QR code
/geoqr - Location to QR code
/encodeqr - Encoded text to QR code
/readerqr - Scan QR from image
/colorqr - QR color customization
/help - View full command list

Try it now! 🚀
"""

HELP_MSG = """
📋 *QRBot Command List*

*Basic*
/start - Start & bot info
/help - List of commands
/about - Bot & developer info

*Generate QR*
/textqr - Text to QR code
/urlqr - URL to QR code
/wifiqr - WiFi to QR code
/vcardqr - Contact to QR code
/geoqr - Location to QR code
/encodeqr - Encoded text to QR code

*QR Reader*
/readerqr - QR code to text

*QR Custom*
/colorqr - QR color customization
/patternqr - Not coming soon!
/logoqr - Not coming soon!
"""

ABOUT_MSG = """
🤖 *About QRBot*\n
Dev: Radzi Zamri
Version: 1.0.0

This bot is built to make generating QR codes easy for you.
"""


ERROR_GENERIC = "⚠️ Something went wrong. Please try again later."
SUCCESS_GENERATE = "✅ Done! Here is your QR code:"

# Validation Errors
ERROR_TEXT_TOO_LONG = "⚠️ Text is too long! Please keep it under 1000 characters."
ERROR_INVALID_PHONE = "⚠️ Invalid phone number! Use digits and optional '+' prefix."
ERROR_INVALID_EMAIL = "⚠️ Invalid email address!"
ERROR_QR_GENERATION = "⚠️ Failed to generate QR code. Please try again."

# QR Reader Strings
QR_READER_INSTRUCTION = "Send an image with the caption /readerqr to scan it."
ERROR_NO_QR_FOUND = "⚠️ No QR code detected.\nPlease send a clear image of a single QR code."
ERROR_QR_READ_FAILED = "⚠️ Failed to read the image. Please try again."

# Cooldown & Security
ERROR_COOLDOWN = "⚠️ Please wait {seconds} seconds before sending another command."
ERROR_PENALTY = "⛔ You are sending commands too fast! You have been temporarily blocked for 60 seconds."
ERROR_BANNED = "⛔ You are banned from using this bot."
ERROR_FILE_TOO_LARGE = "⚠️ File is too large! Maximum size is 5MB."

# Admin
ADMIN_HELP = """
🛡️ *Admin Commands*

/system - View system status
/stats - View statistics
/broadcast - Send message to all users
/logs - Download bot log file
/ban - Ban a user by ID
/unban - Unban a user by ID
/penalties - List active penalties
/unpenalty - Remove penalty from user
"""
ADMIN_BAN_SUCCESS = "✅ User {user_id} has been banned."
ADMIN_UNBAN_SUCCESS = "✅ User {user_id} has been unbanned."
ADMIN_BROADCAST_CONFIRM = "⚠️ You are about to send this message to {count} users:\n\n\"{text}\"\n\nType /confirm to proceed or /cancel to abort."
ADMIN_BROADCAST_CANCEL = "❌ Broadcast cancelled."
ADMIN_BROADCAST_SUCCESS = "✅ Broadcast sent to {count} users."
ADMIN_NO_BROADCAST = "⚠️ No broadcast pending."

ERROR_QR_TOO_LONG = "⚠️ Data too long for QR code. Please shorten your text."
ERROR_QR_BLURRY = "⚠️ Could not detect QR code. The image might be too blurry or low contrast. Please try again with better lighting."
ADMIN_ONLY = "⚠️ This command is for admins only."

# Status & Feedback
STATUS_GENERATING = "⏳ Generating QR code..."
STATUS_SCANNING = "🔍 Scanning QR code..."
ERROR_MULTIPLE_QR = "⚠️ Multiple QR codes detected! Please crop the image to show only one QR code."
ERROR_QR_LOW_QUALITY = "⚠️ QR code detected but could not be decoded. Try a clearer image or better lighting."

# Conversational Prompts
PROMPT_TEXT_QR = "What is the text you want to convert to QR?"
PROMPT_URL_QR = "What is the URL you want to convert?"
PROMPT_WIFI_SSID = "What is the WiFi Name (SSID)?"
PROMPT_WIFI_PASSWORD = "What is the WiFi Password?"
PROMPT_WIFI_AUTH = "What is the Security Type? (WPA, WEP, or nopass)"
PROMPT_VCARD_NAME = "What is the Contact Name?"
PROMPT_VCARD_PHONE = "What is the Phone Number?"
PROMPT_VCARD_EMAIL = "What is the Email Address?"
PROMPT_ENCODE_TEXT = "What is the text you want to encode?"
PROMPT_ENCODE_METHOD = "What encoding method do you want to use?"
PROMPT_BROADCAST_MESSAGE = "What message would you like to broadcast?"
PROMPT_BAN_USER_ID = "Who do you want to ban? (Enter User ID)"
PROMPT_UNBAN_USER_ID = "Who do you want to unban? (Enter User ID)"
PROMPT_UNPENALTY_USER_ID = "Who do you want to remove penalty from? (Enter User ID)"
PROMPT_GEO_LOCATION = "📍 Please share your location so I can generate a navigation QR code."
PROMPT_GEO_PLATFORM = "🗺️ Choose a map platform for navigation:"
ERROR_INVALID_PLATFORM = "⚠️ Invalid platform! Please choose: *Google Maps*, *Waze*, or *Apple Maps*"
PROMPT_UPLOAD_QR = "📸 Please upload the QR code image you want to scan."
SENTINEL_DETECTED = "🛡️ *Sentinel QR Detected*\n\n🔓 *Decrypted Content:* {content}"



