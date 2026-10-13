"""Self-check sin Postgres: swappability + máquina de borrador."""
from app.channels import INPUTS, get_channel
from app.llms import LLMS, get_extractor
from app.service import Service, looks_like_report
from app.ports import IncomingMsg
from app.schemas import SaleExtraction

class FakeCur:
    def __init__(self):
        self.sent = []
        self.db = {"neg": {"id": "n1", "phone_number_id": "biz1", "access_token": "t",
                           "zona_horaria": "America/Guayaquil", "notificaciones_activas": False},
                   "user": {"id": "u1", "telefono": "5939", "nombre": "Juan", "rol": "vendedor"},
                   "seen": set(), "ventas": []}
    def execute(self, sql, params=()):
        self.last = (sql, params)
        return self
    def fetchone(self):
        sql, p = self.last
        if "negocios WHERE phone_number_id" in sql:
            return self.db["neg"]
        if "usuarios WHERE telefono" in sql:
            return self.db["user"] if p[0] == "5939" else None
        if "source_message_id" in sql:
            return {"id": 1} if p[0] in self.db["seen"] else None
        if "estado='borrador'" in sql:
            return None
        if "estado='confirmado'" in sql and "referencia_pago" in sql:
            return None
        return None
    def fetchall(self):
        return []

class FakeChannel:
    name = "fake"
    def fetch_media(self, biz, mid):
        return b"img", "image/jpeg"

class HalfExtractor:
    name = "half"
    def extract(self, draft, text, image, mime):
        return SaleExtraction(monto=None, metodo_pago="efectivo", is_complete=False, next_question="¿Cuál fue el monto?")

class FullExtractor:
    name = "fullx"
    def extract(self, draft, text, image, mime):
        return SaleExtraction(monto=25.5, metodo_pago="efectivo", is_complete=True)

# 1. Registros globales existen y aceptan swap por nombre (input y LLM no hardcodeados)
assert "whatsapp" in INPUTS and get_channel("whatsapp").name == "whatsapp"
assert {"gemini", "stub"} <= set(LLMS) and get_extractor("stub").name == "stub"
try:
    get_channel("telegram-inexistente"); assert False
except ValueError:
    pass

# 2. Usuario desconocido se ignora en silencio
c = FakeCur()
svc = Service(c, FakeChannel(), FullExtractor())
out = []
r = svc.process(IncomingMsg("m1", "0000", "biz1", "vende 10"), lambda b, to="": out.append(b))
assert r == "ignored:unknown-user" and out == []

# 3. Venta incompleta -> borrador + pregunta; ni monto ni método se inventan
c = FakeCur()
svc = Service(c, FakeChannel(), HalfExtractor())
out = []
assert svc.process(IncomingMsg("m2", "5939", "biz1", "vendí algo"), lambda b, to="": out.append(b)) == "ok:draft"
assert out == ["¿Cuál fue el monto?"]

# 4. Venta completa -> confirmado
c = FakeCur()
svc = Service(c, FakeChannel(), FullExtractor())
out = []
assert svc.process(IncomingMsg("m3", "5939", "biz1", "vendí 25.50 en efectivo"), lambda b, to="": out.append(b)) == "ok:confirmed"
assert out == ["✅ Venta guardada."]

# 5. Idempotencia Meta: mismo source_message_id se ignora
c = FakeCur(); c.db["seen"].add("m4")
assert Service(c, FakeChannel(), FullExtractor()).process(
    IncomingMsg("m4", "5939", "biz1", "x"), lambda b, to="": None) == "ignored:duplicate-delivery"

# 6. Reporte de dueño se rutea sin LLM de ventas
assert looks_like_report("¿Cuánto vendimos hoy?")
print("self-check OK: input/LLM swappable, borrador, idempotencia, reportes")
