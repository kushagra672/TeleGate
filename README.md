<div align="center">

# 🚀 TeleGate (TeleGate & Auto-Accept Bot)

**Next-Gen Telegram Channel Join Request Manager, Automated Conversion Funnel & 2-Way Live Chat Proxy**

[![Python Version](https://img.shields.io/badge/Python-3.10%20%7C%203.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Pyrogram](https://img.shields.io/badge/Pyrogram-v2.0-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://docs.pyrogram.org/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Motor%20Async-47A248?style=for-the-badge&logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![APScheduler](https://img.shields.io/badge/APScheduler-AsyncIO-FF6F00?style=for-the-badge)](https://apscheduler.readthedocs.io/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

---

</div>

## 📖 Overview

**TeleGate** is a high-performance, asynchronous Telegram automation bot built for channel administrators, community managers, and digital marketers. It transforms Telegram channel join requests into an interactive customer onboarding pipeline.

Rather than letting channel join requests sit idle or approving them without interaction, **TeleGate** automatically approves requests, immediately initiates a personalized onboarding funnel, schedules re-engagement follow-ups, and bridges private communication between subscribers and your admin team through an intelligent 2-way live chat proxy.

---

## ✨ Key Features

### ⚡ 1. Intelligent Join Request Management
- **Auto-Approval**: Automatically approves incoming channel join requests in real time.
- **Configurable Delay**: Set an artificial delay (e.g., 0s instant or custom seconds) to simulate organic approvals.
- **Batch Processing**: Instant "Accept All Pending" tool within the admin dashboard.
- **Dynamic Welcome Sequence**: Sends customized rich media templates immediately upon approval.

### 🎯 2. State-Driven Conversion Funnel
- **State Machine Architecture**: Tracks each user through distinct journey stages:
  - `NEW_USER` → `WAITING_FOR_YES` → `WAITING_FOR_REGISTRATION` → `WAITING_FOR_DEPOSIT_PROOF` → `LIVE_CHAT` → `COMPLETED`
- **Automated Inactivity Nudges**: Automatically schedules follow-up reminders at **10 minutes**, **30 minutes**, and **60 minutes** if a user drops off before completing the funnel.
- **Crash Resilience**: On startup, the bot inspects MongoDB and automatically reschedules pending follow-up jobs for users whose timers were interrupted.
- **Dual Language Engine**: Native multilingual support (**English** & **Hindi**) with automated per-user language preference caching.

### 💬 3. Two-Way Admin Live Chat Proxy
- **Unified Support Hub**: Directs user messages, inquiries, screenshots, and proofs to an admin chat/group.
- **User Identification**: Every forwarded message is tagged with user details and a clickable `#id<USER_ID>` identifier.
- **Direct Reply Routing**: Admins simply reply to any forwarded message in the admin group; the bot intercepts the reply and seamlessly delivers it to the user's private chat.

### 🎛️ 4. Dynamic Admin Control Panel (`/admin`)
- **Interactive Inline UI**: Full administration directly inside Telegram without needing web dashboards.
- **Live Funnel Analytics**: Real-time stats on Total Users, Approved, Pending, Started, Dropped, and state distributions.
- **Zero-Code Template Manager**: Store and update promotional, welcome, and hack/signal messages directly from a private Telegram Template Channel.
- **Button Styler & Emoji Customizer**: Customize inline buttons with custom color styles (`Primary Blue`, `Success Green`, `Danger Red`, `Default Gray`) and automatically extract Telegram Premium custom emoji IDs.
- **Mass Broadcast System**: Broadcast rich text and media to all registered users with live progress indicators.

---

## 🏗️ Architecture & User Flow

```mermaid
flowchart TD
    User([Telegram User]) -->|Sends Join Request| Channel[Private Telegram Channel]
    Channel -->|Trigger Event| Bot[TeleGate Bot]
    
    subgraph Core Engine
        Bot -->|Approve Request| Channel
        Bot -->|Record / Update| DB[(MongoDB Async Motor)]
        Bot -->|Schedule Nudges 10m/30m/60m| Sched[APScheduler AsyncIO]
        Bot -->|Fetch Message Templates| TplChan[Template Channel]
    end

    Bot -->|Send Welcome & Funnel Steps| User
    User -->|Sends Messages / Screenshots / Proof| Bot
    Bot -->|Proxy Forward with #id| AdminGroup[Admin Support Group]
    AdminGroup -->|Admin Replies to Message| Bot
    Bot -->|Deliver Response| User
```

---

## 📁 Repository Structure

```text
.
├── bot.py                  # Core bot application (Pyrogram, Handlers, Funnel, Admin)
├── requirements.txt        # Python package dependencies
├── Dockerfile              # Docker container definition
├── docker-compose.yml      # Multi-container / Docker deployment specification
├── .dockerignore           # Excludes local caches & secrets from Docker builds
├── .gitignore              # Protects sensitive files (.env, sessions, caches)
├── .env.example            # Sample environment configuration template
└── README.md               # Project documentation
```

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

| Variable | Required | Description | Example |
| :--- | :---: | :--- | :--- |
| `API_ID` | **Yes** | Telegram App API ID from [my.telegram.org](https://my.telegram.org) | `12345678` |
| `API_HASH` | **Yes** | Telegram App API Hash from [my.telegram.org](https://my.telegram.org) | `0123456789abcdef0123456789abcdef` |
| `BOT_TOKEN` | **Yes** | Bot token obtained from [@BotFather](https://t.me/BotFather) | `1234567890:ABCdefGHIjkl...` |
| `MONGO_URI` | **Yes** | MongoDB connection string | `mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true` |
| `ADMIN_CHAT_ID` | **Yes** | Chat/Group ID where user messages & support are routed | `-1001234567890` |
| `ADMIN_IDS` | **Yes** | Telegram User ID(s) authorized to use `/admin` (comma-separated) | `123456789,987654321` |
| `CHANNEL_ID` | **Yes** | Channel ID where join requests are managed | `-1001234567890` |
| `TEMPLATE_CHANNEL_ID` | **Yes** | Private channel ID where message templates are stored | `-1009876543210` |
| `STRING_SESSION` | *No* | Pyrogram v2 string session for userbot / premium emojis | `BQAU...` |
| `EMOJI_*` | *No* | Optional custom emoji IDs for buttons (`EMOJI_VIP`, etc.) | `5368324170671202286` |

---

## 🚀 Installation & Deployment

### Method 1: Local Installation (Python Virtual Environment)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/TeleGate.git
   cd TeleGate
   ```

2. **Create and activate a virtual environment**:
   - **Linux / macOS**:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```

3. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your favorite editor
   ```

5. **Start the bot**:
   ```bash
   python bot.py
   ```

---

### Method 2: Docker & Docker Compose (Recommended for Production)

1. **Ensure Docker and Docker Compose are installed**.
2. **Setup your `.env` file**:
   ```bash
   cp .env.example .env
   nano .env
   ```
3. **Build and start the container in detached mode**:
   ```bash
   docker compose up -d --build
   ```
4. **Monitor logs**:
   ```bash
   docker compose logs -f
   ```
5. **Stop the container**:
   ```bash
   docker compose down
   ```

---

## 🔧 Telegram Bot Configuration Checklist

1. **BotFather Setup**:
   - Create your bot via [@BotFather](https://t.me/BotFather) and obtain the `BOT_TOKEN`.
   - Disable group privacy mode (`/setprivacy` → **Disable**) so the bot can read replies in the admin group.
2. **Target Channel Setup**:
   - Add your bot as an **Administrator** in your target channel (`CHANNEL_ID`).
   - Grant the bot **Invite Users via Links** / **Approve Join Requests** permissions.
3. **Template Channel Setup**:
   - Create a private channel (`TEMPLATE_CHANNEL_ID`) and add your bot as an Administrator.
   - Forward your template media, marketing banners, and instructional messages here.
4. **Admin Support Group**:
   - Create a group for your administrative / support team (`ADMIN_CHAT_ID`).
   - Add the bot to the group so incoming user messages and proof submissions can be routed.

---

## 🛡️ Admin Commands Reference

| Command | Allowed Users | Description |
| :--- | :---: | :--- |
| `/admin` | Configured `ADMIN_IDS` | Opens the full interactive control panel and settings |
| `/start` | All Users | Initiates onboarding flow or selects language |
| `/stats` | Configured `ADMIN_IDS` | Displays real-time user metrics & conversion counts |

---

## 🔒 Security Best Practices

- **Never commit `.env`**: Always ensure `.env` is listed in your `.gitignore`.
- **String Session Security**: Never share Pyrogram `STRING_SESSION` keys publicly, as they provide full user account access.
- **MongoDB IP Whitelist**: In MongoDB Atlas, restrict network access to your server's static IP or secure VPC.

---

## 📄 License

This project is open-source and distributed under the [MIT License](LICENSE).
