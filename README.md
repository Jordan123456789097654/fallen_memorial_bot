# 🛡️ Fallen Officer Memorial Intelligence System

A multi-server, production-ready Python application for emergency responder line-of-duty death monitoring, AI intelligence processing, Discord memorial broadcasts, and an interactive **Public Web Memorial Wall**.

Built with **FastAPI**, **discord.py 2.x**, **SQLAlchemy (SQLite)**, **APScheduler**, and **Google Gemini AI**, ready for **Render.com** deployment with **Persistent Disk Storage**.

---

## 🌐 1. Public Web Memorial Wall & Dashboard (`/wall`)

FastAPI hosts an interactive, high-aesthetic single-page dashboard at `http://localhost:8000/` or `https://your-app.onrender.com/wall`:

- **Glassmorphism Dark Theme:** Responsive UI showcasing memorial cards for fallen emergency responders.
- **Sequential Memorial IDs:** `#1`, `#2`, `#3`... tags displayed on every card.
- **Category Filtering & Search:** Real-time search by responder name, agency, or state, with category tabs (`LAW ENFORCEMENT`, `FIRE`, `EMS`, `RESCUE`, `K9`, `DISPATCH`).
- **🕯️ Virtual Memorial Candles:** Visitors can click `"Light Candle"` on any memorial page, incrementing real-time candle counters.
- **💬 Respectful Condolence Board:** Visitors can write and post public messages of tribute directly onto a responder's memorial page.

---

## 🎛️ 2. Discord Interactive Component Buttons & Modals

Draft review embeds in `#bot-logs` feature interactive Discord buttons (`discord.ui.View`):
- `[ ✅ Approve ]` — Instant green approval button that posts memorial embeds to category channels.
- `[ ❌ Reject ]` — Instant red rejection button.
- `[ ✏️ Edit Draft ]` — Blue button launching a **Discord Pop-up Modal** (`discord.ui.Modal`) where admins edit Name, Agency, Date of Death, and Summary in real-time.
- `[ 🔄 Regenerate AI ]` — Grey button that re-triggers Gemini AI to generate a fresh scripture and memorial draft.

---

## 📅 3. Annual EOW Anniversary Reminders

The background scheduler runs a daily anniversary check at 00:00 UTC:
- Automatically scans database records matching today's month & day.
- Posts solemn anniversary tributes (*"1 Year Ago Today"*, *"5 Years Ago Today"*) to category channels and `#memorial-archive`.

---

## 🐾 4. Specialized K9 & Support Unit Enhancements

Specialized tracking fields for K9 heroes:
- **Handler Name**
- **Canine Breed**
- **Service Years**
- **Unit Badge Number**
- Visual K9 badges displayed on Discord Embeds and the Web Memorial Wall.

---

## 🌐 Deploying on Render.com

1. Push repository code to GitHub.
2. Go to [Render Dashboard](https://dashboard.render.com/) → **New +** → **Blueprint** → Select repo.
3. Configure environment variables in Render:
   - `DISCORD_BOT_TOKEN`: Discord Bot token.
   - `GEMINI_API_KEY`: Google Gemini API key.
   - `API_KEY`: Secret admin API key.
4. Render mounts a 1GB **Persistent Disk** at `/var/data/memorials.db` automatically via `render.yaml`.

---

## 📜 License
Released under the MIT License for honor and solemn remembrance of emergency responders who gave the ultimate sacrifice.
