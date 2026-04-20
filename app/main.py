from fastapi import FastAPI
from app.api.telnyx_webhook import router as telnyx_webhook_router
from app.ws.telnyx_stream import router as telnyx_stream_router
from app.core.logging import logger
from app.services.daily_summary_service import run_daily_summary_scheduler
from app.services.metrics_service import initialize_metrics_db

app = FastAPI(title="Realtime Voice Agent for Craftsmen")

app.include_router(telnyx_webhook_router, tags=["Webhook"])
app.include_router(telnyx_stream_router, tags=["WebSocket"])

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up Realtime Voice Agent server...")
    initialize_metrics_db()
    app.state.daily_summary_task = run_daily_summary_scheduler()


@app.on_event("shutdown")
async def shutdown_event():
    daily_summary_task = getattr(app.state, "daily_summary_task", None)
    if daily_summary_task:
        daily_summary_task.cancel()

@app.get("/")
def health_check():
    return {"status": "running", "service": "voice_agent_telnyx"}
