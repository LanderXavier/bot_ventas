from __future__ import annotations
from fastapi import BackgroundTasks, FastAPI, Query, Request, Response
from psycopg.rows import dict_row

from .channels import get_channel
from .db import pool
from .llms import get_extractor
from .ports import Business
from .service import Service
from .settings import settings

app = FastAPI(title="bot_ventas MVP")
channel = get_channel(settings.input_provider)
_extractor = None

def extractor():
    global _extractor
    if _extractor is None:
        if settings.llm_provider == "openrouter":
            _extractor = get_extractor("openrouter", settings.openrouter_api_key, settings.openrouter_model)
        elif settings.llm_provider == "groq":
            _extractor = get_extractor("groq", settings.groq_api_key, settings.groq_model)
        else:
            _extractor = get_extractor(settings.llm_provider, settings.gemini_api_key, settings.llm_model)
    return _extractor

@app.get("/webhook")
def verify(mode: str = Query("", alias="hub.mode"), token: str = Query("", alias="hub.verify_token"),
           challenge: str = Query("", alias="hub.challenge")):
    return Response(content=challenge, media_type="text/plain") if (mode == "subscribe" and token == settings.meta_verify_token) else Response(status_code=403)

@app.post("/webhook")
async def webhook(req: Request, bg: BackgroundTasks):
    payload = await req.json()
    msgs = channel.parse_webhook(payload)  # parse rápido, proceso en background
    for m in msgs:
        bg.add_task(run_one, m)
    return {"ok": True}  # 200 inmediato: timeouts de Meta

def run_one(m):
    with pool(settings.database_url).connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            svc = Service(cur, channel, extractor(), settings.draft_ttl_minutes)
            def send(body: str, to: str = ""):
                biz = cur.execute("SELECT * FROM negocios WHERE phone_number_id=%s", (m.business_phone_id,)).fetchone()
                svc_ch_biz = Business(id=biz["id"], phone_number_id=biz["phone_number_id"],
                                      access_token=biz["access_token"], zona_horaria=biz["zona_horaria"],
                                      notificaciones_activas=biz["notificaciones_activas"])
                channel.send_text(svc_ch_biz, to or m.from_phone, body)
            try:
                svc.process(m, send)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
