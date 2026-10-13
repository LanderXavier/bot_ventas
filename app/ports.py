from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

@dataclass
class IncomingMsg:
    channel_message_id: str
    from_phone: str
    business_phone_id: str = ""
    text: str = ""
    media_id: str = ""
    media_mime: str = ""

@dataclass
class Business:
    id: str
    phone_number_id: str
    access_token: str
    zona_horaria: str = "America/Guayaquil"
    notificaciones_activas: bool = True

class Channel(Protocol):
    name: str
    def parse_webhook(self, payload: dict) -> list[IncomingMsg]: ...
    def send_text(self, business: Business, to: str, body: str) -> None: ...
    def fetch_media(self, business: Business, media_id: str) -> tuple[bytes, str]: ...

class SaleExtractionModel(Protocol):
    monto: float | None
    moneda: str | None
    cliente_nombre: str | None
    pagador_nombre: str | None
    productos_descripcion: str | None
    metodo_pago: str | None
    referencia_pago: str | None
    is_complete: bool
    next_question: str | None

class Extractor(Protocol):
    name: str
    def extract(self, draft: dict, text: str, image: bytes | None,
                image_mime: str | None) -> SaleExtractionModel: ...
