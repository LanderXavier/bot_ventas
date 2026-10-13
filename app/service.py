from __future__ import annotations

REPORT_WORDS = ("vendimos", "vendió", "vendio", "revisión", "revision", "reporte", "total", "hoy")

def looks_like_report(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in REPORT_WORDS)

def draft_to_dict(row: dict) -> dict:
    return {k: row.get(k) for k in (
        "monto", "moneda", "cliente_nombre", "pagador_nombre",
        "productos_descripcion", "metodo_pago", "referencia_pago") if row.get(k) is not None}

class Service:
    """Máquina de estados sobre ventas.borrador. Recibe Channel+Extractor inyectados (nada hardcodeado)."""
    def __init__(self, conn, channel, extractor, ttl_min: int = 15):
        self.c, self.ch, self.llm, self.ttl = conn, channel, extractor, ttl_min

    def _one(self, sql: str, params: tuple = ()):
        self.c.execute(sql, params)
        r = self.c.fetchone()
        return dict(r) if r else None

    def process(self, msg, send) -> str:
        biz = self._one("SELECT * FROM negocios WHERE phone_number_id=%s", (msg.business_phone_id,))
        if biz is None:  # webhook de otro número
            return "ignored:no-business"
        user = self._one("SELECT * FROM usuarios WHERE telefono=%s AND negocio_id=%s",
                         (msg.from_phone, biz["id"]))
        if user is None:
            return "ignored:unknown-user"  # rechaza silenciosamente
        if self._one("SELECT id FROM ventas WHERE source_message_id=%s", (msg.channel_message_id,)):
            return "ignored:duplicate-delivery"  # idempotencia Meta
        if user["rol"] == "dueño" and msg.text and looks_like_report(msg.text) and not msg.media_id:
            send(self.report(biz, msg.text))
            return "ok:report"
        image, mime = None, None
        if msg.media_id:
            image, mime = self.ch.fetch_media(type("B", (), biz)(), msg.media_id)
        draft = self._one(
            """SELECT * FROM ventas WHERE vendedor_id=%s AND negocio_id=%s AND estado='borrador'
               AND updated_at > now() - (%s || ' minutes')::interval
               ORDER BY updated_at DESC LIMIT 1""",
            (user["id"], biz["id"], str(self.ttl)))
        ext = self.llm.extract(draft_to_dict(draft or {}), msg.text or "", image, mime)
        data = ext.model_dump(exclude={"is_complete", "next_question"})
        if ext.referencia_pago and self._one(
                """SELECT id FROM ventas WHERE negocio_id=%s AND metodo_pago=%s
                   AND referencia_pago=%s AND estado='confirmado'""",
                (biz["id"], ext.metodo_pago, ext.referencia_pago)):
            self._save(user, biz, data, "requiere_revision", msg.channel_message_id, draft)
            send("⚠️ Ese comprobante ya estaba registrado. Lo marqué para revisión.")
            return "ok:logical-duplicate"
        if not ext.is_complete or not (ext.monto and ext.metodo_pago):
            self._save(user, biz, data, "borrador", msg.channel_message_id, draft)
            send(ext.next_question or "¿Cuál fue el monto y el método de pago?")
            return "ok:draft"
        self._save(user, biz, data, "confirmado", msg.channel_message_id, draft)
        send("✅ Venta guardada.")
        if biz.get("notificaciones_activas"):
            dueno = self._one("SELECT telefono FROM usuarios WHERE negocio_id=%s AND rol='dueño' LIMIT 1", (biz["id"],))
            if dueno and dueno["telefono"] != user["telefono"]:
                try:
                    send(f"🔔 Venta: {ext.monto} ({ext.metodo_pago}) — {user.get('nombre') or user['telefono']}",
                         to=dueno["telefono"])
                except TypeError:
                    pass  # send(to=...) solo si el channel lo soporta; el flujo principal ya notificó
        return "ok:confirmed"

    def _save(self, user, biz, data, estado, mid, draft):
        data = {k: v for k, v in data.items() if v is not None}
        if draft:
            sets = ", ".join(f"{k}=%s" for k in data) + ", estado=%s, source_message_id=%s, updated_at=now()"
            self.c.execute(f"UPDATE ventas SET {sets} WHERE id=%s AND negocio_id=%s",
                           (*data.values(), estado, mid, draft["id"], biz["id"]))
        else:
            cols = ["negocio_id", "vendedor_id", *data, "estado", "source_message_id"]
            self.c.execute(f"INSERT INTO ventas ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})",
                           (biz["id"], user["id"], *data.values(), estado, mid))

    def report(self, biz, text: str) -> str:
        t = (text or "").lower()
        if "revisión" in t or "revision" in t:
            rows = self.c.execute(
                "SELECT monto, metodo_pago, pagador_nombre FROM ventas WHERE negocio_id=%s AND estado='requiere_revision' LIMIT 20",
                (biz["id"],)).fetchall()
            return f"🔎 Por revisar: {len(rows)}" + (" (ver detalle en BD)" if rows else ". Todo limpio ✅")
        if "vendió" in t or "vendio" in t or "juan" in t or "vendedor" in t:
            rows = self.c.execute(
                """SELECT u.nombre, SUM(v.monto) total, COUNT(*) n FROM ventas v
                   JOIN usuarios u ON u.id=v.vendedor_id
                   WHERE v.negocio_id=%s AND v.estado='confirmado'
                   AND v.fecha_venta >= date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s
                   GROUP BY u.nombre""", (biz["id"], biz["zona_horaria"], biz["zona_horaria"])).fetchall()
            return "📊 Hoy por vendedor: " + (", ".join(f"{r[0]}: {r[1]} ({r[2]})" for r in rows) or "sin ventas")
        rows = self.c.execute(
            """SELECT v.monto, v.metodo_pago,
                      COALESCE(v.pagador_nombre, v.cliente_nombre, '-') AS quien
               FROM ventas v
               WHERE v.negocio_id=%s AND v.estado='confirmado'
               AND v.fecha_venta >= date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s
               ORDER BY v.fecha_venta DESC LIMIT 20""",
            (biz["id"], biz["zona_horaria"], biz["zona_horaria"])).fetchall() or []
        total = sum(float(r["monto"] or 0) for r in rows)
        head = f"📊 Hoy: {len(rows)} venta{'s' if len(rows) != 1 else ''} — Total ${total:.2f}"
        if not rows:
            return head + ". Sin ventas."
        lines = [head]
        for r in rows:
            met = {"transferencia": "transferencia", "efectivo": "efectivo"}.get(
                r["metodo_pago"] or "-", r["metodo_pago"] or "-")
            quien = r["quien"] or ""
            extra = f" — {quien}" if quien != "-" else ""
            lines.append(f"• ${float(r['monto'] or 0):.2f} en {met}{extra}")
        return "\n".join(lines)
