# 🛡️ Fallen Officer Memorial Intelligence System

A multi-server, production-ready Python application for emergency responder line-of-duty death monitoring, AI intelligence processing, Discord memorial broadcasts, public webhook notifications, social media publishing, staff web admin portal, and an interactive **Public Web Memorial Wall**.

Built with **FastAPI**, **discord.py 2.x**, **SQLAlchemy (SQLite / PostgreSQL)**, **APScheduler**, and **Google Gemini AI**, ready to host on **Render.com Web Service Free Tier**.

---

## 📋 Complete Installation & Setup Guide

### 1. Prerequisites
- **Python 3.12+**
- **Discord Bot Token** with `Bot` intent (`message_content`, `guilds`) and Administrator permissions on your target Discord server(s).
- **Google Gemini API Key** (Free from [Google AI Studio](https://aistudio.google.com/)).

---

### 2. Local Installation & Configuration

#### Step 1: Clone Repository & Create Virtual Environment
```bash
# Clone repository
git clone https://github.com/your-username/fallen_officer_memorial.git
cd fallen_officer_memorial

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

#### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

#### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit your `.env` file:
```env
# Discord Configuration
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DISCORD_GUILD_ID=123456789012345678

# AI Configuration (Google Gemini API)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash

# Staff Web Admin Dashboard Password
STAFF_ADMIN_PASSWORD=memorial_staff_2026

# Backend & Security Settings
API_KEY=memorial_secret_admin_key_2026
DATABASE_URL=sqlite:///./memorials.db
APPROVAL_MODE=MANUAL
SCAN_INTERVAL_HOURS=3
```

#### Step 4: Launch Application
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
- **Web Memorial Wall:** `http://localhost:8000/` or `http://localhost:8000/wall`
- **Staff Admin Dashboard:** `http://localhost:8000/admin`
- **FastAPI Interactive Docs:** `http://localhost:8000/docs`

---

## ⚡ 3. Automated 5-Minute Self-Ping Keep-Alive Worker

The application includes an automated background job (`self_ping_keep_alive()`) running every 5 minutes in APScheduler:
- Pings `GET /healthz` every 5 minutes.
- Prevents free-tier cloud platforms (e.g. **Render Web Services**) from spinning down or sleeping due to inactivity.

---

## 🌐 4. Free Deployment on Render.com (Web Service)

This application is optimized for **Render's Free Web Service Tier** (no paid blueprints required).

1. **Push Code to GitHub:** Push your repository to GitHub.
2. **Create New Web Service:**
   - Go to [Render Dashboard](https://dashboard.render.com/) → **New +** → **Web Service**.
   - Connect your GitHub repository.
3. **Configure Build & Start Commands:**
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/healthz`
4. **Set Environment Variables in Render:**
   - Add `DISCORD_BOT_TOKEN`, `GEMINI_API_KEY`, `API_KEY`, `STAFF_ADMIN_PASSWORD`.
5. **Click Create Web Service!** Render will deploy your application for free.

---

## 💻 5. Staff Web Admin Dashboard (`/admin`)

Access `https://your-app.onrender.com/admin` to access the Staff Admin Portal:

1. **Staff Password Authentication:** Enter `STAFF_ADMIN_PASSWORD` (default: `memorial_staff_2026`).
2. **Pending Review Queue:** One-click **Approve**, **Reject**, and **Edit** buttons directly from your browser.
3. **Manual Scanner Trigger:** Click **Trigger Manual News Scan** to launch background scraper runs instantly.
4. **Maintenance Mode:** Click **Toggle Maintenance Mode** to display a dignified maintenance message on `/wall` while keeping `/admin` accessible.

---

## 🤖 6. Server Administration & Admin Role Restrictions

Server owners can configure command access per server:
- `/config admin_role <role>` — Set a designated Admin Role required to execute management commands (`/approve`, `/reject`, `/edit`, `/scan`, `/test_embed`, `/setstatus`).
- `/config bot_nickname <name>` — Customize the bot's server nickname per guild.

---

## 📜 License
Released under the MIT License for honor and solemn remembrance of emergency responders who gave the ultimate sacrifice.
