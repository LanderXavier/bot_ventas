from __future__ import annotations
import httpx
from .ports import Business, IncomingMsg

GRAPH = "https://graph.facebook.com/v21.0"

class WhatsAppChannel:
    name = "whatsapp"

    def parse_webhook(self, payload: dict) -> list[IncomingMsg]:
        out: list[IncomingMsg] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                biz = value.get("metadata", {}).get("phone_number_id", "")
                for m in value.get("messages", []):
                    mid = m.get("id", "")
                    frm = m.get("from", "")
                    text, media_id = "", ""
                    if m.get("text"):
                        text = m["text"].get("body", "")
                    elif m.get("image"):
                        media_id = m["image"].get("id", "")
                        text = m["image"].get("caption", "")
                    if mid and frm:
                        out.append(IncomingMsg(mid, frm, biz, text, media_id))
        return out

    def send_text(self, business: Business, to: str, body: str) -> None:
        httpx.post(f"{GRAPH}/{business.phone_number_id}/messages",
            headers={"Authorization": f"Bearer {business.access_token}"},
            json={"messaging_product": "whatsapp", "to": to,
                  "text": {"body": body}}, timeout=15).raise_for_status()

    def fetch_media(self, business: Business, media_id: str) -> tuple[bytes, str]:
        h = {"Authorization": f"Bearer {business.access_token}"}
        meta = httpx.get(f"{GRAPH}/{media_id}", headers=h, timeout=15).json()
        r = httpx.get(meta["url"], headers=h, timeout=30)
        r.raise_for_status()
        return r.content, r.headers.get("content-type", "image/jpeg")

class TelegramChannel:
    """Canal Telegram Bot API. Reusa negocios.access_token como bot token y
    negocios.phone_number_id='telegram' como id de negocio (el webhook de
    Telegram no trae identidad del bot). usuarios.telefono = chat_id."""
    name = "telegram"
    API = "https://api.telegram.org"

    def parse_webhook(self, payload: dict) -> list[IncomingMsg]:
        msg = payload.get("message") or payload.get("edited_message") or {}
        if not msg:
            return []
        mid = msg.get("message_id", "")
        chat = msg.get("chat", {}) or {}
        frm = msg.get("from") or {}
        chat_id = str(chat.get("id", "") or frm.get("id", ""))
        text = msg.get("text", "") or msg.get("caption", "")
        media_id = ""
        if msg.get("photo"):
            media_id = msg["photo"][-1].get("file_id", "")
        elif msg.get("document"):
            media_id = (msg.get("document") or {}).get("file_id", "")
        if not (mid and chat_id):
            return []
        return [IncomingMsg(f"tg-{payload.get('update_id')}-{mid}",
                            chat_id, "telegram", text, media_id)]

    def send_text(self, business: Business, to: str, body: str) -> None:
        httpx.post(f"{self.API}/bot{business.access_token}/sendMessage",
                   json={"chat_id": to, "text": body}, timeout=15).raise_for_status()

    def fetch_media(self, business: Business, media_id: str) -> tuple[bytes, str]:
        tok = business.access_token
        fp = httpx.get(f"{self.API}/bot{tok}/getFile",
                       params={"file_id": media_id}, timeout=15).json()["result"]["file_path"]
        r = httpx.get(f"{self.API}/file/bot{tok}/{fp}", timeout=30)
        r.raise_for_status()
        return r.content, r.headers.get("content-type", "image/jpeg")

# Registro global: cambiar de input = INPUT_PROVIDER=nuevo + entrada aquí. Nada hardcodeado en service/main.
INPUTS = {"whatsapp": WhatsAppChannel, "telegram": TelegramChannel}

def get_channel(name: str):
    try:
        return INPUTS[name]()
    except KeyError:
        raise ValueError(f"INPUT_PROVIDER desconocido: {name} (opciones: {sorted(INPUTS)})")
