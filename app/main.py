"""
Main FastAPI Application Entrypoint.
Concurrently hosts REST API, Web Memorial Wall, Leaflet Map, RSS Feed (/feed.xml), PDF Certificates, Family Claims, ODMP/NLEOMF Registry Verification, and discord.py Bot.
"""
import io
import csv
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, Response, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import init_db, get_db, SessionLocal
from app.models import ResponderRecord, ApprovalStatus, GuildConfig, ResponderCategory, Condolence, WebhookSubscription, CandleLog, FamilyClaim
from app.bot import bot
from app.scheduler import start_scheduler, stop_scheduler
from app.scanner import scan_news_sources, post_approved_memorial
from app.ai import get_ai_provider
from app.utils.verification import verify_responder_registry
from app.utils.security import verify_api_key
from app.utils.logger import logger


class CondolenceCreate(BaseModel):
    author_name: str
    message: str


class FamilyClaimCreate(BaseModel):
    claimer_name: str
    relationship_type: str
    claimer_email: str
    notes: Optional[str] = None


class CertificateConfigUpdate(BaseModel):
    chaplain_name: str
    chaplain_title: Optional[str] = "Board Chairperson"
    director_name: str
    director_title: Optional[str] = "Executive Director"


class WebhookSubscribeRequest(BaseModel):
    url: str
    secret: str = None
    category_filter: str = "ALL"
    guild_id: str = None


class WebhookUnsubscribeRequest(BaseModel):
    url: str


class AdminLoginRequest(BaseModel):
    password: str


class CustomMemorialCreate(BaseModel):
    name: str
    agency: str
    category: str = "OTHER"
    date_of_incident: Optional[str] = None
    date_of_death: Optional[str] = None
    summary: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    photo_url: Optional[str] = None
    k9_handler_name: Optional[str] = None
    k9_breed: Optional[str] = None
    service_years: Optional[str] = None
    unit_badge: Optional[str] = None
    bible_verse: Optional[str] = None
    bible_reference: Optional[str] = None
    ai_memorial_text: Optional[str] = None
    article_title: Optional[str] = "Official Memorial Record"
    article_url: Optional[str] = None
    auto_approve: bool = True


def verify_staff_password(x_admin_password: str = Header(None)):
    if not x_admin_password or x_admin_password != settings.STAFF_ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid Staff Admin Password")
    return x_admin_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Fallen Officer Memorial Intelligence System...")
    init_db()

    bot_task = None
    if settings.DISCORD_BOT_TOKEN and settings.DISCORD_BOT_TOKEN != "placeholder_token":
        logger.info("Starting Discord bot task concurrently...")
        bot_task = asyncio.create_task(bot.start(settings.DISCORD_BOT_TOKEN))
    else:
        logger.warning("DISCORD_BOT_TOKEN is not configured in .env. Bot will remain offline, but API will function.")

    start_scheduler(bot=bot)

    yield

    logger.info("Shutting down Fallen Officer Memorial Intelligence System...")
    stop_scheduler()
    if bot_task and not bot.is_closed():
        await bot.close()
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
    logger.info("System shutdown complete.")


