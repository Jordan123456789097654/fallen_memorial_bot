"""
Main FastAPI Application Entrypoint.
Concurrently hosts FastAPI REST API, Public Web Memorial Wall, and discord.py Bot.
Includes dedicated Render /healthz health check, virtual candles, condolences, and eulogy endpoints.
"""
import io
import csv
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import init_db, get_db, SessionLocal
from app.models import ResponderRecord, ApprovalStatus, GuildConfig, ResponderCategory, Condolence
from app.bot import bot
from app.scheduler import start_scheduler, stop_scheduler
from app.scanner import scan_news_sources
from app.ai import get_ai_provider
from app.utils.security import verify_api_key
from app.utils.logger import logger


# Request payload schemas
class CondolenceCreate(BaseModel):
    author_name: str
    message: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan handler for concurrent bot execution and scheduler management.
    """
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
    description="Backend API, Web Memorial Wall, & Multi-Server Intelligence Engine",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files for Web Memorial Wall
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/healthz", tags=["System Health"])
async def healthz():
    """
    Dedicated health check endpoint for Render.com load balancers.
    """
    return {"status": "ok", "service": "fallen-officer-memorial-system"}


@app.get("/", tags=["Web Memorial Wall"])
@app.get("/wall", tags=["Web Memorial Wall"])
async def serve_memorial_wall():
    """
    Serves the interactive Public Web Memorial Wall dashboard.
    """
    return FileResponse("app/static/index.html")


@app.get("/api/status", tags=["System Health"])
async def get_health_status(db: Session = Depends(get_db)):
    """
    System and bot status overview endpoint.
    """
    total_records = db.query(ResponderRecord).count()
    pending_records = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.PENDING).count()
    approved_records = db.query(ResponderRecord).filter(ResponderRecord.status == ApprovalStatus.APPROVED).count()
    total_guilds = db.query(GuildConfig).count()

    bot_is_ready = bot.is_ready() if hasattr(bot, 'is_ready') else False

    return {
        "status": "online",
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
    """
    JSON Analytics & Category Breakdown endpoint.
    """
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
    """
    Returns the newest approved memorial record in JSON format.
    """
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
async def light_candle(id: int, db: Session = Depends(get_db)):
    """
    Increments the virtual candle lighting counter for a responder record.
    """
    record = db.query(ResponderRecord).filter(ResponderRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memorial record not found.")

    record.candle_count += 1
    db.commit()
    db.refresh(record)

    return {"id": record.id, "candle_count": record.candle_count}


@app.get("/responders/{id}/condolences", tags=["Virtual Condolences"])
async def list_condolences(id: int, db: Session = Depends(get_db)):
    """
    Retrieves public condolence messages posted for a responder record.
    """
    condolences = db.query(Condolence).filter(Condolence.record_id == id).order_by(Condolence.id.desc()).all()
    return {"record_id": id, "condolences": [c.to_dict() for c in condolences]}


@app.post("/responders/{id}/condolences", tags=["Virtual Condolences"])
async def post_condolence(id: int, payload: CondolenceCreate, db: Session = Depends(get_db)):
    """
    Posts a public condolence message for a responder record.
    """
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
    """
    Retrieves an AI-generated solemn eulogy speech for a responder.
    """
    record = db.query(ResponderRecord).filter(ResponderRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Memorial record not found.")

    ai_provider = get_ai_provider()
    eulogy = await ai_provider.generate_eulogy(record.to_dict())
    return {"id": id, "name": record.name, "eulogy": eulogy}


@app.get("/responders", tags=["Admin Data Access"])
async def list_all_responders(
    api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Lists all responder records in the database (secured with X-API-Key).
    """
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
    """
    Downloads database records as CSV or JSON file attachment (Secured with X-API-Key).
    """
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
    """
    Triggers an immediate background news scan via API call (Secured with X-API-Key).
    """
    background_tasks.add_task(scan_news_sources, bot=bot)
    return {
        "status": "success",
        "message": "Manual news source scan initiated in background."
    }
