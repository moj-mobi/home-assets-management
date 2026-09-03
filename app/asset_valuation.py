import asyncio
import json
from datetime import datetime
from decimal import Decimal

import httpx
from sqlalchemy import select

from app.models import Asset, AssetValuationJob


VALUATION_DISCLAIMER = (
    "Starost, garancijski status in vrednosti so približne AI-ocene na podlagi modela, "
    "serijske številke in javno dostopnih virov. Niso dokazilo o nakupu, garanciji ali cenitvi."
)

VALUATION_SCHEMA = {
    "type": "object",
    "properties": {
        "model_year_min": {"type": ["integer", "null"]},
        "model_year_max": {"type": ["integer", "null"]},
        "estimated_original_price_eur": {"type": ["number", "null"]},
        "market_value_eu_min_eur": {"type": ["number", "null"]},
        "market_value_eu_max_eur": {"type": ["number", "null"]},
        "market_value_si_min_eur": {"type": ["number", "null"]},
        "market_value_si_max_eur": {"type": ["number", "null"]},
        "warranty_likelihood": {"type": "string", "enum": ["likely_active", "possibly_active", "likely_expired", "insufficient_data"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "url": {"type": "string"}, "region": {"type": "string"}}, "required": ["title", "url", "region"], "additionalProperties": False}},
    },
    "required": ["model_year_min", "model_year_max", "estimated_original_price_eur", "market_value_eu_min_eur", "market_value_eu_max_eur", "market_value_si_min_eur", "market_value_si_max_eur", "warranty_likelihood", "confidence", "rationale", "sources"],
    "additionalProperties": False,
}


class GeminiAssetValuator:
    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model

    async def estimate(self, asset: Asset) -> dict:
        api_key = self.api_key() if callable(self.api_key) else self.api_key
        if not api_key:
            raise RuntimeError("AI-cenitev ni nastavljena. Dodajte ključ v Nastavitve → AI / Gemini.")
        prompt = f"""Oceni domače sredstvo za osebno evidenco v Sloveniji.
Naziv: {asset.name}\nProizvajalec: {asset.manufacturer or 'neznan'}\nModel: {asset.model or 'neznan'}\nSerijska številka: {asset.serial_number or 'ni podana'}\nKategorija: {asset.category or 'neznana'}
Poišči preverljive javne vire. Oceni modelno leto, prvotno maloprodajno ceno z DDV v EUR ter trenutno rabljeno tržno vrednost posebej za EU in Slovenijo. Ne enači oglasne cene z doseženo prodajno ceno; če podatkov za Slovenijo ni, uporabi previdno prilagoditev EU in to pojasni. Garancijo označi samo kot verjetnost, saj datum nakupa in račun nista potrjena. Ne ugibaj natančnosti, ki je viri ne podpirajo."""
        payload = {"model": self.model, "input": prompt, "tools": [{"type": "google_search"}], "response_format": {"type": "text", "mime_type": "application/json", "schema": VALUATION_SCHEMA}, "generation_config": {"thinking_level": "low"}, "store": False}
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post("https://generativelanguage.googleapis.com/v1beta/interactions", headers={"x-goog-api-key": api_key}, json=payload)
            if response.status_code in {400, 401, 403}:
                message = response.json().get("error", {}).get("message", "Gemini je zavrnil cenitev.")
                raise RuntimeError("Gemini API ključ ni veljaven." if "API key" in message else message.replace(api_key, "[skrito]"))
            response.raise_for_status()
        data = response.json()
        text = data.get("output_text")
        if not isinstance(text, str):
            for step in reversed(data.get("steps", [])):
                if step.get("type") == "model_output":
                    for item in step.get("content", []):
                        if item.get("type") == "text": text = item.get("text"); break
                if isinstance(text, str): break
        if not isinstance(text, str): raise RuntimeError("Gemini ni vrnil strukturirane cenitve.")
        return json.loads(text)


def _money(value):
    return Decimal(str(value)).quantize(Decimal("0.01")) if value is not None else None


def process_valuation_batch(factory, valuator, batch_id: str) -> None:
    with factory() as db:
        job_ids = list(db.scalars(select(AssetValuationJob.id).where(AssetValuationJob.batch_id == batch_id, AssetValuationJob.status == "queued").order_by(AssetValuationJob.id)))
    for job_id in job_ids:
        with factory() as db:
            job = db.get(AssetValuationJob, job_id)
            if not job or job.status != "queued": continue
            job.status, job.started_at = "running", datetime.now(); db.commit()
            asset = db.get(Asset, job.asset_id)
            try:
                result = asyncio.run(valuator.estimate(asset))
                asset.estimated_model_year_min = result["model_year_min"]
                asset.estimated_model_year_max = result["model_year_max"]
                asset.estimated_purchase_price = _money(result["estimated_original_price_eur"])
                asset.estimated_market_value_eu_min = _money(result["market_value_eu_min_eur"])
                asset.estimated_market_value_eu_max = _money(result["market_value_eu_max_eur"])
                asset.estimated_market_value_si_min = _money(result["market_value_si_min_eur"])
                asset.estimated_market_value_si_max = _money(result["market_value_si_max_eur"])
                asset.estimated_warranty_likelihood = result["warranty_likelihood"]
                asset.estimate_confidence = Decimal(str(result["confidence"])).quantize(Decimal("0.001"))
                asset.estimate_sources_json = json.dumps(result["sources"], ensure_ascii=False)
                asset.estimate_rationale = result["rationale"]
                asset.estimated_at = datetime.now()
                job.status = "completed"
            except Exception as exc:
                job.status, job.error_message = "failed", str(exc)[:1000]
            job.completed_at = datetime.now(); db.commit()
