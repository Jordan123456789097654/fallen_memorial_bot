"""
Main FastAPI Application Entrypoint.
Concurrently hosts REST API, Web Memorial Wall, Leaflet Map, RSS Feed (/feed.xml), PDF Certificates, Family Claims, and discord.py Bot.
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
    article_title: Optional[str] = "Custom Staff Entry"
    article_url: Optional[str] = None
    auto_approve: bool = True


def verify_staff_password(x_admin_password: str = Header(None)):
    """Verifies Staff Admin Password header."""
    if not x_admin_password or x_admin_password != settings.STAFF_ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid Staff Admin Password")
    return x_admin_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan handler for concurrent bot execution and scheduler management."""
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
    description="Backend API, Web Memorial Wall, Leaflet Map, RSS Feed, PDF Certificates, & Multi-Server Bot Engine",
    version="1.0.0",
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/healthz", tags=["System Health"])
async def healthz():
    return {"status": "ok", "service": "fallen-officer-memorial-system"}


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


@app.get("/feed.xml", tags=["RSS Webfeed Syndication"])
async def get_rss_webfeed(db: Session = Depends(get_db)):
    """Generates an outgoing RSS 2.0 XML feed for news syndication."""
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
    <link>https://fallen-responder.onrender.com/wall</link>
    <description>Official RSS feed of approved emergency responder line-of-duty memorials.</description>
    <language>en-us</language>
    {items_xml}
  </channel>
</rss>
"""
    return Response(content=rss_xml, media_type="application/xml")


@app.get("/responders/{id}/certificate", tags=["Printable Certificates"])
async def generate_tribute_certificate(id: int, db: Session = Depends(get_db)):
    """Generates a printable framed HTML/PDF tribute certificate of honor."""
    record = db.query(ResponderRecord).filter(ResponderRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memorial record not found.")

    cert_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <title>Certificate of Honor - {record.name}</title>
      <style>
        body {{ background: #0c0f17; color: #f0f6fc; font-family: 'Georgia', serif; display: flex; justify-content: center; padding: 2rem; }}
        .cert-border {{ border: 12px double #e5c07b; padding: 3rem; max-width: 800px; width: 100%; text-align: center; background: #121722; box-shadow: 0 0 50px rgba(229,192,123,0.3); }}
        h1 {{ font-size: 2.2rem; color: #e5c07b; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 0.5rem; }}
        h2 {{ font-size: 1.5rem; color: #ffffff; margin-bottom: 1.5rem; }}
        .name {{ font-size: 2.5rem; color: #e5c07b; text-decoration: underline; margin: 1.5rem 0; }}
        p {{ font-size: 1.1rem; line-height: 1.8; color: #c9d1d9; }}
        .scripture {{ font-style: italic; background: rgba(229,192,123,0.1); padding: 1rem; border-left: 4px solid #e5c07b; margin: 1.5rem 0; }}
        .footer {{ margin-top: 2.5rem; font-size: 0.9rem; color: #8b949e; border-top: 1px solid #30363d; padding-top: 1rem; }}
      </style>
    </head>
    <body>
      <div class="cert-border">
        <h1>NATIONAL CERTIFICATE OF HONOR</h1>
        <h2>Line-of-Duty Ultimate Sacrifice</h2>
        <p>This official certificate solemnly attests that</p>
        <div class="name">{record.name}</div>
        <p>of the <strong>{record.agency}</strong> gave their life in courageous service and protection of the public.</p>
        <p><strong>End of Watch:</strong> {record.date_of_death or 'Line of Duty'}</p>
        {f'<div class="scripture">"{record.bible_verse}"<br>— <strong>{record.bible_reference}</strong></div>' if record.bible_verse else ''}
        <div class="footer">
          Sequential Memorial ID: #{record.id} • Verified Honor Roll Record<br>
          <em>"Greater love has no one than this: to lay down one's life for one's friends."</em>
        </div>
      </div>
    </body>
    </html>
    """
    return HTMLResponse(content=cert_html)


@app.post("/responders/{id}/claim", tags=["Family Claim Portal"])
async def submit_family_claim(id: int, payload: FamilyClaimCreate, db: Session = Depends(get_db)):
    """Submits a claim request by verified family or agency representative."""
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
    """Fetches global live candle vigil counters."""
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

    record = ResponderRecord(
        name=payload.name.strip(),
        agency=payload.agency.strip(),
        category=cat_enum,
        date_of_incident=payload.date_of_incident,
        date_of_death=payload.date_of_death or "End of Watch",
        summary=payload.summary or f"Custom staff tribute entry for {payload.name}.",
        latitude=payload.latitude,
        longitude=payload.longitude,
        photo_url=payload.photo_url,
        k9_handler_name=payload.k9_handler_name,
        k9_breed=payload.k9_breed,
        service_years=payload.service_years,
        unit_badge=payload.unit_badge,
        article_title=payload.article_title or f"Memorial Tribute: {payload.name}",
        article_url=art_url,
        source_domain="custom_entry",
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

    return {
        "status": "online",
        "maintenance_mode": settings.MAINTENANCE_MODE,
        "system": "Fallen Officer Memorial Intelligence System",
        "version": "1.0.0",
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
