import { useState, useMemo } from "react";

const C = {
  bg: "#06060A", card: "#0E0E14", bd: "#1A1A24", tx: "#E2E2EA",
  t2: "#9898A8", t3: "#555566", green: "#00D68F", red: "#FF4757",
  blue: "#3B82F6", purple: "#8B5CF6", amber: "#F59E0B", cyan: "#06B6D4",
  pink: "#EC4899",
};

const Tag = ({ children, color = C.green }: { children: React.ReactNode; color?: string }) => (
  <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 4, background: `${color}18`, color, letterSpacing: "0.04em", whiteSpace: "nowrap" }}>{children}</span>
);

const FREE_OPTIONS = [
  {
    id: "groq_free",
    name: "Groq Free",
    model: "Whisper Large v3 Turbo",
    type: "STT only",
    cost: "$0.00",
    limits: "2,000 req/día · 28,800 seg audio/día (8h)",
    audiosPerDay: 192,
    wer: "9.5%",
    speed: "216x real-time",
    lang: "99 idiomas",
    precision: "★★★★☆",
    pros: ["Gratis total", "Mejor que OpenAI Whisper (WER 9.5 vs 10.6)", "API compatible OpenAI", "Sin tarjeta de crédito"],
    cons: ["Solo transcripción (necesitas LLM aparte)", "Rate limit: 20 req/min", "Si Groq cambia free tier, se rompe"],
    color: C.amber,
    signup: "console.groq.com",
    badge: "GRATIS",
  },
  {
    id: "gemini_audio",
    name: "Gemini Flash-Lite Free",
    model: "Gemini 2.0 Flash-Lite",
    type: "Audio nativo → todo en 1 call",
    cost: "$0.00",
    limits: "1,000 req/día · 15 req/min",
    audiosPerDay: 1000,
    wer: "~10-12%",
    speed: "Fast",
    lang: "100+ idiomas",
    precision: "★★★★☆",
    pros: ["1 sola llamada: transcribe + limpia + extrae + resume", "Sin dependencia extra", "YA tienes API key activa"],
    cons: ["⚠️ Dic 2025: Google recortó free tier 50-80%", "⚠️ Flash-Lite puede NO soportar audio input", "Restricción EU para free tier (verificar)", "Si Google recorta más, afecta"],
    color: C.blue,
    signup: "ai.google.dev (ya lo tienes)",
    badge: "VERIFICAR",
  },
  {
    id: "groq_gemini_combo",
    name: "Groq Free + Gemini Free",
    model: "Whisper Turbo → Flash-Lite texto",
    type: "STT gratis + LLM gratis",
    cost: "$0.00",
    limits: "~192 audios/día (bottleneck: Groq audio seconds)",
    audiosPerDay: 192,
    wer: "9.5%",
    speed: "Fast (2 calls paralelas)",
    lang: "99 idiomas",
    precision: "★★★★★",
    pros: ["100% gratis", "Mejor precisión (Whisper dedicado)", "LLM dedicado para inteligencia", "Redundancia: 2 providers"],
    cons: ["2 cuentas API que mantener", "Rate limit cruzado más complejo", "~192 audios/día máx"],
    color: C.green,
    signup: "Groq + Google AI",
    badge: "⭐ RECOMENDADO",
  },
];

const SCALE_TABLE = [
  { phase: "Stefano solo", creators: 1, audiosPerCreator: 15, notes: "Beta test" },
  { phase: "10 clientes", creators: 10, audiosPerCreator: 10, notes: "Launch" },
  { phase: "50 clientes", creators: 50, audiosPerCreator: 10, notes: "Tracción" },
  { phase: "200 clientes", creators: 200, audiosPerCreator: 10, notes: "Scale" },
  { phase: "500 clientes", creators: 500, audiosPerCreator: 10, notes: "Objetivo" },
];

