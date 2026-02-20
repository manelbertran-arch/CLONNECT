import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAutolearningDashboard } from "@/hooks/useApi";
import { useAuth } from "@/context/AuthContext";
import type {
  AutopilotReadiness,
  AutolearningLesson,
  AutolearningAchievement,
} from "@/services/api";

// =============================================================================
// PALETTE & HELPERS (exact design spec)
// =============================================================================

const P = { bg: "#09090B", card: "#141417", bd: "#1F1F23", tx: "#E4E4E7", t2: "#A1A1AA", t3: "#63636E", vi: "#8B5CF6", cy: "#06B6D4", gn: "#34D399", am: "#FBBF24", rd: "#F87171" };
const sc = (p: number) => p >= 70 ? P.gn : p >= 35 ? P.am : P.rd;

// =============================================================================
// COMPARISON CARD
// =============================================================================

function CompCard({ c, creatorName }: { c: AutolearningLesson; creatorName: string }) {
  const lesson = c.linked_rule?.rule_text || null;

  if (c.action === "approved") {
    return (
      <div style={{ padding: "10px 14px", borderRadius: 8, border: `1px solid ${P.bd}`, display: "flex", gap: 10, alignItems: "flex-start" }}>
        <span style={{ color: P.gn, fontSize: 12, marginTop: 2 }}>✓</span>
        <div>
          <div style={{ fontSize: 13, color: P.t2, lineHeight: 1.5 }}>{c.suggested_response || "(sin texto)"}</div>
          <div style={{ fontSize: 11, color: P.t3, marginTop: 4 }}>El clon acerto</div>
        </div>
      </div>
    );
  }
  if (c.action === "discarded") {
    return (
      <div style={{ padding: "10px 14px", borderRadius: 8, border: `1px solid ${P.bd}` }}>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
          <span style={{ color: P.rd, fontSize: 12, marginTop: 2 }}>✗</span>
          <div style={{ fontSize: 13, color: P.t3, textDecoration: "line-through", lineHeight: 1.5 }}>{c.suggested_response || "(sin texto)"}</div>
        </div>
        {lesson && <div style={{ fontSize: 12, color: P.t2, marginTop: 8, paddingLeft: 22 }}>💡 {lesson}</div>}
      </div>
    );
  }
  // edited
  return (
    <div style={{ padding: "14px", borderRadius: 8, border: `1px solid ${P.bd}` }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <div>
          <div style={{ fontSize: 10, color: P.rd, fontWeight: 500, marginBottom: 4 }}>Clon</div>
          <div style={{ fontSize: 13, color: P.t3, lineHeight: 1.5 }}>{c.suggested_response || "(sin texto)"}</div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: P.gn, fontWeight: 500, marginBottom: 4 }}>{creatorName}</div>
          <div style={{ fontSize: 13, color: P.t2, lineHeight: 1.5 }}>{c.final_response || "(sin texto)"}</div>
        </div>
      </div>
      {lesson && <div style={{ fontSize: 12, color: P.t2, marginTop: 10 }}>💡 {lesson}</div>}
    </div>
  );
}

// =============================================================================
// LOADING SKELETON
// =============================================================================

