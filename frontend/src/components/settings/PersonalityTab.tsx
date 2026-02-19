import { useState, useEffect } from "react";
import { Save, RefreshCw, Loader2, Check, Sparkles, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { API_URL } from "@/services/api";

type ToastFn = (opts: {
  title?: string;
  description?: string;
  variant?: "default" | "destructive";
}) => void;

interface PersonalityTabProps {
  config: Record<string, any> | undefined;
  updateConfig: {
    mutateAsync: (data: Record<string, any>) => Promise<any>;
    isPending: boolean;
  };
  toast: ToastFn;
  queryClient: {
    invalidateQueries: (options: { queryKey: string[] }) => Promise<void>;
  };
}

const personalityPresets = [
  {
    id: "amigo",
    emoji: "😊",
    label: "Amigo",
    rules: "- Tutea siempre al usuario\n- Usa emojis (1-2 por mensaje)\n- Sé cercano y conversacional\n- Responde como un amigo de confianza\n- Muestra empatía y comprensión"
  },
  {
    id: "mentor",
    emoji: "🎓",
    label: "Mentor",
    rules: "- Posiciónate como experto en tu campo\n- Da consejos prácticos y accionables\n- Ofrece valor antes de vender\n- Guía paso a paso al usuario\n- Comparte conocimiento estructurado"
  },
  {
    id: "vendedor",
    emoji: "🎯",
    label: "Vendedor",
    rules: "- Ve al grano, sé directo\n- Destaca beneficios y resultados\n- Incluye llamadas a la acción claras\n- Crea urgencia de manera natural\n- Maneja objeciones con empatía"
  },
  {
    id: "profesional",
    emoji: "💼",
    label: "Profesional",
    rules: "- Usa tono formal pero accesible\n- Trata de usted al usuario\n- Evita emojis excesivos (máximo 1)\n- Sé preciso y conciso\n- Demuestra expertise y credibilidad"
  },
];

export default function PersonalityTab({ config, updateConfig, toast, queryClient }: PersonalityTabProps) {
  const [botName, setBotName] = useState("");
  const [rules, setRules] = useState("");
  const [selectedPreset, setSelectedPreset] = useState<string | null>("amigo");
  const [aiPrompt, setAiPrompt] = useState("");
  const [isGeneratingAI, setIsGeneratingAI] = useState(false);

  useEffect(() => {
    if (config) {
      setBotName(config.clone_name || "");
      setRules(config.clone_vocabulary || "");
      const matchingPreset = personalityPresets.find(p => p.rules === config.clone_vocabulary);
      setSelectedPreset(matchingPreset?.id || null);
    }
  }, [config]);

  const handlePresetSelect = (presetId: string) => {
    setSelectedPreset(presetId);
    const preset = personalityPresets.find(p => p.id === presetId);
    if (preset) {
      setRules(preset.rules);
    }
  };

  const handleGenerateAIPersonality = async () => {
    if (!aiPrompt.trim()) {
      toast({
        title: "Escribe una descripción",
        description: "Describe cómo quieres que sea tu asistente.",
        variant: "destructive",
      });
      return;
    }

    setIsGeneratingAI(true);
    try {
      const token = localStorage.getItem("clonnect_auth_token");
      const response = await fetch(`${API_URL}/api/ai/generate-rules`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ prompt: aiPrompt }),
      });

      if (response.ok) {
        const data = await response.json();
        setRules(data.rules || "");
        setSelectedPreset(null);
        setAiPrompt("");
        toast({
          title: "Instrucciones generadas",
          description: "Puedes editarlas antes de guardar.",
        });
      } else {
        throw new Error("Error al generar");
      }
    } catch {
      const generatedRules = `- ${aiPrompt.split(',').map((s: string) => s.trim()).filter(Boolean).join('\n- ')}`;
      setRules(generatedRules);
      setSelectedPreset(null);
      setAiPrompt("");
      toast({
        title: "Instrucciones añadidas",
        description: "Puedes editarlas antes de guardar.",
      });
    } finally {
      setIsGeneratingAI(false);
    }
  };

  const handleSavePersonality = async () => {
    try {
      await updateConfig.mutateAsync({
        clone_name: botName,
        clone_vocabulary: rules,
      });
      toast({
        title: "Guardado",
        description: "La personalidad del bot ha sido actualizada.",
      });
      await queryClient.invalidateQueries({ queryKey: ["creatorConfig"] });
    } catch (error) {
      toast({
        title: "Error al guardar",
        description: error instanceof Error ? error.message : "No se pudo guardar la configuración",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-6">
      {/* Bot Name */}
      <div className="p-5 rounded-2xl bg-card border border-border/50">
        <Label htmlFor="botName" className="text-sm font-medium mb-3 block">Nombre del bot</Label>
        <Input
          id="botName"
          value={botName}
          onChange={(e) => setBotName(e.target.value)}
          className="bg-muted/30 border-border/30"
          placeholder="Tu nombre o marca"
        />
      </div>

      {/* Presets - 4 opciones */}
      <div className="p-5 rounded-2xl bg-card border border-border/50">
        <h3 className="text-sm font-medium mb-1">Estilo de comunicación</h3>
        <p className="text-xs text-muted-foreground mb-4">Elige un estilo base</p>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {personalityPresets.map((preset) => (
            <button
              key={preset.id}
              onClick={() => handlePresetSelect(preset.id)}
              className={cn(
                "p-4 rounded-xl border text-center transition-all",
                selectedPreset === preset.id
                  ? "border-primary bg-primary/5"
                  : "border-border/30 hover:border-border"
              )}
            >
              <span className="text-xl block mb-2">{preset.emoji}</span>
              <span className="text-xs font-medium">{preset.label}</span>
              {selectedPreset === preset.id && (
                <Check className="w-3.5 h-3.5 text-primary mx-auto mt-2" />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Personalizar con IA */}
      <div className="rounded-xl p-6 border border-primary/30 bg-gradient-to-br from-primary/10 via-accent/5 to-primary/10">
        <div className="flex items-center gap-2 mb-4">
          <Sparkles className="w-5 h-5 text-primary" />
          <h3 className="text-lg font-semibold">Personalizar con IA</h3>
        </div>

        <p className="text-muted-foreground text-sm mb-4">
          Describe cómo quieres que sea tu bot y generaremos las instrucciones
        </p>

        <Textarea
          value={aiPrompt}
          onChange={(e) => setAiPrompt(e.target.value)}
          placeholder="Ej: Quiero que sea cercano, use emojis, tutee al usuario, y mencione mi curso de trading cuando pregunten por inversiones..."
          className="bg-background/80 border-0 min-h-[80px] resize-none mb-3"
        />

        <Button
          onClick={handleGenerateAIPersonality}
          disabled={isGeneratingAI || !aiPrompt.trim()}
          className="bg-gradient-to-r from-primary to-accent hover:opacity-90"
        >
          {isGeneratingAI ? (
            <>
              <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
              Generando...
            </>
          ) : (
            <>
              <Wand2 className="w-4 h-4 mr-2" />
              Generar instrucciones
            </>
          )}
        </Button>
      </div>

      {/* Rules - editable */}
      <div className="metric-card">
        <h3 className="text-lg font-semibold mb-2">Instrucciones del bot</h3>
        <p className="text-muted-foreground text-sm mb-4">Puedes editar estas reglas manualmente</p>

        <Textarea
          value={rules}
          onChange={(e) => {
            setRules(e.target.value);
            setSelectedPreset(null);
          }}
          className="bg-secondary border-0 min-h-[160px] font-mono text-sm resize-none"
          placeholder="Las instrucciones aparecerán aquí..."
        />
      </div>

      {/* Save */}
      <Button
        onClick={handleSavePersonality}
        disabled={updateConfig.isPending}
        className="w-full bg-gradient-to-r from-primary to-accent hover:opacity-90 transition-opacity"
      >
        {updateConfig.isPending ? (
          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
        ) : (
          <Save className="w-4 h-4 mr-2" />
        )}
        Guardar cambios
      </Button>
    </div>
  );
}
