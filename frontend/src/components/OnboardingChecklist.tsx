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
    <div className="bg-gradient-to-r from-purple-900/40 to-indigo-900/40 border border-purple-500/30 rounded-xl p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <span className="text-2xl">🚀</span>
          Configura tu clon en {data.total} pasos
        </h3>
        <span className="text-sm text-purple-300">
          {data.percentage}% completado
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-700 rounded-full h-2 mb-6">
        <div
          className="bg-gradient-to-r from-purple-500 to-cyan-400 h-2 rounded-full transition-all duration-500"
          style={{ width: `${data.percentage}%` }}
        />
      </div>

      {/* Steps */}
      <div className="space-y-3">
        {Object.entries(data.core_steps).map(([key, completed]) => {
          const stepInfo = stepLabels[key] || { label: key, link: "/settings" };
          return (
            <div
              key={key}
              className={`flex items-center gap-3 p-3 rounded-lg transition-colors ${
                completed
                  ? "bg-green-900/20 border border-green-500/20"
                  : "bg-gray-800/50 hover:bg-gray-800"
              }`}
            >
              <span className="text-xl">
                {completed ? "✅" : "⬜"}
              </span>
              <Link
                to={stepInfo.link}
                className={`flex-1 ${
                  completed
                    ? "text-green-400 line-through"
                    : "text-white hover:text-cyan-400"
                }`}
              >
                {stepInfo.label}
              </Link>
              {!completed && (
                <Link
                  to={stepInfo.link}
                  className="text-xs bg-purple-600 hover:bg-purple-500 px-3 py-1 rounded-full text-white transition-colors"
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
        <div className="mt-6 p-4 bg-gradient-to-r from-cyan-600/20 to-purple-600/20 rounded-lg border border-cyan-500/30">
          <p className="text-sm text-gray-300 mb-2">Siguiente paso:</p>
          <Link
            to={data.next_step.link}
            className="flex items-center justify-between group"
          >
            <span className="text-lg font-medium text-white group-hover:text-cyan-400 transition-colors">
              {data.next_step.label}
            </span>
            <span className="text-cyan-400 group-hover:translate-x-1 transition-transform">
              →
            </span>
          </Link>
          {data.next_step.description && (
            <p className="text-sm text-gray-400 mt-1">{data.next_step.description}</p>
          )}
        </div>
      )}
    </div>
  );
}

export default OnboardingChecklist;
