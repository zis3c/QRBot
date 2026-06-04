# Installation Guide 🛠️

This guide provides detailed instructions on how to set up, configure, and deploy QRBot.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Installation](#local-installation)
    - [Windows](#windows)
    - [Linux (Ubuntu/Debian)](#linux-ubuntudebian)
    - [macOS](#macos)
- [Configuration](#configuration)
- [Docker Deployment](#docker-deployment)

---

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.9** or higher
- **Git**
- A Telegram account and a **Bot Token** (Get one from [@BotFather](https://t.me/BotFather))
- **libzbar**: Required for reading QR codes (see OS-specific instructions below).

---

## Local Installation

### Windows

1.  **Clone the Repository**
    ```powershell
    git clone https://github.com/zis3c/QRBot.git
    cd QRBot
    ```

2.  **Create a Virtual Environment** (Recommended)
    ```powershell
    python -m venv venv
    .\venv\Scripts\Activate
    ```

3.  **Install Dependencies**
    ```powershell
    pip install -r requirements.txt
    ```
    *Note: On Windows, the `pyzbar` library usually includes the necessary DLLs. If you encounter errors, you may need to install the [Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170).*

4.  **Configure Environment**
    See the [Configuration](#configuration) section.

5.  **Run the Bot**
    ```powershell
    python bot.py
    ```

### Linux (Ubuntu/Debian)

1.  **Install System Dependencies**
    ```bash
    sudo apt-get update
    sudo apt-get install libzbar0
    ```

2.  **Clone and Setup**
    ```bash
    git clone https://github.com/zis3c/QRBot.git
    cd QRBot
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Run**
    ```bash
    python bot.py
    ```

### macOS

1.  **Install zbar via Homebrew**
    ```bash
    brew install zbar
    ```

2.  **Clone and Setup**
    ```bash
    git clone https://github.com/zis3c/QRBot.git
    cd QRBot
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

---

## Configuration

QRBot uses environment variables for configuration. You can set these in your terminal or use a `.env` file (if you install `python-dotenv`).

### Required Variables

| Variable | Description |
| :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Your Telegram Bot API Token obtained from @BotFather. |

### Optional Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `ADMIN_IDS` | Comma-separated list of Telegram User IDs for admin access. | `None` |

### Setting up .env (Local Development)

1.  Create a file named `.env` in the root directory.
2.  Add your variables:
    ```env
    TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIjkLmnOpQrStUvWxYz
    ADMIN_IDS=12345678,87654321
    ```

---

## Docker Deployment

Docker is the easiest way to run QRBot in a consistent environment.

1.  **Build the Image**
    ```bash
    docker build -t qrbot .
    ```

2.  **Run the Container**
    ```bash
    docker run -d \
      -e TELEGRAM_BOT_TOKEN="your_token_here" \
      -e ADMIN_IDS="12345678" \
      --name qrbot_instance \
      qrbot
    ```

---

