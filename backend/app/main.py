import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Literal, Optional, Dict, Any, List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# OpenAI official SDK (Responses API recommended for new projects)
from openai import OpenAI

APP_CITY_DEFAULT = "São Paulo"

# --- Models ---
class AnalyzeRequest(BaseModel):
  query: str = Field(..., min_length=3, max_length=500)
  city: str = Field(default=APP_CITY_DEFAULT, min_length=2, max_length=80)

class RadarItem(BaseModel):
  impact: Literal["positive","monitor","risk"]
  title: str
  date: Optional[str] = None
  why_it_matters: str
  source: Optional[str] = None

class AnalyzeResponse(BaseModel):
  request_id: str
  input: Dict[str, str]
  score: Dict[str, Any]
  summary: str
  positives: List[str]
  cautions: List[str]
  risks: List[str]
  radar: List[RadarItem]
  generated_at: str

# --- App ---
app = FastAPI(title="Decision Engine MVP", version="0.1.0")

# CORS for Vercel frontend
allowed = os.getenv("CORS_ORIGINS","*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed] if allowed else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Simple in-memory cache (MVP) ---
# In production, move to Redis or Postgres table.
_cache: Dict[str, Dict[str, Any]] = {}

def _cache_key(city: str, query: str) -> str:
  raw = f"{city.strip().lower()}|{query.strip().lower()}"
  return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _now_iso() -> str:
  return datetime.now(timezone.utc).isoformat()

# --- News retrieval (MVP) ---
# For the MVP we support 2 modes:
# 1) If BING_NEWS_KEY is set, fetch via Bing News Search endpoint.
# 2) Otherwise, return an empty list and let the LLM create a conservative 'no items found' output.
async def fetch_news(city: str, query: str) -> List[Dict[str, str]]:
  key = os.getenv("BING_NEWS_KEY")
  if not key:
    return []

  # Bing News Search API (endpoint can vary by Azure configuration).
  # We'll use the public endpoint format; if you use Azure, you may need to adjust.
  endpoint = os.getenv("BING_NEWS_ENDPOINT","https://api.bing.microsoft.com/v7.0/news/search")
  q = f"{query} {city}"
  params = {"q": q, "mkt": "pt-BR", "count": 5, "sortBy": "Date"}
  headers = {"Ocp-Apim-Subscription-Key": key}

  async with httpx.AsyncClient(timeout=12) as client:
    r = await client.get(endpoint, params=params, headers=headers)
    if r.status_code != 200:
      # Don't fail the whole analysis due to news API. Just return empty.
      return []
    data = r.json()
    items = []
    for it in data.get("value", [])[:5]:
      items.append({
        "title": it.get("name","").strip(),
        "url": it.get("url","").strip(),
        "datePublished": it.get("datePublished","").strip(),
        "source": (it.get("provider",[{}])[0].get("name","") if it.get("provider") else "")
      })
    return items

# --- Scoring (MVP heuristic) ---
def compute_score_stub() -> Dict[str, Any]:
  # MVP placeholder: we return a neutral baseline that the LLM can explain.
  breakdown = {
    "Preço vs Mercado": 18,
    "Segurança & Risco": 15,
    "Infraestrutura & Mobilidade": 16,
    "Radar do Entorno": 12,
    "Estabilidade da Região": 8
  }
  total = sum(breakdown.values())
  label = "Boa decisão, com atenção" if total >= 55 else "Não recomendado"
  return {"total": total, "label": label, "breakdown": breakdown}

# --- OpenAI call (Responses API) ---
def get_openai_client() -> OpenAI:
  api_key = os.getenv("OPENAI_API_KEY")
  if not api_key:
    raise HTTPException(status_code=500, detail="OPENAI_API_KEY não configurada no backend.")
  return OpenAI(api_key=api_key)

def build_prompt(city: str, query: str, news: List[Dict[str, str]], score: Dict[str, Any]) -> str:
  # Keep prompt deterministic, safe, and explicit about unknowns.
  news_text = "\n".join([f"- {n.get('title','')} ({n.get('datePublished','')}) — fonte: {n.get('source','')} — url: {n.get('url','')}" for n in news]) or "(nenhuma notícia retornada pela API)"
  return f"""Você é um consultor neutro de decisão imobiliária. Gere um relatório objetivo em PT-BR.
NÃO invente dados. Se não houver dados suficientes, seja transparente e conservador.

Cidade piloto: {city}
Consulta do usuário: {query}

Pontuação preliminar (heurística do MVP):
- Total: {score['total']} / 100
- Quebra por bloco: {json.dumps(score['breakdown'], ensure_ascii=False)}

Notícias/eventos do entorno (últimos meses):
{news_text}

Tarefa:
1) Produza um resumo em 1 frase (summary) que explique a conclusão com equilíbrio.
2) Liste 3–5 pontos fortes (positives), 2–4 pontos de atenção (cautions) e 0–3 riscos (risks).
3) Produza até 5 itens de radar (radar). Cada item deve ser baseado nas notícias fornecidas; se não houver notícias, retorne radar vazio [].
   - impact: "positive" | "monitor" | "risk"
   - title: título curto
   - date: data (se disponível)
   - why_it_matters: 1–2 frases objetivas
   - source: nome da fonte (se disponível)

Responda SOMENTE no formato JSON válido, com estas chaves exatas:
{{
  "summary": string,
  "positives": string[],
  "cautions": string[],
  "risks": string[],
  "radar": [{{"impact":"positive|monitor|risk","title":string,"date":string?,"why_it_matters":string,"source":string?}}]
}}
""".strip()

def safe_json_parse(text: str) -> Dict[str, Any]:
  # Try direct parse; if fails, attempt to extract first JSON object.
  try:
    return json.loads(text)
  except Exception:
    m = None
    # Find first {...} block
    import re
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
      return json.loads(m.group(0))
    raise

@app.get("/health")
def health():
  return {"ok": True, "time": _now_iso()}

@app.post("/v1/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
  city = req.city.strip() or APP_CITY_DEFAULT
  query = req.query.strip()

  # cache
  key = _cache_key(city, query)
  if key in _cache:
    return _cache[key]

  score = compute_score_stub()
  news = await fetch_news(city, query)

  client = get_openai_client()
  model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # adjustable

  prompt = build_prompt(city, query, news, score)

  try:
    resp = client.responses.create(
      model=model,
      input=prompt,
      temperature=0.2,
    )
    # Extract text output (Responses API)
    out_text = ""
    for item in resp.output:
      if item.type == "output_text":
        out_text += item.text
    if not out_text:
      # Some SDK versions return output_text via resp.output_text
      out_text = getattr(resp, "output_text", "") or ""

    parsed = safe_json_parse(out_text)
  except HTTPException:
    raise
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Falha ao gerar relatório (IA): {str(e)}")

  # normalize and validate
  try:
    radar_items = parsed.get("radar", []) or []
    radar = []
    for it in radar_items[:5]:
      radar.append(RadarItem(**it))
  except Exception:
    radar = []

  result = AnalyzeResponse(
    request_id=key[:12],
    input={"query": query, "city": city},
    score=score,
    summary=str(parsed.get("summary","")).strip() or "Relatório gerado.",
    positives=[str(x).strip() for x in (parsed.get("positives",[]) or [])][:5],
    cautions=[str(x).strip() for x in (parsed.get("cautions",[]) or [])][:5],
    risks=[str(x).strip() for x in (parsed.get("risks",[]) or [])][:5],
    radar=radar,
    generated_at=_now_iso()
  ).model_dump()

  _cache[key] = result
  return result
