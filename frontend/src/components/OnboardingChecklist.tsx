import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

const CREATOR_ID = import.meta.env.VITE_CREATOR_ID || "manel";
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface OnboardingStep {
  key: string;
  label: string;
  description?: string;
  link: string;
}

interface OnboardingStatus {
  status: string;
  steps: Record<string, boolean>;
  core_steps: Record<string, boolean>;
  completed: number;
  total: number;
  percentage: number;
  is_complete: boolean;
  next_step: OnboardingStep;
}

async function fetchOnboardingStatus(): Promise<OnboardingStatus> {
  const response = await fetch(`${API_URL}/onboarding/${CREATOR_ID}/status`);
  if (!response.ok) throw new Error("Failed to fetch onboarding status");
  return response.json();
}

const stepLabels: Record<string, { label: string; link: string }> = {
  connect_channel: { label: "Conectar un canal", link: "/settings" },
  connect_instagram: { label: "Conectar Instagram", link: "/settings" },
  connect_telegram: { label: "Conectar Telegram", link: "/settings" },
  connect_whatsapp: { label: "Conectar WhatsApp", link: "/settings" },
  add_product: { label: "Añadir un producto", link: "/settings" },
  configure_personality: { label: "Configurar personalidad", link: "/settings" },
  activate_bot: { label: "Activar el bot", link: "/settings" },
};

export function OnboardingChecklist() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["onboarding", CREATOR_ID],
    queryFn: fetchOnboardingStatus,
    staleTime: 60000, // 1 minute
  });

  // Don't show if loading, error, or complete
  if (isLoading || error || !data || data.is_complete) {
    return null;
  }

  return (
    <div className="metric-card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold flex items-center gap-2">
          <span className="text-xl">🚀</span>
          Configura tu clon en {data.total} pasos
        </h3>
        <span className="text-sm text-muted-foreground">
          {data.percentage}% completado
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-secondary rounded-full h-2 mb-6">
        <div
          className="bg-primary h-2 rounded-full transition-all duration-500"
          style={{ width: `${data.percentage}%` }}
        />
      </div>

      {/* Steps */}
      <div className="space-y-2">
        {Object.entries(data.core_steps).map(([key, completed]) => {
          const stepInfo = stepLabels[key] || { label: key, link: "/settings" };
          return (
            <div
              key={key}
              className={`flex items-center gap-3 p-3 rounded-lg transition-colors ${
                completed
                  ? "bg-secondary/50"
                  : "bg-secondary/50 hover:bg-secondary"
              }`}
            >
              <span className="text-lg">
                {completed ? "✅" : "⬜"}
              </span>
              <Link
                to={stepInfo.link}
                className={`flex-1 text-sm ${
                  completed
                    ? "text-muted-foreground line-through"
                    : "text-foreground hover:text-primary"
                }`}
              >
                {stepInfo.label}
              </Link>
              {!completed && (
                <Link
                  to={stepInfo.link}
                  className="text-xs bg-primary hover:bg-primary/80 px-3 py-1 rounded-full text-primary-foreground transition-colors"
                >
                  Configurar
                </Link>
              )}
            </div>
          );
        })}
      </div>

      {/* Next step CTA */}
      {data.next_step?.key && (
        <div className="mt-4 p-3 bg-secondary/50 rounded-lg">
          <p className="text-xs text-muted-foreground mb-1">Siguiente paso:</p>
          <Link
            to={data.next_step.link}
            className="flex items-center justify-between group"
          >
            <span className="font-medium text-foreground group-hover:text-primary transition-colors">
              {data.next_step.label}
            </span>
            <span className="text-primary group-hover:translate-x-1 transition-transform">
              →
            </span>
          </Link>
          {data.next_step.description && (
            <p className="text-xs text-muted-foreground mt-1">{data.next_step.description}</p>
          )}
        </div>
      )}
    </div>
  );
}

export default OnboardingChecklist;