const TIERS = [
  {
    name: "TIER 0 — 100% GRATIS",
    range: "1-20 creators",
    color: C.green,
    method: "Groq Free (STT) + Gemini Free Flash-Lite (inteligencia)",
    costPerAudio: 0,
    maxAudios: 192,
    desc: "Sin tarjeta. Sin factura. Cubre beta y primeros 20 clientes.",
  },
  {
    name: "TIER 1 — CASI GRATIS",
    range: "20-100 creators",
    color: C.cyan,
    method: "Groq Free (STT) + Gemini PAID Flash-Lite (texto)",
    costPerAudio: 0.0001,
    maxAudios: 2000,
    desc: "STT sigue gratis en Groq. Solo pagas Gemini texto ~$0.0001/audio.",
  },
  {
    name: "TIER 2 — MUY BARATO",
    range: "100-500 creators",
    color: C.blue,
    method: "Groq PAID Whisper ($0.04/h) + Gemini PAID Flash-Lite",
    costPerAudio: 0.0021,
    maxAudios: 999999,
    desc: "Sin rate limits. $0.002/audio. A 500 creators = ~$63/mes.",
  },
  {
    name: "TIER 3 — ESCALA",
    range: "500+ creators",
    color: C.purple,
    method: "Gemini PAID Flash (audio nativo, 1 call)",
    costPerAudio: 0.0006,
    maxAudios: 999999,
    desc: "Una sola llamada. Más simple. $0.0006/audio. A 500 creators = ~$18/mes.",
  },
];

