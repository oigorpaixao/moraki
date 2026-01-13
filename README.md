# Decision Engine MVP (São Paulo)

Este repositório contém:
- **Frontend (Next.js)** na raiz (deploy no **Vercel**)
- **Backend (FastAPI)** em `/backend` (deploy no **Render**)

## 1) Rodar local (opcional)
### Frontend
```bash
npm install
npm run dev
```
Crie um arquivo `.env.local` com:
```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:10000
```

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export OPENAI_API_KEY="SUA_CHAVE"
uvicorn app.main:app --host 0.0.0.0 --port 10000
```

## 2) Deploy (produção) — Vercel + Render
- Frontend: Vercel aponta para este repositório (raiz)
- Backend: Render aponta para a pasta `/backend`

**Variáveis de ambiente:**
- No Render (backend):
  - `OPENAI_API_KEY`
  - `OPENAI_MODEL` (opcional, padrão `gpt-4o-mini`)
  - `CORS_ORIGINS` (ex.: `https://SEUAPP.vercel.app`)
  - `BING_NEWS_KEY` (opcional)
  - `BING_NEWS_ENDPOINT` (opcional)
- No Vercel (frontend):
  - `NEXT_PUBLIC_API_BASE_URL` = URL do Render (ex.: `https://seu-backend.onrender.com`)

## Endpoints
- `GET /health`
- `POST /v1/analyze` { "query": "...", "city": "São Paulo" }
