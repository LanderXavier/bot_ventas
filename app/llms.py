from __future__ import annotations
from .schemas import SaleExtraction

SYSTEM = (
    "Extraes ventas de mensajes de WhatsApp (texto o comprobante). "
    "El nombre visible en el comprobante es pagador_nombre, NO necesariamente cliente_nombre. "
    "No inventes datos ni asumas inferencias: lo no explícito va como null. "
    "Marca is_complete=true solo si hay monto y metodo_pago; si falta algo, "
    "pon next_question con UNA pregunta corta en español. Fusiona el borrador previo con el mensaje nuevo."
)

class GeminiExtractor:
    name = "gemini"
    def __init__(self, api_key: str, model: str = "gemini-3.8-flash"):
        from google import genai  # import tardío para no exigir la lib en tests con stub
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def extract(self, draft: dict, text: str, image: bytes | None,
                image_mime: str | None) -> SaleExtraction:
        from google.genai import types
        parts: list = [f"Borrador actual (JSON, puede estar vacío): {draft}\nMensaje nuevo: {text}\n{SYSTEM}"]
        if image:
            parts.append(types.Part.from_bytes(data=image, mime_type=image_mime or "image/jpeg"))
        resp = self._client.models.generate_content(
            model=self._model, contents=parts,
            config={"response_mime_type": "application/json",
                    "response_schema": SaleExtraction})
        return resp.parsed  # google-genai valida contra el schema Pydantic

class OpenRouterExtractor:
    """Extractor vía API compatible con OpenAI (OpenRouter, Groq...). Modelo gratis:
    OPENROUTER_MODEL=openrouter/free (acepta imágenes + JSON)."""
    name = "openrouter"
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "openrouter/free",
                 base_url: str = "https://openrouter.ai/api/v1"):
        import httpx
        self._http = httpx.Client(timeout=60)
        self._key = api_key
        self._model = model
        self._url = f"{base_url}/chat/completions"

    def extract(self, draft: dict, text: str, image: bytes | None,
                image_mime: str | None) -> SaleExtraction:
        import base64
        content: list = [{"type": "text",
            "text": f"Borrador actual (JSON, puede estar vacío): {draft}\nMensaje nuevo: {text}\n{SYSTEM} "
                    f"Responde SOLO con el JSON de la venta."}]
        if image:
            b64 = base64.b64encode(image).decode()
            content.append({"type": "image_url",
                "image_url": {"url": f"data:{image_mime or 'image/jpeg'};base64,{b64}"}})
        r = self._http.post(self._url,
            headers={"Authorization": f"Bearer {self._key}"},
            json={"model": self._model,
                  "messages": [{"role": "user", "content": content}],
                  "response_format": {"type": "json_object"}})
        r.raise_for_status()
        import json as _json
        data = _json.loads(r.json()["choices"][0]["message"]["content"])
        m = data.get("monto")
        if isinstance(m, str):  # formato latino: "7,00" o "1.250,00"
            m = m.strip().replace(" ", "")
            data["monto"] = float(m.replace(".", "").replace(",", ".") if "," in m else m)
        return SaleExtraction.model_validate(data)

class StubExtractor:
    """Extractor sin red para dev/test. LLM_PROVIDER=stub."""
    name = "stub"
    def extract(self, draft: dict, text: str, image: bytes | None,
                image_mime: str | None) -> SaleExtraction:
        import re
        data = dict(draft)
        low = (text or "").lower()
        m = re.search(r"\d+(?:[.,]\d+)?", low)
        if m and data.get("monto") is None:
            data["monto"] = float(m.group(0).replace(",", "."))
        if "efectivo" in low:
            data["metodo_pago"] = "efectivo"
        if "transferencia" in low or "comprobante" in low or image:
            data.setdefault("metodo_pago", "transferencia")
        complete = bool(data.get("monto") and data.get("metodo_pago"))
        return SaleExtraction(**data, is_complete=complete,
            next_question=None if complete else "¿Cuál fue el monto?")

# Registro global: cambiar de LLM = LLM_PROVIDER=nuevo + entrada aquí.
LLMS = {"gemini": GeminiExtractor, "stub": StubExtractor, "openrouter": OpenRouterExtractor, "groq": OpenRouterExtractor}

def get_extractor(name: str, api_key: str = "", model: str = ""):
    if name == "gemini":
        return GeminiExtractor(api_key, model or "gemini-3.8-flash")
    if name == "openrouter":
        return OpenRouterExtractor(api_key, model or "openrouter/free")
    if name == "groq":
        return OpenRouterExtractor(api_key, model or "qwen/qwen3.8-27b",
                                   "https://api.groq.com/openai/v1")
    try:
        return LLMS[name]()
    except KeyError:
        raise ValueError(f"LLM_PROVIDER desconocido: {name} (opciones: {sorted(LLMS)})")
