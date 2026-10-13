from __future__ import annotations
from pydantic import BaseModel, Field

class SaleExtraction(BaseModel):
    monto: float | None = None
    moneda: str | None = None
    cliente_nombre: str | None = None
    # Nombre visible en el comprobante = pagador, no necesariamente comprador
    pagador_nombre: str | None = None
    productos_descripcion: str | None = None
    metodo_pago: str | None = None
    referencia_pago: str | None = None
    is_complete: bool = False
    next_question: str | None = None
    # shortcut: fecha_venta la pone la BD (now()); ampliar cuando se pida reporte por fecha libre
    fecha_venta: str | None = Field(default=None, description="ISO datetime si el mensaje la indica")
