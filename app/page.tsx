"use client";

import { useMemo, useState } from "react";

type AnalyzeResponse = {
  request_id: string;
  input: { query: string; city: string };
  score: {
    total: number;
    label: string;
    breakdown: Record<string, number>;
    place_score?: number;
    confidence?: number;
    meta?: Record<string, any>;
  };
  summary: string;
  positives: string[];
  cautions: string[];
  risks: string[];
  radar: Array<{
    impact: "positive" | "monitor" | "risk";
    title: string;
    date?: string;
    why_it_matters: string;
    source?: string;
  }>;
  generated_at: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "";

function badgeByLabel(label?: string, fallbackScore?: number) {
  const l = (label || "").toLowerCase();

  if (l.includes("boa decisão") && !l.includes("atenção")) {
    return { text: "Boa decisão", color: "#0f766e" };
  }
  if (l.includes("atenção") || (typeof fallbackScore === "number" && fallbackScore >= 65)) {
    return { text: "Boa decisão, com atenção", color: "#a16207" };
  }
  if (l.includes("neutro")) {
    return { text: "Neutro (precisa de mais dados)", color: "#64748b" };
  }
  return { text: "Não recomendado", color: "#b91c1c" };
}

function confidenceInfo(conf?: number) {
  if (typeof conf !== "number") return { text: "—", color: "#64748b" };
  if (conf >= 75) return { text: "Alta", color: "#0f766e" };
  if (conf >= 50) return { text: "Média", color: "#a16207" };
  return { text: "Baixa", color: "#b91c1c" };
}

function ProgressBar({ value }: { value: number }) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div style={{ height: 8, borderRadius: 999, background: "#0b1220", border: "1px solid #334155", overflow: "hidden" }}>
      <div style={{ width: `${v}%`, height: "100%", background: "#60a5fa" }} />
    </div>
  );
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const badgeInfo = useMemo(() => {
    if (!data) return null;
    return badgeByLabel(data.score.label, data.score.total);
  }, [data]);

  const conf = data?.score?.confidence;
  const placeScore = data?.score?.place_score;
  const confMeta = useMemo(() => confidenceInfo(conf), [conf]);

  async function onAnalyze() {
    setError(null);
    setData(null);

    const q = query.trim();
    if (!q) {
      setError("Cole um endereço ou link do anúncio.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/v1/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, city: "São Paulo" }),
      });

      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || `Erro HTTP ${res.status}`);
      }

      const json = (await res.json()) as AnalyzeResponse;
      setData(json);
    } catch (e: any) {
      setError(e?.message || "Erro ao analisar.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ minHeight: "100vh", background: "#0b0f14", color: "#e5e7eb" }}>
      <div style={{ maxWidth: 980, margin: "0 auto", padding: "48px 20px" }}>
        <header style={{ marginBottom: 32 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 10, height: 10, borderRadius: 999, background: "#60a5fa" }} />
            <span style={{ letterSpacing: 1.5, fontSize: 12, color: "#9ca3af" }}>DECISION ENGINE (MVP)</span>
          </div>

          <h1 style={{ fontSize: 44, lineHeight: 1.1, margin: "14px 0 10px" }}>
            Antes de comprar um imóvel, entenda o que ninguém te conta sobre o lugar.
          </h1>

          <p style={{ margin: 0, fontSize: 16, color: "#9ca3af", maxWidth: 760 }}>
            Analisamos dados públicos, infraestrutura, segurança e contexto urbano para apoiar sua decisão — não substitui avaliação técnica.
          </p>
        </header>

        {/* Search */}
        <section style={{ background: "#0f172a", border: "1px solid #1f2937", borderRadius: 16, padding: 18 }}>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Cole o endereço ou link do anúncio"
              style={{
                flex: "1 1 520px",
                padding: "14px 14px",
                borderRadius: 12,
                border: "1px solid #334155",
                background: "#0b1220",
                color: "#e5e7eb",
                outline: "none",
                fontSize: 14,
              }}
            />

            <button
              onClick={onAnalyze}
              disabled={loading}
              style={{
                padding: "14px 16px",
                borderRadius: 12,
                border: "1px solid #334155",
                background: "#111827",
                color: "#e5e7eb",
                cursor: loading ? "not-allowed" : "pointer",
                minWidth: 170,
                fontWeight: 600,
              }}
            >
              {loading ? "Analisando..." : "Analisar endereço"}
            </button>
          </div>

          <div style={{ marginTop: 10, color: "#94a3b8", fontSize: 12 }}>
            Não indicamos imóveis. Não vendemos anúncios. Quanto mais específico o endereço, melhor a análise.
          </div>

          {error && (
            <div
              style={{
                marginTop: 14,
                background: "#1f2937",
                border: "1px solid #374151",
                padding: 12,
                borderRadius: 12,
                color: "#fecaca",
              }}
            >
              {error}
            </div>
          )}
        </section>

        {/* What you get (block 2) */}
        <section style={{ marginTop: 14, background: "#0f172a", border: "1px solid #1f2937", borderRadius: 16, padding: 18 }}>
          <div style={{ fontWeight: 800, marginBottom: 10 }}>O que você recebe nessa análise</div>

          <ul style={{ margin: 0, paddingLeft: 18, color: "#cbd5e1", display: "grid", gap: 8, fontSize: 14 }}>
            <li>
              <span style={{ fontWeight: 700, color: "#e5e7eb" }}>Nota final (0–100)</span> para decisão rápida
            </li>
            <li>
              <span style={{ fontWeight: 700, color: "#e5e7eb" }}>Qualidade do lugar (place_score)</span> separada da{" "}
              <span style={{ fontWeight: 700, color: "#e5e7eb" }}>confiança</span> da análise
            </li>
            <li>
              <span style={{ fontWeight: 700, color: "#e5e7eb" }}>Preço vs mercado</span> (sinal de oportunidade ou risco)
            </li>
            <li>
              <span style={{ fontWeight: 700, color: "#e5e7eb" }}>Segurança & risco</span> (alertas e pontos de atenção)
            </li>
            <li>
              <span style={{ fontWeight: 700, color: "#e5e7eb" }}>Infraestrutura & mobilidade</span> (acesso, serviços e deslocamento)
            </li>
            <li>
              <span style={{ fontWeight: 700, color: "#e5e7eb" }}>Radar do entorno</span> (contexto urbano e sinais recentes)
            </li>
            <li>
              <span style={{ fontWeight: 700, color: "#e5e7eb" }}>Resumo final</span> com prós e cuidados antes de decidir
            </li>
          </ul>

          <p style={{ marginTop: 12, marginBottom: 0, color: "#94a3b8", fontSize: 12 }}>
            Usamos dados públicos e inferências. Isso não substitui vistoria técnica, jurídica ou laudos.
          </p>
        </section>

        {loading && (
          <section style={{ marginTop: 18, background: "#0f172a", border: "1px solid #1f2937", borderRadius: 16, padding: 18 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Preparando seu relatório…</div>
            <div style={{ color: "#9ca3af", fontSize: 14 }}>
              • Analisando preço da região…<br />
              • Verificando sinais de segurança…<br />
              • Buscando notícias do entorno…<br />
              • Gerando síntese e score…
            </div>
          </section>
        )}

        {data && (
          <section style={{ marginTop: 18, display: "grid", gap: 14 }}>
            <div style={{ background: "#0f172a", border: "1px solid #1f2937", borderRadius: 16, padding: 18 }}>
              <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 6 }}>
                {data.input.city} • {new Date(data.generated_at).toLocaleString("pt-BR")}
              </div>

              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
                <div style={{ fontSize: 14, color: "#9ca3af" }}>Consulta</div>
                <div style={{ fontSize: 14, color: "#e5e7eb", maxWidth: 760, textAlign: "right" }}>{data.input.query}</div>
              </div>

              <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
                <div style={{ fontSize: 48, fontWeight: 800 }}>{data.score.total}</div>

                <div style={{ marginTop: 4, flex: "1 1 520px" }}>
                  <div
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "6px 10px",
                      borderRadius: 999,
                      border: `1px solid ${badgeInfo?.color}`,
                      color: badgeInfo?.color,
                    }}
                  >
                    <span style={{ fontWeight: 700 }}>{badgeInfo?.text}</span>
                    <span style={{ color: "#9ca3af" }}>/ 100</span>
                  </div>

                  {/* NEW: place_score + confidence */}
                  <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 6 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                        <div style={{ color: "#cbd5e1", fontSize: 13 }}>
                          <span style={{ color: "#9ca3af" }}>Qualidade do lugar:</span>{" "}
                          <span style={{ fontWeight: 800 }}>{typeof placeScore === "number" ? placeScore : "—"}</span>
                          <span style={{ color: "#9ca3af" }}> / 100</span>
                        </div>

                        <div style={{ color: "#cbd5e1", fontSize: 13 }}>
                          <span style={{ color: "#9ca3af" }}>Confiança:</span>{" "}
                          <span style={{ fontWeight: 800 }}>{typeof conf === "number" ? conf : "—"}</span>
                          <span style={{ color: "#9ca3af" }}> / 100</span>{" "}
                          <span style={{ color: confMeta.color, fontWeight: 800 }}>({confMeta.text})</span>
                        </div>
                      </div>

                      {typeof conf === "number" && <ProgressBar value={conf} />}
                    </div>

                    <div style={{ color: "#d1d5db", fontSize: 15 }}>{data.summary}</div>
                  </div>
                </div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 14 }}>
              <Card title="Breakdown (MVP)">
                <SmallList items={Object.entries(data.score.breakdown).map(([k, v]) => `${k}: ${v} pts`)} />
              </Card>

              <Card title="Radar do Entorno (notícias e eventos)">
                {data.radar.length === 0 ? (
                  <div style={{ color: "#9ca3af" }}>Nenhum item relevante encontrado.</div>
                ) : (
                  <div style={{ display: "grid", gap: 10 }}>
                    {data.radar.map((n, idx) => (
                      <div key={idx} style={{ border: "1px solid #334155", borderRadius: 14, padding: 12, background: "#0b1220" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                          <div style={{ fontWeight: 700 }}>
                            {n.impact === "risk" ? "🔴" : n.impact === "monitor" ? "🟡" : "🟢"} {n.title}
                          </div>
                          {n.date && <div style={{ color: "#94a3b8", fontSize: 12 }}>{n.date}</div>}
                        </div>
                        <div style={{ color: "#d1d5db", marginTop: 6 }}>{n.why_it_matters}</div>
                        {n.source && <div style={{ color: "#94a3b8", fontSize: 12, marginTop: 6 }}>Fonte: {n.source}</div>}
                      </div>
                    ))}
                  </div>
                )}
              </Card>

              <Card title="Síntese final">
                <Grid3 positives={data.positives} cautions={data.cautions} risks={data.risks} />
              </Card>
            </div>
          </section>
        )}

        <footer style={{ marginTop: 42, color: "#6b7280", fontSize: 12 }}>
          MVP para validação (São Paulo). Este relatório não substitui avaliação técnica do imóvel.
        </footer>
      </div>
    </main>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "#0f172a", border: "1px solid #1f2937", borderRadius: 16, padding: 18 }}>
      <div style={{ fontWeight: 800, marginBottom: 10 }}>{title}</div>
      {children}
    </div>
  );
}

