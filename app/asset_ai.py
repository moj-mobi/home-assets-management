import base64
import json
import httpx

ASSET_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"}, "category": {"type": "string"},
        "manufacturer": {"type": "string"}, "model": {"type": "string"},
        "serial_number": {"type": "string"}, "notes": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["name", "category", "manufacturer", "model", "serial_number", "notes", "confidence"],
    "additionalProperties": False,
}

class GeminiVisionAnalyzer:
    def __init__(self, api_key: str, model: str = "gemini-3.7-flash"):
        self.api_key, self.model = api_key, model

    @staticmethod
    def _response_text(data: dict) -> str:
        # Some Interactions API releases expose this convenience field, while
        # current Gemini responses place the final text in a model_output step.
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        for step in reversed(data.get("steps", [])):
            if step.get("type") != "model_output":
                continue
            for item in step.get("content", []):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    return item["text"]
        raise KeyError("Gemini response does not contain model output text")

    async def analyze(self, images: list[tuple[bytes, str]]) -> dict:
        if not self.api_key:
            raise RuntimeError("AI prepoznava ni nastavljena. Skrbnik mora dodati GEMINI_API_KEY.")
        input_items = [{"type": "text", "text": "Prepoznaj domače sredstvo iz fotografij. Prepiši samo jasno vidno serijsko številko; ne ugibaj je. Ostale podatke smiselno dopolni. Odgovori v slovenščini."}]
        for data, mime in images:
            input_items.append({"type": "image", "data": base64.b64encode(data).decode("ascii"), "mime_type": mime})
        payload = {
            "model": self.model,
            "input": input_items,
            "response_format": {"type": "text", "mime_type": "application/json", "schema": ASSET_SCHEMA},
            "generation_config": {"thinking_level": "low"},
        }
        url = "https://generativelanguage.googleapis.com/v1beta/interactions"
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers={"x-goog-api-key": self.api_key}, json=payload)
            if response.status_code in {400, 401, 403}:
                message = response.json().get("error", {}).get("message", "Gemini je zavrnil zahtevo.")
                if "API key" in message: message = "Gemini API ključ ni veljaven."
                raise RuntimeError(message)
            response.raise_for_status()
        try:
            text = self._response_text(response.json())
            return json.loads(text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Gemini ni vrnil uporabnega strukturiranega odgovora.") from exc
