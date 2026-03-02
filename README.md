# QRBot

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Aiogram](https://img.shields.io/badge/Aiogram-Framework-26A5E4?logo=telegram&logoColor=white)
![qrcode](https://img.shields.io/badge/qrcode-Generator-4B8BBE?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen.svg)

<div align="center">
  <img src="preview.png" alt="QRBot Preview" width="200">
</div>

🔗 **Try it live:** [**@PautQRBot**](https://t.me/PautQRBot) · 📺 **Video tutorial:** [**Watch on YouTube**](https://www.youtube.com/watch?v=uJM2nCFWCx4)

A versatile Telegram bot for generating and reading QR codes. Built with Python and `Aiogram`, it supports multiple QR formats, custom colour styling, and password-protected encrypted QR codes.

> [!NOTE]
> **Privacy First**: QRBot processes all data in-memory and does not store generated QR codes or scanned images on the server.

## Features

- 🚀 **QR Generation**: Create QR codes for Text, URL, WiFi credentials, vCard contacts, Geo coordinates, and encoded data (Base64, Hex, ROT13).
- 🔒 **Sentinel QR**: Password-protected, encrypted QR codes for secure data sharing.
- 👁️ **QR Reader**: Decode any QR code from an image sent directly to the bot.
- 🎨 **Customisation**: Choose custom foreground/background colours, or use Light and Dark mode presets.
- 🛠️ **Admin Tools**: Broadcast messages, view user stats, manage bans, and monitor system health.

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/zis3c/QRBot.git
   cd QRBot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**

   Obtain a bot token from [@BotFather](https://t.me/BotFather) and set it as an environment variable:
   ```bash
   export TELEGRAM_BOT_TOKEN=your_token_here
   # Windows: set TELEGRAM_BOT_TOKEN=your_token_here
   ```

4. **Run the bot**
   ```bash
   python bot.py
   ```

For detailed setup instructions on Windows, Linux, macOS, and Docker, see the **[Installation Guide](INSTALLATION.md)**.

### Deploy to Render

This project includes a `render.yaml` for one-click deployment on [Render](https://render.com):

1. Link your forked repository to Render.
2. Add `TELEGRAM_BOT_TOKEN` and `ADMIN_IDS` in the Render dashboard under **Environment**.
3. Deploy. The built-in keep-alive server prevents the instance from sleeping.

## Project Structure

```
QRBot/
├── bot.py               # Main bot logic and command handlers
├── admin.py             # Admin tools and management commands
├── database.py          # Database operations
├── middlewares.py       # Aiogram middlewares
├── notifications.py     # Notification system
├── qr_generator.py      # QR code generation logic
├── qr_reader.py         # QR code scanning and decoding logic
├── states.py            # FSM states for multi-step conversations
├── strings.py           # Bot text and string constants
├── render.yaml          # Render deployment configuration
├── requirements.txt     # Python dependencies
├── Dockerfile           # Docker setup
├── INSTALLATION.md      # Detailed installation guide
├── CONTRIBUTING.md      # Contribution guidelines
└── README.md            # Project documentation
```

## Commands

| Command | Description |
|:--------|:------------|
| `/start` | Start the bot and view info |
| `/help` | View the full command list |
| `/textqr` | Convert text to a QR code |
| `/urlqr` | Convert a URL to a QR code |
| `/wifiqr` | Create a WiFi login QR code |
| `/vcardqr` | Create a contact (vCard) QR code |
| `/geoqr` | Create a location QR code |
| `/encodeqr` | Create an encoded QR (Base64 / Hex / Sentinel) |
| `/readerqr` | Start QR Reader mode |
| `/colorqr` | Customise QR code colours |

### Admin Commands
*Visible only to admins defined in `ADMIN_IDS`.*

| Command | Description |
|:--------|:------------|
| `/admin` | Show admin help |
| `/stats` | View system statistics |
| `/broadcast` | Send a message to all users |
| `/ban <user_id>` | Ban a user |
| `/unban <user_id>` | Unban a user |
| `/logs` | Retrieve log files |

## How It Works

1. **Authentication**: The bot connects to Telegram using a token issued by [@BotFather](https://t.me/BotFather) via the Aiogram framework.
2. **Command Routing**: Incoming messages are matched to handlers by command or FSM state, enabling multi-step conversations.
3. **QR Generation**: `qr_generator.py` encodes the user's input into the selected QR format, applies colour options, and renders the image in-memory.
4. **Sentinel Encryption**: For Sentinel QR, the payload is AES-encrypted with the user's password before encoding; the key is never stored.
5. **QR Reading**: Images sent to the bot are passed to `qr_reader.py`, which decodes and returns the embedded data.
6. **Admin Layer**: Admin commands are protected by a middleware that checks the sender's ID against `ADMIN_IDS` before execution.

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