function SmallList({ items }: { items: string[] }) {
  return (
    <ul style={{ margin: 0, paddingLeft: 18, color: "#d1d5db" }}>
      {items.map((t, i) => (
        <li key={i} style={{ marginBottom: 6 }}>
          {t}
        </li>
      ))}
    </ul>
  );
}

function Grid3({ positives, cautions, risks }: { positives: string[]; cautions: string[]; risks: string[] }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
      <div style={{ border: "1px solid #334155", borderRadius: 14, padding: 12, background: "#0b1220" }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>✅ O que joga a favor</div>
        {positives.length ? <SmallList items={positives} /> : <div style={{ color: "#9ca3af" }}>—</div>}
      </div>

      <div style={{ border: "1px solid #334155", borderRadius: 14, padding: 12, background: "#0b1220" }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>⚠️ Onde ter cautela</div>
        {cautions.length ? <SmallList items={cautions} /> : <div style={{ color: "#9ca3af" }}>—</div>}
      </div>

      <div style={{ border: "1px solid #334155", borderRadius: 14, padding: 12, background: "#0b1220" }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>❌ Pontos críticos</div>
        {risks.length ? <SmallList items={risks} /> : <div style={{ color: "#9ca3af" }}>—</div>}
      </div>
    </div>
  );
}
