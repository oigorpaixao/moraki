import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Literal, Optional, Dict, Any, List, Tuple

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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

# -------------------------
# ✅ CORS (FIX para Vercel)
# -------------------------
# Por que isso resolve:
# - O browser faz um preflight OPTIONS antes do POST /v1/analyze
# - Se o backend não responder com Access-Control-Allow-Origin, o fetch dá "Failed to fetch"
#
# Configure no Render (Environment):
#   CORS_ORIGINS=https://moraki-7n33.vercel.app,http://localhost:3000
#   CORS_ORIGIN_REGEX=^https://.*\.vercel\.app$
#
# Obs: CORSMiddleware NÃO aceita "*.vercel.app" em allow_origins,
# por isso usamos allow_origin_regex para liberar qualquer preview da Vercel.

raw_origins = os.getenv("CORS_ORIGINS", "").strip()
origins = [o.strip() for o in raw_origins.split(",") if o.strip()] if raw_origins else []

origin_regex = os.getenv("CORS_ORIGIN_REGEX", "").strip() or r"^https://.*\.vercel\.app$"

# Importante: se você não usa cookies/sessão no fetch, deixe False.
# (allow_credentials=True + "*" costuma virar dor de cabeça no CORS)
app.add_middleware(
  CORSMiddleware,
  allow_origins=origins,                 # ex: ["https://moraki-7n33.vercel.app","http://localhost:3000"]
  allow_origin_regex=origin_regex,       # libera previews da Vercel
  allow_credentials=False,
  allow_methods=["GET", "POST", "OPTIONS"],
  allow_headers=["*"],
)

# --- Simple in-memory cache (MVP) ---
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "21600"))  # 6h default

def _cache_key(city: str, query: str) -> str:
  raw = f"{city.strip().lower()}|{query.strip().lower()}"
  return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _now_iso() -> str:
  return datetime.now(timezone.utc).isoformat()

def _now_ts() -> int:
  return int(datetime.now(timezone.utc).timestamp())

# --- News retrieval (MVP) ---
async def fetch_news(city: str, query: str) -> List[Dict[str, str]]:
  key = os.getenv("BING_NEWS_KEY")
  if not key:
    return []

  endpoint = os.getenv("BING_NEWS_ENDPOINT","https://api.bing.microsoft.com/v7.0/news/search")
  q = f"{query} {city}"
  params = {"q": q, "mkt": "pt-BR", "count": 5, "sortBy": "Date"}
  headers = {"Ocp-Apim-Subscription-Key": key}

  async with httpx.AsyncClient(timeout=12) as client:
    r = await client.get(endpoint, params=params, headers=headers)
    if r.status_code != 200:
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

# ----------------------------
# Scoring (Upgrade: place_score + confidence)
# ----------------------------

POSITIVE_KWS = {
  "inaugura", "inauguração", "invest", "investimento", "revitaliza", "revitalização",
  "obra", "melhoria", "reforma", "expansão", "novo", "abertura", "parque", "hospital",
  "metrô", "linha", "mobilidade", "segurança reforçada", "queda de crimes", "redução de crimes"
}

NEGATIVE_KWS = {
  "assalto", "roubo", "furto", "homicídio", "latrocínio", "tiroteio", "crime", "violência",
  "sequestro", "arrastão", "tráfico", "explosão", "incêndio", "acidente", "interdição",
  "protesto", "greve", "alagamento", "enchente", "deslizamento"
}

MONITOR_KWS = {
  "investiga", "investigação", "suspeita", "alerta", "risco", "denúncia", "aumento de casos",
  "surto", "dengue", "chikungunya", "zika", "intermitência", "instabilidade"
}

def _clamp(n: float, lo: int, hi: int) -> int:
  return int(max(lo, min(hi, round(n))))

def _address_specificity(query: str) -> float:
  """
  Retorna 0..1 com base em sinais de especificidade do endereço.
  Serve para CONFIANÇA, não para qualidade do lugar.
  """
  q = query.lower().strip()
  score = 0.0

  if any(ch.isdigit() for ch in q):
    score += 0.35
  if "," in q or "-" in q:
    score += 0.15

  import re
  if re.search(r"\b\d{5}-\d{3}\b", q) or re.search(r"\b\d{8}\b", q):
    score += 0.25

  if "http://" in q or "https://" in q:
    score += 0.25

  if any(t in q for t in ["bairro", "rua", "avenida", "av.", "travessa", "alameda", "praça"]):
    score += 0.10

  return max(0.0, min(1.0, score))

def _title_signal(title: str) -> Tuple[int, int, int]:
  t = (title or "").lower()
  pos = any(k in t for k in POSITIVE_KWS)
  neg = any(k in t for k in NEGATIVE_KWS)
  mon = any(k in t for k in MONITOR_KWS)

  # conservador: neg > monitor > pos
  if neg:
    return (0, 0, 1)
  if mon:
    return (0, 1, 0)
  if pos:
    return (1, 0, 0)
  return (0, 0, 0)