function LoadingSkeleton() {
  return (
    <div style={{ minHeight: "100vh", background: P.bg, color: P.tx, fontFamily: "'Inter',system-ui,sans-serif" }}>
      <div style={{ maxWidth: 620, margin: "0 auto", padding: "48px 20px 100px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 40 }}>
          <div>
            <div style={{ width: 140, height: 14, background: P.bd, borderRadius: 4, marginBottom: 8 }} />
            <div style={{ width: 200, height: 22, background: P.bd, borderRadius: 4 }} />
          </div>
        </div>
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <div style={{ width: 120, height: 14, background: P.bd, borderRadius: 4, margin: "0 auto 10px" }} />
          <div style={{ width: 160, height: 60, background: P.bd, borderRadius: 8, margin: "0 auto" }} />
        </div>
        {[1, 2, 3, 4].map(i => (
          <div key={i} style={{ padding: "16px 0", borderBottom: `1px solid ${P.bd}`, display: "flex", gap: 16, alignItems: "center" }}>
            <div style={{ width: 44, height: 20, background: P.bd, borderRadius: 4 }} />
            <div style={{ flex: 1 }}>
              <div style={{ width: "60%", height: 14, background: P.bd, borderRadius: 4, marginBottom: 6 }} />
              <div style={{ width: "100%", height: 3, background: P.bd, borderRadius: 2 }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// EMPTY STATE
// =============================================================================

function EmptyState() {
  const navigate = useNavigate();
  return (
    <div style={{ minHeight: "100vh", background: P.bg, color: P.tx, fontFamily: "'Inter',system-ui,sans-serif" }}>
      <div style={{ maxWidth: 620, margin: "0 auto", padding: "48px 20px 100px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "60vh", textAlign: "center", gap: 16 }}>
        <div style={{ fontSize: 48 }}>🧠</div>
        <h2 style={{ fontSize: 20, fontWeight: 600 }}>Tu clon aun no ha empezado a aprender</h2>
        <p style={{ fontSize: 14, color: P.t3, maxWidth: 400 }}>
          Activa el modo copiloto y empieza a aprobar, editar o descartar sugerencias para que tu clon aprenda de ti.
        </p>
        <div
          onClick={() => navigate("/copilot")}
          style={{ background: P.vi, color: "#fff", padding: "10px 24px", borderRadius: 8, cursor: "pointer", fontSize: 14, fontWeight: 600, marginTop: 8 }}
        >
          Ir al Copiloto
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// MAIN PAGE
// =============================================================================

export default function Autolearning() {
  const { data, isLoading, error } = useAutolearningDashboard();
  const { user, creatorId } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState<number | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => { setTimeout(() => setReady(true), 50); }, []);

  if (isLoading) return <LoadingSkeleton />;

  if (error) {
    return (
      <div style={{ minHeight: "100vh", background: P.bg, color: P.tx, fontFamily: "'Inter',system-ui,sans-serif", display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 12 }}>
        <div style={{ fontSize: 32 }}>⚠️</div>
        <p style={{ fontSize: 16, fontWeight: 500 }}>Error al cargar el dashboard</p>
        <p style={{ fontSize: 13, color: P.t3 }}>{(error as Error).message}</p>
      </div>
    );
  }

  if (!data || data.clone_xp.total_xp === 0) return <EmptyState />;

  // Derive display values from API data
  const NAME = user?.name || creatorId?.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()) || "Creador";
  const { clone_xp, autopilot_readiness, lessons, achievements } = data;
  const { level, total_xp, streak, breakdown } = clone_xp;

  // Compute overall approval rate (percentage)
  const totalActions = breakdown.approved + breakdown.edited + breakdown.discarded;
  const approval = totalActions > 0 ? Math.round((breakdown.approved / totalActions) * 100) : 0;

  // Pending count from copilot (not in this API — show lessons count as CTA)
  const pendingLessons = lessons.filter(l => l.action !== "approved").length;

  // Map autopilot_readiness → CATS format
  const CATS = autopilot_readiness.map((item: AutopilotReadiness) => ({
    name: item.label,
    pct: Math.round(item.approval_rate * 100),
    approved: item.approved,
    total: item.total,
    ready: item.status === "ready",
    intent: item.intent,
  }));

  // Map achievements → MEDALS format
  const MEDALS = achievements.map((ach: AutolearningAchievement) => ({
    e: ach.icon,
    n: ach.name,
    on: ach.unlocked,
  }));

  // Get lessons matching a category intent
  const getLessonsForIntent = (intent: string) =>
    lessons.filter((l: AutolearningLesson) => l.intent === intent);

  return (
    <div style={{ minHeight: "100vh", background: P.bg, color: P.tx, fontFamily: "'Inter',system-ui,sans-serif" }}>
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
      <div style={{ maxWidth: 620, margin: "0 auto", padding: "48px 20px 100px" }}>

        {/* ── HEADER ── */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 40 }}>
          <div>
            <div style={{ fontSize: 13, color: P.t3, marginBottom: 4 }}>{level.emoji} Nivel {level.number} · {level.name}</div>
            <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, letterSpacing: "-0.03em" }}>Clon de {NAME}</h1>
          </div>
          {streak.current > 0 && (
            <div style={{ fontSize: 13, color: P.t3 }}>🔥 {streak.current} dias</div>
          )}
        </div>

        {/* ── THE NUMBER ── */}
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <div style={{ fontSize: 13, color: P.t3, marginBottom: 10 }}>Tu clon acierta</div>
          <div style={{ fontSize: 72, fontWeight: 800, letterSpacing: "-0.05em", lineHeight: 1 }}>{approval}<span style={{ fontSize: 28, color: P.t3, fontWeight: 500 }}>/100</span></div>
          {total_xp > 0 && (
            <div style={{ fontSize: 13, color: P.gn, marginTop: 10 }}>{total_xp} XP acumulados. Tus correcciones funcionan.</div>
          )}
        </div>

        {/* ── CTA ── */}
        {pendingLessons > 0 && (
          <div
            onClick={() => navigate("/copilot")}
            style={{
              background: P.vi, borderRadius: 10, padding: "16px 24px", marginBottom: 48, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "space-between"
            }}
          >
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: "#fff" }}>{pendingLessons} correcciones recientes</div>
              <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", marginTop: 1 }}>Cada correccion mejora tu clon</div>
            </div>
            <span style={{ fontSize: 14, fontWeight: 600, color: "#fff" }}>Revisar →</span>
          </div>
        )}

        {/* ── CATEGORÍAS ── */}
        {CATS.length > 0 && (
          <div style={{ marginBottom: 48 }}>
            <div style={{ fontSize: 12, color: P.t3, fontWeight: 500, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>Por tipo de mensaje</div>

            {CATS.map((cat, i) => {
              const isOpen = open === i;
              const color = sc(cat.pct);
              const catLessons = getLessonsForIntent(cat.intent);

              return (
                <div key={cat.name} style={{ borderBottom: `1px solid ${P.bd}` }}>
                  <div
                    onClick={() => setOpen(isOpen ? null : i)}
                    style={{ padding: "16px 0", cursor: "pointer", display: "flex", alignItems: "center", gap: 16 }}
                  >
                    <span style={{ fontSize: 18, fontWeight: 700, color, width: 44, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{cat.pct}%</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                        <span style={{ fontSize: 14, fontWeight: 500 }}>{cat.name}</span>
                        <span style={{ fontSize: 12, color: P.t3 }}>{cat.approved}/{cat.total}</span>
                      </div>
                      <div style={{ height: 3, borderRadius: 2, background: P.bd }}>
                        <div style={{ width: ready ? `${cat.pct}%` : "0%", height: "100%", borderRadius: 2, background: color, transition: `width 0.8s ${i * 0.08}s ease` }} />
                      </div>
                    </div>
                    {cat.ready ? (
                      <span style={{ fontSize: 11, color: P.gn, fontWeight: 500, whiteSpace: "nowrap" }}>Activar autopilot →</span>
                    ) : (
                      <span style={{ fontSize: 16, color: P.t3, transition: "transform 0.2s", transform: isOpen ? "rotate(180deg)" : "none" }}>›</span>
                    )}
                  </div>
                  {isOpen && catLessons.length > 0 && (
                    <div style={{ paddingBottom: 16, paddingLeft: 60, display: "flex", flexDirection: "column", gap: 6 }}>
                      {catLessons.map(c => <CompCard key={c.id} c={c} creatorName={NAME} />)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* ── ÚLTIMAS CORRECCIONES ── */}
        {lessons.length > 0 && (
          <div style={{ marginBottom: 48 }}>
            <div style={{ fontSize: 12, color: P.t3, fontWeight: 500, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>Ultimas correcciones</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {lessons.map(c => <CompCard key={c.id} c={c} creatorName={NAME} />)}
            </div>
          </div>
        )}

        {/* ── LOGROS ── */}
        {MEDALS.length > 0 && (
          <div>
            <div style={{ fontSize: 12, color: P.t3, fontWeight: 500, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>Logros</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {MEDALS.map((m, i) => (
                <div key={i} style={{
                  width: 56, height: 56, borderRadius: 8, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                  background: m.on ? P.card : "transparent", border: `1px solid ${m.on ? P.bd : "transparent"}`,
                  opacity: m.on ? 1 : 0.2
                }}>
                  <span style={{ fontSize: 20 }}>{m.on ? m.e : "🔒"}</span>
                  <span style={{ fontSize: 7, color: P.t3, marginTop: 2 }}>{m.n}</span>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
      <style>{`* { box-sizing: border-box; }`}</style>
    </div>
  );
}