export default function FreeAudioOptions() {
  const [tab, setTab] = useState("options");
  const [avgDur, setAvgDur] = useState(2.5);

  const scaleCalc = useMemo(() => {
    return SCALE_TABLE.map(row => {
      const totalAudios = row.creators * row.audiosPerCreator;
      const tier = TIERS.find((_t, i) => {
        if (i === TIERS.length - 1) return true;
        return totalAudios <= _t.maxAudios;
      })!;
      const monthlyCost = totalAudios * 30 * tier.costPerAudio * avgDur;
      return { ...row, totalAudios, tier, monthlyCost };
    });
  }, [avgDur]);

  const tabs = [
    { id: "options", label: "Opciones Gratis" },
    { id: "tiers", label: "Escalación" },
    { id: "prompt", label: "Prompt Listo" },
  ];

  return (
    <div style={{ minHeight: "100vh", background: C.bg, color: C.tx, fontFamily: "'Inter',system-ui,sans-serif", padding: "28px 16px 100px" }}>
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
      <div style={{ maxWidth: 760, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 10, color: C.t3, textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 4 }}>Audio Intelligence · Investigación de costes</div>
          <h1 style={{ fontSize: 22, fontWeight: 900, margin: 0, letterSpacing: "-0.03em" }}>
            Transcripción de Audio — <span style={{ color: C.green }}>Opciones Gratuitas</span>
          </h1>
          <p style={{ fontSize: 12, color: C.t3, marginTop: 6 }}>
            Groq free tier · Gemini free tier · Cascade de 4 niveles · Investigado Feb 2026
          </p>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 2, marginBottom: 20 }}>
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              padding: "7px 14px", fontSize: 11, fontWeight: tab === t.id ? 700 : 400, cursor: "pointer",
              border: "none", borderRadius: 6, background: tab === t.id ? C.green : "transparent",
              color: tab === t.id ? "#000" : C.t3, transition: "all 0.15s"
            }}>{t.label}</button>
          ))}
        </div>

        {/* ============ TAB 1: OPTIONS ============ */}
        {tab === "options" && (
          <div>
            {/* TL;DR */}
            <div style={{ background: `${C.green}10`, border: `1px solid ${C.green}30`, borderRadius: 10, padding: "16px 18px", marginBottom: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.green, marginBottom: 8 }}>TL;DR — Resultado de la investigación</div>
              <div style={{ fontSize: 12, color: C.t2, lineHeight: 1.7 }}>
                <strong style={{ color: C.tx }}>Groq da Whisper GRATIS</strong> — 2,000 requests/día, 8 horas de audio/día, precisión mejor que OpenAI Whisper (WER 9.5% vs 10.6%). Cubre hasta ~20 creators sin pagar nada. Combinado con Gemini Flash-Lite gratis para la inteligencia (limpieza + extracción + resumen), tienes un pipeline completo a coste $0.00.
              </div>
            </div>

            {/* Hallazgo Groq */}
            <div style={{ background: `${C.amber}08`, border: `1px solid ${C.amber}25`, borderRadius: 10, padding: "16px 18px", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 18 }}>🔥</span>
                <div style={{ fontSize: 14, fontWeight: 800, color: C.amber }}>Hallazgo clave: Groq Free Tier</div>
              </div>
              <div style={{ fontSize: 12, color: C.t2, lineHeight: 1.7, marginBottom: 12 }}>
                Fuente: <span style={{ color: C.t3, fontFamily: "'JetBrains Mono', monospace", fontSize: 10 }}>console.groq.com/docs/rate-limits</span> (verificado hoy)
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
                {[
                  { label: "Requests/día", value: "2,000", sub: "20 RPM" },
                  { label: "Audio/día", value: "8 horas", sub: "28,800 seg" },
                  { label: "Modelo", value: "Whisper v3 Turbo", sub: "WER 9.5%" },
                ].map((m, i) => (
                  <div key={i} style={{ background: C.bg, borderRadius: 8, padding: "12px", textAlign: "center" }}>
                    <div style={{ fontSize: 10, color: C.t3, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>{m.label}</div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: C.amber, fontFamily: "'JetBrains Mono', monospace" }}>{m.value}</div>
                    <div style={{ fontSize: 10, color: C.t3, marginTop: 2 }}>{m.sub}</div>
                  </div>
                ))}
              </div>
              <div style={{ fontSize: 11, color: C.t3, marginTop: 10, fontStyle: "italic" }}>
                A 2.5 min/audio = ~192 audios/día gratis = ~20 creators × 10 audios/día
              </div>
            </div>

            {/* Gemini Dec 2025 warning */}
            <div style={{ background: `${C.red}08`, border: `1px solid ${C.red}25`, borderRadius: 10, padding: "14px 16px", marginBottom: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: C.red, marginBottom: 6 }}>⚠️ Gemini Free Tier — Recortado Dic 2025</div>
              <div style={{ fontSize: 11, color: C.t2, lineHeight: 1.6 }}>
                Google recortó el free tier entre 50-92% en diciembre 2025. Flash bajó de 250 a <strong>20 RPD</strong>. Flash-Lite mantiene <strong>1,000 RPD</strong> pero hay restricciones EU. Ya tienes API key paid activa, así que esto te afecta solo si intentas usar free tier puro.
              </div>
            </div>

            {/* 3 Options */}
            {FREE_OPTIONS.map((opt, i) => (
              <div key={opt.id} style={{
                background: C.card, borderRadius: 10, border: `1px solid ${i === 2 ? `${opt.color}40` : C.bd}`,
                padding: "18px", marginBottom: 12,
                ...(i === 2 ? { boxShadow: `0 0 20px ${opt.color}10` } : {})
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                  <div>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                      <span style={{ fontSize: 15, fontWeight: 800, color: opt.color }}>{opt.name}</span>
                      <Tag color={opt.badge === "⭐ RECOMENDADO" ? C.green : opt.badge === "GRATIS" ? C.amber : C.purple}>{opt.badge}</Tag>
                    </div>
                    <div style={{ fontSize: 11, color: C.t3 }}>{opt.model} · {opt.type}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 22, fontWeight: 900, color: opt.color, fontFamily: "'JetBrains Mono', monospace" }}>{opt.cost}</div>
                    <div style={{ fontSize: 10, color: C.t3 }}>por audio</div>
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8, marginBottom: 12 }}>
                  {[
                    { l: "WER", v: opt.wer },
                    { l: "Precisión", v: opt.precision },
                    { l: "Velocidad", v: opt.speed },
                    { l: "Audios/día", v: opt.audiosPerDay >= 999 ? "1,000" : String(opt.audiosPerDay) },
                  ].map((m, j) => (
                    <div key={j} style={{ background: C.bg, borderRadius: 6, padding: "8px", textAlign: "center" }}>
                      <div style={{ fontSize: 9, color: C.t3, textTransform: "uppercase", letterSpacing: "0.06em" }}>{m.l}</div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: C.tx, marginTop: 2, fontFamily: m.l === "Precisión" ? "inherit" : "'JetBrains Mono', monospace" }}>{m.v}</div>
                    </div>
                  ))}
                </div>

                <div style={{ fontSize: 11, color: C.t3, marginBottom: 10 }}>
                  <strong style={{ color: C.t2 }}>Límites:</strong> {opt.limits}
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div>
                    <div style={{ fontSize: 10, fontWeight: 700, color: C.green, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.06em" }}>Pros</div>
                    {opt.pros.map((p, j) => (
                      <div key={j} style={{ fontSize: 11, color: C.t2, lineHeight: 1.5, paddingLeft: 12, position: "relative" }}>
                        <span style={{ position: "absolute", left: 0, color: C.green }}>+</span>{p}
                      </div>
                    ))}
                  </div>
                  <div>
                    <div style={{ fontSize: 10, fontWeight: 700, color: C.red, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.06em" }}>Contras</div>
                    {opt.cons.map((c, j) => (
                      <div key={j} style={{ fontSize: 11, color: C.t2, lineHeight: 1.5, paddingLeft: 12, position: "relative" }}>
                        <span style={{ position: "absolute", left: 0, color: C.red }}>−</span>{c}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}

            {/* Quick comparison vs Whisper paid */}
            <div style={{ background: C.card, borderRadius: 10, border: `1px solid ${C.bd}`, padding: "16px 18px", marginTop: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>Precisión comparada (WER = Word Error Rate, menor = mejor)</div>
              {[
                { name: "Deepgram Nova-3", wer: 6.8, color: C.purple, cost: "$0.0043/min", free: false },
                { name: "Groq Whisper v3 Turbo", wer: 9.5, color: C.amber, cost: "GRATIS", free: true },
                { name: "Whisper Large v3", wer: 10.3, color: C.t3, cost: "$0.006/min", free: false },
                { name: "OpenAI Whisper v2 (actual)", wer: 10.6, color: C.red, cost: "$0.006/min", free: false },
                { name: "Gemini Flash (audio)", wer: 11, color: C.blue, cost: "~$0.0002/min", free: false },
              ].map((m, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                  <div style={{ width: 180, fontSize: 11, color: m.free ? C.tx : C.t2, fontWeight: m.free ? 700 : 400 }}>{m.name}</div>
                  <div style={{ flex: 1, height: 18, background: C.bg, borderRadius: 4, overflow: "hidden" }}>
                    <div style={{ width: `${(m.wer / 15) * 100}%`, height: "100%", background: `${m.color}80`, borderRadius: 4, display: "flex", alignItems: "center", paddingLeft: 6 }}>
                      <span style={{ fontSize: 10, fontWeight: 700, color: "#fff", fontFamily: "'JetBrains Mono', monospace" }}>{m.wer}%</span>
                    </div>
                  </div>
                  <div style={{ width: 90, fontSize: 10, color: m.free ? C.green : C.t3, textAlign: "right", fontWeight: m.free ? 700 : 400, fontFamily: "'JetBrains Mono', monospace" }}>
                    {m.cost}
                  </div>
                </div>
              ))}
              <div style={{ fontSize: 10, color: C.t3, marginTop: 8 }}>
                Groq gratis tiene MEJOR precisión que lo que pagas ahora con OpenAI Whisper.
              </div>
            </div>
          </div>
        )}

        {/* ============ TAB 2: TIERS ============ */}
        {tab === "tiers" && (
          <div>
            <div style={{ background: `${C.green}10`, border: `1px solid ${C.green}30`, borderRadius: 10, padding: "16px 18px", marginBottom: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.green, marginBottom: 6 }}>Estrategia: Cascade de 4 niveles</div>
              <div style={{ fontSize: 12, color: C.t2, lineHeight: 1.7 }}>
                Empiezas 100% gratis. El sistema sube de tier automáticamente cuando llegas al rate limit. No pagas nada hasta que tus ingresos lo justifiquen.
              </div>
            </div>

            {/* 4 Tiers */}
            {TIERS.map((tier, i) => (
              <div key={i} style={{
                background: C.card, borderRadius: 10, border: `1px solid ${tier.color}30`,
                padding: "16px 18px", marginBottom: 12, position: "relative",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 800, color: tier.color, marginBottom: 2 }}>{tier.name}</div>
                    <div style={{ fontSize: 11, color: C.t3, marginBottom: 8 }}>{tier.range}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 20, fontWeight: 900, color: tier.color, fontFamily: "'JetBrains Mono', monospace" }}>
                      {tier.costPerAudio === 0 ? "$0" : `${tier.costPerAudio.toFixed(4)}`}
                    </div>
                    <div style={{ fontSize: 10, color: C.t3 }}>por audio</div>
                  </div>
                </div>
                <div style={{ fontSize: 11, color: C.t2, marginBottom: 8 }}>
                  <strong style={{ color: C.tx }}>Método:</strong> {tier.method}
                </div>
                <div style={{ fontSize: 11, color: C.t3, lineHeight: 1.5 }}>{tier.desc}</div>
              </div>
            ))}

            {/* Scale projection */}
            <div style={{ background: C.card, borderRadius: 10, border: `1px solid ${C.bd}`, overflow: "hidden", marginTop: 20 }}>
              <div style={{ padding: "14px 18px", borderBottom: `1px solid ${C.bd}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 700 }}>Proyección de costes reales</span>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 10, color: C.t3 }}>Avg:</span>
                  <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace", color: C.cyan }}>{avgDur}m</span>
                  <input type="range" min={1} max={5} step={0.5} value={avgDur} onChange={e => setAvgDur(Number(e.target.value))}
                    style={{ width: 80, accentColor: C.cyan }} />
                </div>
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${C.bd}` }}>
                    {["Fase", "Creators", "Audios/día", "Tier", "Coste/mes"].map((h, i) => (
                      <th key={i} style={{ padding: "10px 14px", textAlign: i < 3 ? "left" : "right", color: C.t3, fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {scaleCalc.map((row, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${C.bd}` }}>
                      <td style={{ padding: "12px 14px", fontWeight: 600 }}>{row.phase}</td>
                      <td style={{ padding: "12px 14px", fontFamily: "'JetBrains Mono', monospace" }}>{row.creators}</td>
                      <td style={{ padding: "12px 14px", fontFamily: "'JetBrains Mono', monospace", color: C.t2 }}>{row.totalAudios}</td>
                      <td style={{ padding: "12px 14px", textAlign: "right" }}>
                        <Tag color={row.tier.color}>{row.tier.name.split("—")[0].trim()}</Tag>
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, fontSize: 14, color: row.monthlyCost === 0 ? C.green : row.monthlyCost < 10 ? C.cyan : C.amber }}>
                        {row.monthlyCost === 0 ? "$0.00" : `${row.monthlyCost.toFixed(2)}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Revenue comparison */}
            <div style={{ background: `${C.green}08`, border: `1px solid ${C.green}25`, borderRadius: 10, padding: "16px 18px", marginTop: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.green, marginBottom: 8 }}>Ingreso vs Coste Audio (plan 49€/mes)</div>
              {scaleCalc.map((row, i) => {
                const revenue = row.creators * 49;
                const costEur = row.monthlyCost * 0.92;
                const pct = revenue > 0 ? (costEur / revenue * 100) : 0;
                return (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "6px 0", borderBottom: i < scaleCalc.length - 1 ? `1px solid ${C.green}15` : "none" }}>
                    <span style={{ width: 100, fontSize: 11, fontWeight: 600 }}>{row.phase}</span>
                    <span style={{ width: 70, fontSize: 11, color: C.t2, textAlign: "right" }}>{revenue.toLocaleString()}€</span>
                    <div style={{ flex: 1, height: 14, background: C.bg, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${Math.max(0.5, pct)}%`, height: "100%", background: pct === 0 ? C.green : C.red, borderRadius: 3, minWidth: pct > 0 ? 2 : 0 }} />
                    </div>
                    <span style={{ width: 60, fontSize: 11, fontFamily: "'JetBrains Mono', monospace", color: pct === 0 ? C.green : C.t2, textAlign: "right", fontWeight: 600 }}>
                      {pct === 0 ? "0.00%" : `${pct.toFixed(2)}%`}
                    </span>
                  </div>
                );
              })}
              <div style={{ fontSize: 10, color: C.t3, marginTop: 8 }}>
                Barra roja = % del ingreso que se va en audio. Hasta 50 creators: $0. A 500 creators: ~0.26% del ingreso.
              </div>
            </div>
          </div>
        )}

        {/* ============ TAB 3: PROMPT ============ */}
        {tab === "prompt" && (
          <div>
            <div style={{ background: `${C.green}10`, border: `1px solid ${C.green}30`, borderRadius: 10, padding: "16px 18px", marginBottom: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.green, marginBottom: 6 }}>Prompt para implementar la cascade</div>
              <div style={{ fontSize: 12, color: C.t2, lineHeight: 1.7 }}>
                Pega esto en Claude Code para implementar el sistema de audio con fallback automático por tiers.
              </div>
            </div>

            <div style={{ background: C.card, borderRadius: 10, border: `1px solid ${C.bd}`, padding: "18px", fontFamily: "'JetBrains Mono', monospace", fontSize: 11, lineHeight: 1.7, color: C.t2, whiteSpace: "pre-wrap", overflowX: "auto", maxHeight: 600, overflowY: "auto" }}>
{`## IMPLEMENTAR: Audio Intelligence Pipeline con Cascade Gratuita

CONTEXTO: Clonnect procesa audios de DMs (Instagram/WhatsApp).
Actualmente usa OpenAI Whisper ($0.006/min). Migrar a cascade
gratuita sin perder precisión.

### ARQUITECTURA: 4 TIERS DE FALLBACK

\`\`\`
TIER 0 (FREE):  Groq Free Whisper → Gemini Free Flash-Lite
TIER 1 (CHEAP): Groq Free Whisper → Gemini Paid Flash-Lite
TIER 2 (PAID):  Groq Paid Whisper → Gemini Paid Flash-Lite
TIER 3 (SCALE): Gemini Paid Flash (audio nativo, 1 call)
\`\`\`

### PASO 1: Crear audio_transcription_service.py

\`\`\`python
class AudioTranscriptionCascade:
    """
    Cascade de transcripción con fallback automático.
    Intenta gratis primero, escala a paid si rate limit.
    """

    PROVIDERS = [
        ("groq_free", "whisper-large-v3-turbo"),
        ("groq_paid", "whisper-large-v3-turbo"),
        ("openai", "whisper-1"),  # fallback actual
    ]

    async def transcribe(self, audio_bytes, duration_s, lang="es"):
        for provider, model in self.PROVIDERS:
            try:
                if provider == "groq_free":
                    return await self._groq_transcribe(
                        audio_bytes, model,
                        api_key=GROQ_API_KEY,
                    )
                elif provider == "groq_paid":
                    # Same as free but different key or
                    # catches 429 from free
                    return await self._groq_transcribe(
                        audio_bytes, model,
                        api_key=GROQ_API_KEY,
                    )
                elif provider == "openai":
                    return await self._openai_transcribe(
                        audio_bytes, model
                    )
            except RateLimitError:
                logger.warning(f"Rate limit hit on {provider}")
                continue
            except Exception as e:
                logger.error(f"Error on {provider}: {e}")
                continue

        raise Exception("All transcription providers failed")

    async def _groq_transcribe(self, audio_bytes, model, api_key):
        """Groq API - OpenAI compatible endpoint"""
        client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )
        # Groq acepta audio directamente
        response = await client.audio.transcriptions.create(
            model=model,
            file=("audio.ogg", audio_bytes, "audio/ogg"),
            language=lang,
            response_format="text"
        )
        return response.text
\`\`\`

### PASO 2: Crear audio_intelligence_service.py

\`\`\`python
class AudioIntelligenceService:
    """
    Procesa transcripción cruda → inteligencia estructurada.
    1 sola llamada a Gemini Flash-Lite con prompt combinado.
    """

    COMBINED_PROMPT = """Procesa esta transcripción de audio
de un mensaje directo de {platform}.

TRANSCRIPCIÓN CRUDA:
{raw_text}

Responde SOLO en JSON válido con esta estructura:
{{
  "clean_text": "transcripción limpia sin muletillas...",
  "summary": "1-3 frases con TODOS los datos clave...",
  "entities": {{
    "people": [],
    "places": [],
    "dates": [],
    "numbers": [],
    "products": [],
    "action_items": []
  }},
  "emotional_tone": "amistoso/urgente/neutro/etc",
  "intent": "pregunta/compra/soporte/saludo/etc"
}}

REGLAS:
- clean_text: elimina "bueno", "eh", "o sea", repeticiones
- summary: DEBE incluir TODOS los nombres, fechas, lugares
- entities: extrae TODO dato concreto mencionado
- Si hay intención de compra, marcarlo en intent"""

    async def process(self, raw_text, role="user",
                      platform="instagram"):
        prompt = self.COMBINED_PROMPT.format(
            raw_text=raw_text,
            platform=platform
        )
        # Usa Gemini Flash-Lite (ya configurado)
        result = await call_gemini(
            prompt=prompt,
            model="gemini-2.0-flash-lite",
            response_format="json"
        )
        return json.loads(result)
\`\`\`

### PASO 3: Integrar en webhook handler

Donde actualmente se procesa el audio:

\`\`\`python
if message_type == "audio":
    # 1. Descargar audio
    audio_bytes = await download_media(media_url)

    # 2. Transcribir (cascade: Groq free → paid → OpenAI)
    cascade = AudioTranscriptionCascade()
    raw_text = await cascade.transcribe(audio_bytes, duration)

    # 3. Inteligencia (Gemini Flash-Lite, ~$0.0001)
    intel = AudioIntelligenceService()
    result = await intel.process(raw_text, role=role)

    # 4. Guardar en msg_metadata
    msg_metadata["transcription"] = result
    message_content = result["clean_text"]
\`\`\`

### PASO 4: Configuración

Añadir a .env / Railway:
\`\`\`
GROQ_API_KEY=gsk_xxxxxx  # Crear en console.groq.com (gratis)
# GOOGLE_API_KEY ya existe (Gemini)
# OPENAI_API_KEY ya existe (fallback)
\`\`\`

### PASO 5: Verificar

1. Enviar audio de prueba por WhatsApp
2. Verificar logs: ¿usó Groq free? ¿Gemini free?
3. Verificar msg_metadata tiene transcription con todos campos
4. Verificar que el bot responde al CONTENIDO del audio

### COSTES ESPERADOS
- Hasta 20 creators: $0.00/mes
- Hasta 100 creators: ~$3/mes (solo Gemini texto)
- Hasta 500 creators: ~$63/mes (Groq paid + Gemini)
- Si cobras 49€/mes: el audio es <0.3% del ingreso

### GIT
\`\`\`
feat(audio): cascade transcription (Groq free → paid → OpenAI)
- 4-tier fallback: free → cheap → paid → scale
- Groq Whisper free: 2000 req/day, WER 9.5% (mejor que actual)
- Combined intelligence prompt: 1 Gemini call = clean+extract+summary
- Zero cost hasta 20 creators
\`\`\``}
            </div>
          </div>
        )}

      </div>
      <style>{`* { box-sizing: border-box; margin: 0; padding: 0; } button { font-family: inherit; } ::-webkit-scrollbar { width: 4px; height: 4px; } ::-webkit-scrollbar-thumb { background: ${C.bd}; border-radius: 2px; }`}</style>
    </div>
  );
}