def compute_score(city: str, query: str, news: List[Dict[str, str]]) -> Dict[str, Any]:
  """
  Retorna:
  - place_score (0..100): qualidade do lugar (sinais, notícias)
  - confidence (0..100): confiança na análise (especificidade + evidência)
  - total (0..100): score final ponderado (place ajustado por confidence)
  - breakdown: por blocos (continua existindo pro front)
  """

  specificity = _address_specificity(query)

  pos_n = mon_n = neg_n = 0
  for n in (news or []):
    p, m, g = _title_signal(n.get("title", ""))
    pos_n += p
    mon_n += m
    neg_n += g

  news_count = len(news or [])

  # --------------------
  # 1) PLACE SCORE (não usa specificity)
  # --------------------
  base_place = {
    "Preço vs Mercado": 14,
    "Segurança & Risco": 14,
    "Infraestrutura & Mobilidade": 14,
    "Radar do Entorno": 14,
    "Estabilidade da Região": 14,
  }

  if news_count == 0:
    base_place["Radar do Entorno"] -= 4
    base_place["Estabilidade da Região"] -= 1
  else:
    base_place["Radar do Entorno"] += _clamp(min(4, news_count), 1, 4)

  base_place["Segurança & Risco"] -= _clamp(6 * neg_n + 2 * mon_n, 0, 18)
  base_place["Estabilidade da Região"] -= _clamp(4 * neg_n + 2 * mon_n, 0, 14)

  base_place["Infraestrutura & Mobilidade"] += _clamp(2 * pos_n, 0, 6)
  base_place["Radar do Entorno"] += _clamp(1 * pos_n, 0, 3)

  breakdown = {
    "Preço vs Mercado": _clamp(base_place["Preço vs Mercado"], 0, 25),
    "Segurança & Risco": _clamp(base_place["Segurança & Risco"], 0, 25),
    "Infraestrutura & Mobilidade": _clamp(base_place["Infraestrutura & Mobilidade"], 0, 20),
    "Radar do Entorno": _clamp(base_place["Radar do Entorno"], 0, 15),
    "Estabilidade da Região": _clamp(base_place["Estabilidade da Região"], 0, 15),
  }

  place_score = sum(breakdown.values())

  # --------------------
  # 2) CONFIDENCE
  # --------------------
  confidence = 35
  confidence += _clamp(35 * specificity, 0, 35)
  confidence += _clamp(5 * news_count, 0, 20)

  signal_strength = pos_n + mon_n + neg_n
  confidence += _clamp(4 * signal_strength, 0, 12)

  confidence = _clamp(confidence, 0, 100)

  # --------------------
  # 3) FINAL SCORE
  # --------------------
  multiplier = 0.60 + 0.40 * (confidence / 100.0)
  total = _clamp(place_score * multiplier, 0, 100)

  if total >= 80:
    label = "Boa decisão"
  elif total >= 65:
    label = "Boa decisão, com atenção"
  elif total >= 50:
    label = "Neutro (precisa de mais dados)"
  else:
    label = "Não recomendado"

  meta = {
    "place_score": place_score,
    "confidence": confidence,
    "multiplier": round(multiplier, 2),
    "specificity": round(specificity, 2),
    "news_count": news_count,
    "signals": {"positive": pos_n, "monitor": mon_n, "negative": neg_n},
  }

  return {
    "total": total,
    "label": label,
    "breakdown": breakdown,
    "place_score": place_score,
    "confidence": confidence,
    "meta": meta
  }

# --- OpenAI call (Responses API) ---
def get_openai_client() -> OpenAI:
  api_key = os.getenv("OPENAI_API_KEY")
  if not api_key:
    raise HTTPException(status_code=500, detail="OPENAI_API_KEY não configurada no backend.")
  return OpenAI(api_key=api_key)

def build_prompt(city: str, query: str, news: List[Dict[str, str]], score: Dict[str, Any]) -> str:
  news_text = "\n".join([
    f"- {n.get('title','')} ({n.get('datePublished','')}) — fonte: {n.get('source','')} — url: {n.get('url','')}"
    for n in news
  ]) or "(nenhuma notícia retornada pela API)"

  return f"""Você é um consultor neutro de decisão imobiliária. Gere um relatório objetivo em PT-BR.
NÃO invente dados. Se não houver dados suficientes, seja transparente e conservador.

Cidade piloto: {city}
Consulta do usuário: {query}

Pontuação (MVP):
- Score final (ponderado): {score['total']} / 100
- Score do lugar (place_score): {score.get('place_score')} / 100
- Confiança do diagnóstico (confidence): {score.get('confidence')} / 100
- Quebra por bloco: {json.dumps(score['breakdown'], ensure_ascii=False)}
- Metadados: {json.dumps(score.get('meta',{}), ensure_ascii=False)}

Notícias/eventos do entorno (últimos meses):
{news_text}

Tarefa:
1) Produza um resumo em 1 frase (summary) que explique a conclusão com equilíbrio e mencione o nível de confiança (alto/médio/baixo) sem inventar.
2) Liste 3–5 pontos fortes (positives), 2–4 pontos de atenção (cautions) e 0–3 riscos (risks).
3) Produza até 5 itens de radar (radar). Cada item deve ser baseado nas notícias fornecidas; se não houver notícias, retorne radar vazio [].

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
  try:
    return json.loads(text)
  except Exception:
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

  key = _cache_key(city, query)

  cached = _cache.get(key)
  if cached:
    if (_now_ts() - int(cached.get("_cached_at", 0))) <= CACHE_TTL_SECONDS:
      return cached["payload"]
    else:
      _cache.pop(key, None)

  news = await fetch_news(city, query)
  score = compute_score(city, query, news)

  client = get_openai_client()
  model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

  prompt = build_prompt(city, query, news, score)

  try:
    resp = client.responses.create(
      model=model,
      input=prompt,
      temperature=0.2,
    )

    out_text = ""
    for item in resp.output:
      if item.type == "output_text":
        out_text += item.text
    if not out_text:
      out_text = getattr(resp, "output_text", "") or ""

    parsed = safe_json_parse(out_text)
  except HTTPException:
    raise
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Falha ao gerar relatório (IA): {str(e)}")

  try:
    radar_items = parsed.get("radar", []) or []
    radar = [RadarItem(**it) for it in radar_items[:5]]
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

  _cache[key] = {"_cached_at": _now_ts(), "payload": result}
  return result