app = FastAPI(
    title="Fallen Officer Memorial Intelligence System API",
    description="Backend API, Web Memorial Wall, Leaflet Map, RSS Feed, PDF Certificates, ODMP/NLEOMF Registry Verification, & Multi-Server Bot Engine",
    version="1.0.0",
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.api_route("/healthz", methods=["GET", "HEAD"], tags=["System Health & Uptime"])
@app.api_route("/health", methods=["GET", "HEAD"], tags=["System Health & Uptime"])
@app.api_route("/ping", methods=["GET", "HEAD"], tags=["System Health & Uptime"])
@app.api_route("/status", methods=["GET", "HEAD"], tags=["System Health & Uptime"])
@app.api_route("/api/status", methods=["GET", "HEAD"], tags=["System Health & Uptime"])
async def system_health_status(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Universal health check & uptime status endpoint for external monitoring tools
    (UptimeRobot, Better Uptime, StatusCake, Pingdom, Render Monitors).
    Supports GET and HEAD HTTP methods.
    """
    bot_online = False
    bot_latency = None
    if bot and hasattr(bot, 'is_ready') and bot.is_ready():
        bot_online = True
        bot_latency = round(bot.latency * 1000) if hasattr(bot, 'latency') else None

    db_status = "connected"
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    maint = settings.MAINTENANCE_MODE
    status_str = "maintenance" if maint else "operational"

    response.headers["X-System-Status"] = status_str
    response.headers["X-Bot-Online"] = str(bot_online)
    if bot_latency is not None:
        response.headers["X-Bot-Latency-MS"] = str(bot_latency)

    if request.method == "HEAD":
        return Response(status_code=200)

    return {
        "status": "ok",
        "system": "Fallen Officer Memorial Intelligence System",
        "version": "2.5.0",
        "uptime_status": status_str,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "database": db_status,
        "discord_bot": {
            "online": bot_online,
            "latency_ms": bot_latency
        },
        "maintenance_mode": maint
    }


@app.get("/api/status/badge", tags=["System Health & Uptime"])
async def get_uptime_status_badge():
    """
    Shields.io compatible JSON badge endpoint for live README/Status Page badges.
    """
    maint = settings.MAINTENANCE_MODE
    if maint:
        return {
            "schemaVersion": 1,
            "label": "memorial system",
            "message": "maintenance",
            "color": "orange"
        }
    return {
        "schemaVersion": 1,
        "label": "memorial system",
        "message": "operational",
        "color": "brightgreen"
    }


@app.get("/", tags=["Web Memorial Wall"])
@app.get("/wall", tags=["Web Memorial Wall"])
async def serve_memorial_wall():
    if settings.MAINTENANCE_MODE:
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
          <title>System Maintenance | Fallen Officer Memorial</title>
          <style>
            body { background: #0a0c10; color: #e5c07b; font-family: sans-serif; text-align: center; padding: 5rem 1.5rem; }
            h1 { font-size: 2.2rem; margin-bottom: 1rem; }
            p { color: #8b949e; font-size: 1.1rem; max-width: 500px; margin: 0 auto; }
          </style>
        </head>
        <body>
          <h1>🛠️ System Maintenance in Progress</h1>
          <p>The National Fallen Responder Memorial Wall is currently undergoing scheduled maintenance. Please check back shortly.</p>
        </body>
        </html>
        """)
    return FileResponse("app/static/index.html")


@app.get("/admin", tags=["Staff Admin Portal"])
async def serve_admin_portal():
    return FileResponse("app/static/admin.html")


@app.get("/system-status", tags=["System Status Page"])
@app.get("/status.html", tags=["System Status Page"])
async def serve_status_page():
    return FileResponse("app/static/status.html")


@app.get("/api/memorials", tags=["Public Memorials"])
async def get_public_memorials(db: Session = Depends(get_db)):
    records = (
        db.query(ResponderRecord)
        .filter(ResponderRecord.status == ApprovalStatus.APPROVED)
        .order_by(ResponderRecord.id.desc())
        .all()
    )
    return {"count": len(records), "records": [r.to_dict() for r in records]}


@app.post("/responders/{id}/verify", tags=["ODMP & NLEOMF Registry Auto-Verification"])
async def trigger_registry_verification(id: int, db: Session = Depends(get_db)):
    record = db.query(ResponderRecord).filter(ResponderRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memorial record not found.")

    res = await verify_responder_registry(record.to_dict())
    record.nleomf_verified = res.get("nleomf_verified", False)
    record.odmp_verified = res.get("odmp_verified", False)
    record.fire_hero_verified = res.get("fire_hero_verified", False)
    record.unit_awards = res.get("unit_awards")
    record.verification_badge = res.get("verification_badge")
    db.commit()
    db.refresh(record)

    return {"status": "verified", "record": record.to_dict()}


@app.get("/feed.xml", tags=["RSS Webfeed Syndication"])
async def get_rss_webfeed(db: Session = Depends(get_db)):
    records = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.APPROVED).order_by(ResponderRecord.id.desc()).limit(25).all()

    items_xml = ""
    for r in records:
        pub_date = r.created_at.strftime("%a, %d %b %Y %H:%M:%S GMT") if r.created_at else ""
        items_xml += f"""
        <item>
          <title><![CDATA[In Memoriam: {r.name} ({r.agency})]]></title>
          <link>{r.article_url}</link>
          <guid>#{r.id}</guid>
          <pubDate>{pub_date}</pubDate>
          <description><![CDATA[{r.ai_memorial_text or r.summary}]]></description>
          <category>{r.category.value if hasattr(r.category, 'value') else r.category}</category>
        </item>
        """

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>National Fallen Responder Memorial Intelligence Feed</title>
    <link>https://fallen-memorial-bot.onrender.com/wall</link>
    <description>Official RSS feed of approved emergency responder line-of-duty memorials.</description>
    <language>en-us</language>
    {items_xml}
  </channel>
</rss>
"""
    return Response(content=rss_xml, media_type="application/xml")


@app.post("/api/admin/certificate/config", tags=["Staff Admin Portal"])
async def update_certificate_config(
    payload: CertificateConfigUpdate,
    auth: str = Depends(verify_staff_password),
    db: Session = Depends(get_db)
):
    """Saves global default Chaplain, Director, and Leadership titles in database."""
    configs = db.query(GuildConfig).all()
    c_title = payload.chaplain_title.strip() if payload.chaplain_title else "Board Chairperson"
    d_title = payload.director_title.strip() if payload.director_title else "Executive Director"

    if not configs:
        cfg = GuildConfig(
            guild_id="default_system",
            cert_chaplain_name=payload.chaplain_name.strip(),
            cert_chaplain_title=c_title,
            cert_director_name=payload.director_name.strip(),
            cert_director_title=d_title
        )
        db.add(cfg)
    else:
        for cfg in configs:
            cfg.cert_chaplain_name = payload.chaplain_name.strip()
            cfg.cert_chaplain_title = c_title
            cfg.cert_director_name = payload.director_name.strip()
            cfg.cert_director_title = d_title
    db.commit()
    return {
        "status": "updated",
        "chaplain_name": payload.chaplain_name,
        "chaplain_title": c_title,
        "director_name": payload.director_name,
        "director_title": d_title
    }


@app.get("/responders/{id}/certificate", tags=["Printable Certificates"])
async def generate_tribute_certificate(
    id: int,
    chaplain: Optional[str] = None,
    chap_title: Optional[str] = None,
    director: Optional[str] = None,
    dir_title: Optional[str] = None,
    db: Session = Depends(get_db)
):
    record = db.query(ResponderRecord).filter(ResponderRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memorial record not found.")

    cfg = db.query(GuildConfig).first()
    default_chap = cfg.cert_chaplain_name if (cfg and cfg.cert_chaplain_name) else "Rev. Joseph Miller"
    default_chap_title = cfg.cert_chaplain_title if (cfg and cfg.cert_chaplain_title) else "Board Chairperson"
    default_dir = cfg.cert_director_name if (cfg and cfg.cert_director_name) else "Chief Marcus Vance"
    default_dir_title = cfg.cert_director_title if (cfg and cfg.cert_director_title) else "Executive Director"

    chap_name = chaplain.strip() if chaplain else default_chap
    c_title = chap_title.strip() if chap_title else default_chap_title
    dir_name = director.strip() if director else default_dir
    d_title = dir_title.strip() if dir_title else default_dir_title

    cause_text = record.summary or "Line-of-Duty Ultimate Sacrifice in Protection of the Public"
    if len(cause_text) > 160:
        cause_text = cause_text[:160] + "..."

    cert_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Certificate of Honor - {record.name}</title>
      <link rel="preconnect" href="https://fonts.googleapis.com">
      <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
      <link href="https://fonts.googleapis.com/css2?family=Alex+Brush&family=Cinzel:wght@600;700;800;900&family=Playfair+Display:ital,wght@0,600;0,700;1,400&display=swap" rel="stylesheet">
      <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
      <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background: #0d0f14;
          font-family: 'Playfair Display', serif;
          color: #1a1a1a;
          display: flex;
          flex-direction: column;
          align-items: center;
          padding: 2rem 1rem;
          min-height: 100vh;
        }}

        .print-bar {{
          position: fixed;
          top: 1rem;
          background: rgba(18, 23, 33, 0.95);
          border: 1px solid #e5c07b;
          border-radius: 30px;
          padding: 0.75rem 1.5rem;
          display: flex;
          gap: 0.85rem;
          align-items: center;
          box-shadow: 0 0 20px rgba(0, 0, 0, 0.6);
          z-index: 9999;
          backdrop-filter: blur(10px);
        }}

        .print-bar input {{
          padding: 0.4rem 0.75rem;
          border-radius: 8px;
          border: 1px solid #e5c07b;
          background: #06080c;
          color: #fff;
          font-size: 0.85rem;
          outline: none;
          width: 140px;
        }}

        .print-btn {{
          background: #e5c07b;
          color: #000;
          border: none;
          padding: 0.55rem 1.1rem;
          border-radius: 20px;
          font-weight: 700;
          font-family: sans-serif;
          cursor: pointer;
          font-size: 0.85rem;
        }}

        .download-btn {{
          background: #1f6feb;
          color: #fff;
          border: none;
          padding: 0.55rem 1.1rem;
          border-radius: 20px;
          font-weight: 700;
          font-family: sans-serif;
          cursor: pointer;
          font-size: 0.85rem;
        }}

        .cert-container {{
          width: 960px;
          min-height: 660px;
          background: #fdfbf7;
          background-image: radial-gradient(circle at 50% 50%, #fffdf9 0%, #f7f2e6 100%);
          border: 12px double #b8860b;
          box-shadow: 0 0 40px rgba(0,0,0,0.8);
          padding: 2.25rem;
          margin-top: 4rem;
          position: relative;
          display: flex;
          flex-direction: column;
          text-align: center;
        }}

        .cert-inner-border {{
          border: 2px solid #b8860b;
          height: 100%;
          padding: 1.85rem 2.5rem;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
        }}

        .cert-header h1 {{
          font-family: 'Cinzel', serif;
          font-size: 2.1rem;
          color: #1a2332;
          letter-spacing: 4px;
          text-transform: uppercase;
          font-weight: 900;
        }}

        .cert-header h2 {{
          font-family: 'Cinzel', serif;
          font-size: 1.05rem;
          color: #b8860b;
          letter-spacing: 2px;
          text-transform: uppercase;
          margin-top: 0.25rem;
        }}

        .attest-line {{
          font-size: 1rem;
          color: #4a4a4a;
          font-style: italic;
          margin-top: 0.85rem;
        }}

        .recipient-name {{
          font-family: 'Cinzel', serif;
          font-size: 2.4rem;
          color: #b8860b;
          font-weight: 700;
          margin: 0.65rem 0 0.35rem;
          border-bottom: 2px solid #b8860b;
          display: inline-block;
          padding-bottom: 0.2rem;
        }}

        .agency-line {{
          font-size: 1.15rem;
          color: #222;
          line-height: 1.5;
        }}

        .eow-badge {{
          font-size: 1rem;
          font-weight: 700;
          color: #8b0000;
          margin-top: 0.5rem;
        }}

        .cause-duty-box {{
          font-size: 0.9rem;
          color: #2c3e50;
          margin-top: 0.35rem;
          font-style: italic;
          font-weight: 600;
        }}

        .scripture-box {{
          font-style: italic;
          font-size: 0.95rem;
          color: #333;
          background: rgba(184, 134, 11, 0.06);
          border-left: 3px solid #b8860b;
          padding: 0.6rem 1.1rem;
          margin: 0.75rem auto;
          max-width: 660px;
        }}

        .cert-footer {{
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
          margin-top: 1.1rem;
          padding-top: 0.75rem;
          border-top: 1px solid #d4af37;
        }}

        .sig-block {{
          text-align: center;
          width: 240px;
        }}

        .sig-line {{
          font-family: 'Alex Brush', cursive;
          font-size: 1.9rem;
          color: #0d1b2a;
          border-bottom: 1px solid #777;
          margin-bottom: 0.2rem;
          min-height: 2.4rem;
        }}

        .sig-title {{
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 1px;
          color: #555;
          font-family: sans-serif;
          font-weight: 700;
        }}

        .gold-seal {{
          width: 90px;
          height: 90px;
          border-radius: 50%;
          background: radial-gradient(ellipse at center, #ffd700 0%, #b8860b 100%);
          border: 3px double #ffffff;
          box-shadow: 0 0 15px rgba(184, 134, 11, 0.6);
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
          color: #000;
          font-family: 'Cinzel', serif;
          font-size: 0.55rem;
          font-weight: 900;
          text-align: center;
          padding: 0.4rem;
          text-transform: uppercase;
        }}

        .serial-bar {{
          margin-top: 0.65rem;
          font-size: 0.75rem;
          color: #666;
          font-family: monospace;
          text-align: right;
        }}

        @media print {{
          body {{ background: #fff; padding: 0; }}
          .print-bar {{ display: none; }}
          .cert-container {{
            margin-top: 0;
            box-shadow: none;
            width: 100%;
            border-width: 8px;
          }}
        }}
      </style>
    </head>
    <body>

      <div class="print-bar">
        <span style="color: #e5c07b; font-weight: 700; font-family: 'Cinzel', serif; font-size: 0.95rem; letter-spacing: 1px;">
          Official Line-of-Duty Certificate &bull; Serial No. NFRM-2026-#{record.id}
        </span>

        <div style="display: flex; gap: 0.75rem; align-items: center;">
          <button class="download-btn" onclick="downloadPDF()">📥 Download PDF File</button>
          <button class="print-btn" onclick="window.print()">🖨️ Print Certificate</button>
        </div>
      </div>

      <script>
        function updateSignatures() {{
          const chap = document.getElementById('chapInput').value || '{chap_name}';
          const dir = document.getElementById('dirInput').value || '{dir_name}';
          document.getElementById('sigChaplain').innerText = chap;
          document.getElementById('sigDirector').innerText = dir;
        }}

        function downloadPDF() {{
          const element = document.getElementById('certDoc');
          const opt = {{
            margin:       0.15,
            filename:     'Certificate_{record.name.replace(" ", "_")}.pdf',
            image:        {{ type: 'jpeg', quality: 0.98 }},
            html2canvas:  {{ scale: 2, useCORS: true }},
            jsPDF:        {{ unit: 'in', format: 'letter', orientation: 'landscape' }}
          }};
          html2pdf().set(opt).from(element).save();
        }}
      </script>

      <div class="cert-container" id="certDoc">
        <div class="cert-inner-border">
          
          <div class="cert-header">
            <h1>UNITED STATES HONOR ROLL</h1>
            <h2>National Certificate of Line-of-Duty Valor</h2>
            <div class="attest-line">This official document solemnly attests and places into perpetual honor</div>
          </div>

          <div>
            <div class="recipient-name">{record.name}</div>
            <div class="agency-line">
              of the <strong>{record.agency}</strong><br>
              who gave their life in valiant service, sacrifice, and protection of the public.
            </div>
            <div class="eow-badge">End of Watch: {record.date_of_death or 'Line of Duty'}</div>
            <div class="cause-duty-box">✝ Duty Details & Sacrifice: {cause_text}</div>
          </div>

          {f'<div class="scripture-box">"{record.bible_verse}"<br>— <strong>{record.bible_reference}</strong></div>' if record.bible_verse else ''}

          <div>
            <div class="cert-footer">
              <div class="sig-block">
                <div class="sig-line" id="sigChaplain">{chap_name}</div>
                <div class="sig-title" id="sigChaplainTitle">{c_title}</div>
              </div>

              <div class="gold-seal">
                ⭐<br>OFFICIAL<br>HONOR ROLL<br>SEAL
              </div>

              <div class="sig-block">
                <div class="sig-line" id="sigDirector">{dir_name}</div>
                <div class="sig-title" id="sigDirectorTitle">{d_title}</div>
              </div>
            </div>

            <div class="serial-bar">Official Certificate Serial No. NFRM-2026-#{record.id}</div>
          </div>

        </div>
      </div>

    </body>
    </html>
    """
    return HTMLResponse(content=cert_html)


@app.post("/responders/{id}/claim", tags=["Family Claim Portal"])
async def submit_family_claim(id: int, payload: FamilyClaimCreate, db: Session = Depends(get_db)):
    record = db.query(ResponderRecord).filter(ResponderRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memorial record not found.")

    claim = FamilyClaim(
        record_id=id,
        claimer_name=payload.claimer_name.strip(),
        relationship_type=payload.relationship_type.strip(),
        claimer_email=payload.claimer_email.strip(),
        notes=payload.notes,
        status="PENDING"
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return {"status": "submitted", "claim": claim.to_dict()}


@app.get("/api/vigil/live", tags=["Real-Time Candle Vigils"])
async def get_live_vigil_stats(db: Session = Depends(get_db)):
    total_candles = db.query(ResponderRecord).all()
    c_sum = sum(r.candle_count for r in total_candles)
    return {"global_candles_lit": c_sum, "active_vigil": True}


@app.post("/api/admin/memorials/custom", tags=["Staff Admin Portal"])
async def create_custom_memorial(
    payload: CustomMemorialCreate,
    auth: str = Depends(verify_staff_password),
    db: Session = Depends(get_db)
):
    try:
        cat_enum = ResponderCategory[payload.category.upper()]
    except KeyError:
        cat_enum = ResponderCategory.OTHER

    import time
    art_url = payload.article_url or f"https://memorial.custom/entry/{int(time.time())}"

    ver_res = await verify_responder_registry({
        "name": payload.name,
        "agency": payload.agency,
        "category": payload.category,
        "summary": payload.summary
    })

    record = ResponderRecord(
        name=payload.name.strip(),
        agency=payload.agency.strip(),
        category=cat_enum,
        date_of_incident=payload.date_of_incident,
        date_of_death=payload.date_of_death or "End of Watch",
        summary=payload.summary or f"Official memorial tribute for {payload.name}.",
        nleomf_verified=ver_res.get("nleomf_verified", False),
        odmp_verified=ver_res.get("odmp_verified", False),
        fire_hero_verified=ver_res.get("fire_hero_verified", False),
        unit_awards=ver_res.get("unit_awards"),
        verification_badge=ver_res.get("verification_badge"),
        latitude=payload.latitude,
        longitude=payload.longitude,
        photo_url=payload.photo_url,
        k9_handler_name=payload.k9_handler_name,
        k9_breed=payload.k9_breed,
        service_years=payload.service_years,
        unit_badge=payload.unit_badge,
        article_title=payload.article_title or f"Memorial Record: {payload.name}",
        article_url=art_url,
        source_domain="official_memorial",
        bible_verse=payload.bible_verse or "Greater love has no one than this: to lay down one's life for one's friends.",
        bible_reference=payload.bible_reference or "John 15:13",
        ai_memorial_text=payload.ai_memorial_text or payload.summary or f"Honoring the courage and ultimate sacrifice of {payload.name}.",
        status=ApprovalStatus.APPROVED if payload.auto_approve else ApprovalStatus.PENDING
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    if payload.auto_approve:
        await post_approved_memorial(bot, record)

    return {"status": "created", "broadcasted": payload.auto_approve, "record": record.to_dict()}


@app.post("/api/admin/maintenance", tags=["Staff Admin Portal"])
async def toggle_maintenance_mode(auth: str = Depends(verify_staff_password)):
    settings.MAINTENANCE_MODE = not settings.MAINTENANCE_MODE
    if hasattr(bot, 'change_presence') and bot.is_ready():
        import discord
        if settings.MAINTENANCE_MODE:
            await bot.change_presence(
                status=discord.Status.dnd,
                activity=discord.Activity(name="🛠️ System Maintenance in Progress", type=discord.ActivityType.watching)
            )
        else:
            await bot.change_presence(
                status=discord.Status.online,
                activity=discord.Activity(name="Line of Duty Memorials", type=discord.ActivityType.watching)
            )
    return {"status": "updated", "maintenance_mode": settings.MAINTENANCE_MODE}


@app.post("/api/admin/login", tags=["Staff Admin Portal"])
async def admin_login(payload: AdminLoginRequest):
    if payload.password != settings.STAFF_ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid Staff Admin Password")
    return {"status": "authenticated", "message": "Welcome to Staff Admin Portal"}


@app.post("/api/admin/approve/{id}", tags=["Staff Admin Portal"])
async def admin_approve(id: int, auth: str = Depends(verify_staff_password), db: Session = Depends(get_db)):
    record = db.query(ResponderRecord).filter(ResponderRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memorial record not found")

    record.status = ApprovalStatus.APPROVED
    db.commit()
    db.refresh(record)

    await post_approved_memorial(bot, record)
    return {"status": "approved", "record": record.to_dict()}


@app.post("/api/admin/reject/{id}", tags=["Staff Admin Portal"])
async def admin_reject(id: int, auth: str = Depends(verify_staff_password), db: Session = Depends(get_db)):
    record = db.query(ResponderRecord).filter(ResponderRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memorial record not found")

    record.status = ApprovalStatus.REJECTED
    db.commit()
    return {"status": "rejected", "id": id}


@app.delete("/api/admin/responders/{id}", tags=["Staff Admin Portal"])
async def admin_delete(id: int, auth: str = Depends(verify_staff_password), db: Session = Depends(get_db)):
    record = db.query(ResponderRecord).filter(ResponderRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memorial record not found")

    db.delete(record)
    db.commit()
    return {"status": "deleted", "id": id}


@app.get("/api/status", tags=["System Health"])
async def get_health_status(db: Session = Depends(get_db)):
    total_records = db.query(ResponderRecord).count()
    pending_records = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.PENDING).count()
    approved_records = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.APPROVED).count()
    total_guilds = db.query(GuildConfig).count()

    bot_is_ready = bot.is_ready() if hasattr(bot, 'is_ready') else False

    cfg = db.query(GuildConfig).first()

    return {
        "status": "online",
        "maintenance_mode": settings.MAINTENANCE_MODE,
        "system": "Fallen Officer Memorial Intelligence System",
        "version": "1.0.0",
        "cert_chaplain_name": cfg.cert_chaplain_name if cfg else "Rev. Joseph Miller",
        "cert_chaplain_title": cfg.cert_chaplain_title if cfg else "Board Chairperson",
        "cert_director_name": cfg.cert_director_name if cfg else "Chief Marcus Vance",
        "cert_director_title": cfg.cert_director_title if cfg else "Executive Director",
        "bot_status": {
            "online": bot_is_ready,
            "latency_ms": round(bot.latency * 1000) if bot_is_ready else None,
            "connected_guilds_count": len(bot.guilds) if bot_is_ready else 0,
        },
        "database_stats": {
            "total_memorials": total_records,
            "pending_review": pending_records,
            "approved": approved_records,
            "configured_servers": total_guilds
        }
    }


@app.get("/stats", tags=["Public Analytics"])
async def get_analytics_stats(db: Session = Depends(get_db)):
    total = db.query(ResponderRecord).count()
    approved = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.APPROVED).count()
    pending = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.PENDING).count()

    by_category = {}
    for cat in ResponderCategory:
        cnt = db.query(ResponderRecord).filter(ResponderRecord.category == cat).count()
        by_category[cat.value] = cnt

    return {
        "total_records": total,
        "approved_records": approved,
        "pending_records": pending,
        "category_breakdown": by_category
    }


@app.get("/latest", tags=["Public Memorials"])
async def get_latest_memorial(db: Session = Depends(get_db)):
    record = (
        db.query(ResponderRecord)
        .filter(ResponderRecord.status == ApprovalStatus.APPROVED)
        .order_by(ResponderRecord.id.desc())
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No approved memorial records found in database."
        )
    return record.to_dict()


@app.post("/responders/{id}/candle", tags=["Virtual Candles"])
async def light_candle(id: int, request: Request, db: Session = Depends(get_db)):
    record = db.query(ResponderRecord).filter(ResponderRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memorial record not found.")

    client_ip = request.client.host if request.client else "127.0.0.1"
    cutoff = datetime.utcnow() - timedelta(hours=24)

    recent_log = (
        db.query(CandleLog)
        .filter(
            CandleLog.record_id == id,
            CandleLog.client_ip == client_ip,
            CandleLog.created_at >= cutoff
        )
        .first()
    )

    if recent_log:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You have already lit a candle for this responder today. Thank you for your tribute!"
        )

    candle_log = CandleLog(record_id=id, client_ip=client_ip)
    db.add(candle_log)

    record.candle_count += 1
    db.commit()
    db.refresh(record)

    return {"id": record.id, "candle_count": record.candle_count, "message": "Candle lit successfully!"}


@app.get("/responders/{id}/condolences", tags=["Virtual Condolences"])
async def list_condolences(id: int, db: Session = Depends(get_db)):
    condolences = db.query(Condolence).filter(Condolence.record_id == id).order_by(Condolence.id.desc()).all()
    return {"record_id": id, "condolences": [c.to_dict() for c in condolences]}


@app.post("/responders/{id}/condolences", tags=["Virtual Condolences"])
async def post_condolence(id: int, payload: CondolenceCreate, db: Session = Depends(get_db)):
    record = db.query(ResponderRecord).filter(ResponderRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memorial record not found.")

    condolence = Condolence(
        record_id=id,
        author_name=payload.author_name.strip() or "Anonymous Visitor",
        message=payload.message.strip()
    )
    db.add(condolence)
    db.commit()
    db.refresh(condolence)

    return condolence.to_dict()


@app.get("/responders/{id}/eulogy", tags=["AI Intelligence"])
async def get_ai_eulogy(id: int, db: Session = Depends(get_db)):
    record = db.query(ResponderRecord).filter(ResponderRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memorial record not found.")

    ai_provider = get_ai_provider()
    eulogy = await ai_provider.generate_eulogy(record.to_dict())
    return {"id": id, "name": record.name, "eulogy": eulogy}


@app.post("/webhooks/subscribe", tags=["Webhook Subscription API"])
async def subscribe_webhook(payload: WebhookSubscribeRequest, db: Session = Depends(get_db)):
    existing = db.query(WebhookSubscription).filter(WebhookSubscription.url == payload.url).first()
    if existing:
        existing.category_filter = payload.category_filter.upper()
        existing.is_active = True
        if payload.secret:
            existing.secret = payload.secret
        db.commit()
        return {"status": "updated", "subscription": existing.to_dict()}

    sub = WebhookSubscription(
        url=payload.url,
        secret=payload.secret,
        category_filter=payload.category_filter.upper(),
        guild_id=payload.guild_id,
        is_active=True
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {"status": "created", "subscription": sub.to_dict()}


@app.get("/webhooks", tags=["Admin Data Access"])
async def list_webhooks(
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    subs = db.query(WebhookSubscription).all()
    return {"count": len(subs), "webhooks": [s.to_dict() for s in subs]}


@app.get("/guilds", tags=["Admin Data Access"])
async def list_guilds(
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    configs = db.query(GuildConfig).all()
    return {"count": len(configs), "guilds": [c.to_dict() for c in configs]}


@app.get("/responders", tags=["Admin Data Access"])
async def list_all_responders(
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    records = db.query(ResponderRecord).order_by(ResponderRecord.id.desc()).all()
    return {
        "count": len(records),
        "records": [r.to_dict() for r in records]
    }


@app.get("/export", tags=["Admin Data Access"])
async def export_data(
    format: str = "json",
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    records = db.query(ResponderRecord).order_by(ResponderRecord.id.asc()).all()
    dict_records = [r.to_dict() for r in records]

    if format.lower() == "csv":
        output = io.StringIO()
        if dict_records:
            writer = csv.DictWriter(output, fieldnames=dict_records[0].keys())
            writer.writeheader()
            writer.writerows(dict_records)
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=memorials_export.csv"}
        )

    return Response(
        content=json.dumps(dict_records, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=memorials_export.json"}
    )


@app.post("/scan", tags=["Scanner Automation"])
async def trigger_manual_scan(
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    background_tasks.add_task(scan_news_sources, bot=bot)
    return {
        "status": "success",
        "message": "Manual news source scan initiated in background."
    }
