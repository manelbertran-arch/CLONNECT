import { useState, useEffect } from "react";
import { Save, RefreshCw, Loader2, Plus, Trash2, Check, Sparkles, Wand2, HelpCircle, User, ChevronDown, Pencil, Package } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { API_URL } from "@/services/api";
import type { Product } from "@/types/api";

type ToastFn = (opts: {
  title?: string;
  description?: string;
  variant?: "default" | "destructive";
}) => void;

interface FAQItem {
  id: string;
  question: string;
  answer: string;
}

interface KnowledgeData {
  faqs?: FAQItem[];
  about?: {
    bio?: string;
    specialties?: string | string[];
    experience?: string;
    target_audience?: string;
  };
  items?: any[];
}

interface ProductsData {
  products?: Product[];
}

interface KnowledgeTabProps {
  knowledgeData: KnowledgeData | undefined;
  knowledgeLoading: boolean;
  productsData: ProductsData | undefined;
  toast: ToastFn;
  addFAQMutation: {
    mutateAsync: (args: { question: string; answer: string }) => Promise<any>;
    isPending: boolean;
  };
  deleteFAQMutation: {
    mutateAsync: (id: string) => Promise<any>;
    isPending: boolean;
  };
  updateFAQMutation: {
    mutateAsync: (args: { itemId: string; question: string; answer: string }) => Promise<any>;
    isPending: boolean;
  };
  updateAboutMutation: {
    mutateAsync: (data: { bio: string; specialties: string; experience: string; target_audience: string }) => Promise<any>;
    isPending: boolean;
  };
}

const faqTemplates = [
  { question: "¿Cuánto cuesta?", answer: "" },
  { question: "¿Qué incluye?", answer: "" },
  { question: "¿Hay garantía?", answer: "" },
  { question: "¿Cómo pago?", answer: "" },
  { question: "¿Cuál es el horario?", answer: "" },
  { question: "¿Ofrecen soporte?", answer: "" },
];

export default function KnowledgeTab({
  knowledgeData,
  knowledgeLoading,
  productsData,
  toast,
  addFAQMutation,
  deleteFAQMutation,
  updateFAQMutation,
  updateAboutMutation,
}: KnowledgeTabProps) {
  const [aboutOpen, setAboutOpen] = useState(false);
  const [aboutData, setAboutData] = useState({
    bio: "",
    specialties: "",
    experience: "",
    target_audience: ""
  });
  const [originalAboutData, setOriginalAboutData] = useState({ bio: "", specialties: "", experience: "", target_audience: "" });
  const [aboutHasChanges, setAboutHasChanges] = useState(false);

  const [faqQuestion, setFaqQuestion] = useState("");
  const [faqAnswer, setFaqAnswer] = useState("");
  const [faqModalOpen, setFaqModalOpen] = useState(false);
  const [aiKnowledgePrompt, setAiKnowledgePrompt] = useState("");
  const [isGeneratingKnowledge, setIsGeneratingKnowledge] = useState(false);
  const [editingFaq, setEditingFaq] = useState<{ id: string; question: string; answer: string } | null>(null);

  const products = productsData?.products || [];

  useEffect(() => {
    if (knowledgeData?.about) {
      const about = knowledgeData.about;
      const specialtiesValue = Array.isArray(about.specialties)
        ? about.specialties.join(", ")
        : (about.specialties || "");
      const newData = {
        bio: about.bio || "",
        specialties: specialtiesValue,
        experience: about.experience || "",
        target_audience: about.target_audience || ""
      };
      setAboutData(newData);
      setOriginalAboutData(newData);
      setAboutHasChanges(false);
    }
  }, [knowledgeData]);

  useEffect(() => {
    const hasChanges =
      aboutData.bio !== originalAboutData.bio ||
      aboutData.specialties !== originalAboutData.specialties ||
      aboutData.experience !== originalAboutData.experience ||
      aboutData.target_audience !== originalAboutData.target_audience;
    setAboutHasChanges(hasChanges);
  }, [aboutData, originalAboutData]);

  const handleSaveAbout = async () => {
    try {
      await updateAboutMutation.mutateAsync(aboutData);
      setOriginalAboutData(aboutData);
      setAboutHasChanges(false);
      toast({
        title: "Guardado",
        description: "Tu información 'Sobre ti' se ha guardado correctamente.",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo guardar. Inténtalo de nuevo.",
        variant: "destructive",
      });
    }
  };

  const handleAddFAQ = async () => {
    if (!faqQuestion.trim() || !faqAnswer.trim()) {
      toast({
        title: "Campos incompletos",
        description: "Por favor completa la pregunta y la respuesta.",
        variant: "destructive",
      });
      return;
    }

    try {
      await addFAQMutation.mutateAsync({ question: faqQuestion, answer: faqAnswer });
      toast({ title: "FAQ añadida", description: "La pregunta ha sido guardada." });
      setFaqQuestion("");
      setFaqAnswer("");
      setFaqModalOpen(false);
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to add FAQ",
        variant: "destructive",
      });
    }
  };

  const handleDeleteFAQ = async (itemId: string) => {
    try {
      await deleteFAQMutation.mutateAsync(itemId);
      toast({ title: "FAQ eliminada", description: "La pregunta ha sido eliminada." });
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to delete FAQ",
        variant: "destructive",
      });
    }
  };

  const handleUpdateFAQ = async () => {
    if (!editingFaq) return;
    try {
      await updateFAQMutation.mutateAsync({
        itemId: editingFaq.id,
        question: editingFaq.question,
        answer: editingFaq.answer
      });
      setEditingFaq(null);
      toast({ title: "FAQ actualizada", description: "La pregunta ha sido actualizada." });
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to update FAQ",
        variant: "destructive",
      });
    }
  };

  const handleSelectTemplate = (template: { question: string; answer: string }) => {
    setFaqQuestion(template.question);
    setFaqAnswer("");
    setFaqModalOpen(true);
  };

  const handleGenerateKnowledge = async () => {
    if (!aiKnowledgePrompt.trim()) {
      toast({
        title: "Escribe una descripción",
        description: "Describe tu negocio o pega tu bio para generar FAQs.",
        variant: "destructive",
      });
      return;
    }

    setIsGeneratingKnowledge(true);
    try {
      const token = localStorage.getItem("clonnect_auth_token");
      const response = await fetch(`${API_URL}/api/ai/generate-knowledge-full`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ content: aiKnowledgePrompt }),
      });

      if (!response.ok) throw new Error("Error generating knowledge");

      const result = await response.json();

      if (result.faqs && result.faqs.length > 0) {
        for (const faq of result.faqs) {
          await addFAQMutation.mutateAsync({
            question: faq.question,
            answer: faq.answer,
          });
        }
      }

      if (result.about) {
        const specialtiesValue = Array.isArray(result.about.specialties)
          ? result.about.specialties.join(", ")
          : (result.about.specialties || "");
        setAboutData(prev => ({
          bio: result.about.bio || prev.bio,
          specialties: specialtiesValue || prev.specialties,
          experience: result.about.experience || prev.experience,
          target_audience: result.about.target_audience || prev.target_audience,
        }));
        setAboutOpen(true);
      }

      const faqCount = result.faqs?.length || 0;
      const aboutFilled = result.about?.bio ? " + perfil completado" : "";
      toast({
        title: "Knowledge generado",
        description: `${faqCount} FAQs creadas${aboutFilled}.`,
      });
      setAiKnowledgePrompt("");

    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to generate",
        variant: "destructive",
      });
    } finally {
      setIsGeneratingKnowledge(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. SOBRE TI - Collapsible */}
      <div className="metric-card overflow-hidden p-0">
        <button
          onClick={() => setAboutOpen(!aboutOpen)}
          className="w-full p-4 flex justify-between items-center hover:bg-secondary/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <User className="w-5 h-5 text-primary" />
            <span className="font-semibold">Sobre ti</span>
            {aboutData.bio && (
              <span className="text-xs bg-success/20 text-success px-2 py-0.5 rounded-full">Completado</span>
            )}
          </div>
          <ChevronDown className={cn("w-5 h-5 transition-transform", aboutOpen && "rotate-180")} />
        </button>

        {aboutOpen && (
          <div className="p-6 pt-2 space-y-4 border-t border-border">
            <p className="text-sm text-muted-foreground">Esta información ayuda al bot a presentarte correctamente</p>

            <div>
              <Label className="text-sm text-muted-foreground mb-2 block">Bio / Descripción</Label>
              <Textarea
                value={aboutData.bio}
                onChange={(e) => setAboutData({...aboutData, bio: e.target.value})}
                placeholder="Soy trader profesional desde 2018..."
                className="bg-secondary border-0 min-h-[80px] resize-none"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-sm text-muted-foreground mb-2 block">Especialidades</Label>
                <Input
                  value={aboutData.specialties}
                  onChange={(e) => setAboutData({...aboutData, specialties: e.target.value})}
                  placeholder="Ej: coaching, nutrición, marketing..."
                  className="bg-secondary border-0"
                />
              </div>
              <div>
                <Label className="text-sm text-muted-foreground mb-2 block">Experiencia</Label>
                <Input
                  value={aboutData.experience}
                  onChange={(e) => setAboutData({...aboutData, experience: e.target.value})}
                  placeholder=""
                  className="bg-secondary border-0"
                />
              </div>
            </div>

            <div>
              <Label className="text-sm text-muted-foreground mb-2 block">Público objetivo</Label>
              <Input
                value={aboutData.target_audience}
                onChange={(e) => setAboutData({...aboutData, target_audience: e.target.value})}
                placeholder="Ej: Emprendedores, profesionales, estudiantes..."
                className="bg-secondary border-0"
              />
            </div>

            {/* Save Button */}
            <div className="flex items-center justify-end gap-3 pt-4 border-t border-border mt-4">
              {aboutHasChanges ? (
                <Button
                  onClick={handleSaveAbout}
                  disabled={updateAboutMutation.isPending}
                  className="bg-primary hover:bg-primary/90"
                >
                  {updateAboutMutation.isPending ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Guardando...
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4 mr-2" />
                      Guardar cambios
                    </>
                  )}
                </Button>
              ) : (
                <span className="text-sm text-muted-foreground flex items-center gap-2">
                  <Check className="w-4 h-4 text-success" />
                  Sin cambios pendientes
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 2. FAQS */}
      <div className="metric-card space-y-6">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <HelpCircle className="w-5 h-5 text-primary" />
            <h3 className="text-lg font-semibold">Preguntas Frecuentes</h3>
          </div>
          <p className="text-sm text-muted-foreground">El bot usará estas respuestas automáticamente</p>
        </div>

        {/* AI Generator */}
        <div className="rounded-xl p-5 border border-primary/30 bg-gradient-to-br from-primary/10 via-accent/5 to-primary/10">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-4 h-4 text-primary" />
            <span className="font-medium">Genera todo automáticamente</span>
          </div>
          <p className="text-xs text-muted-foreground mb-3">Describe tu negocio y generaremos FAQs + tu perfil "Sobre ti"</p>

          <Textarea
            value={aiKnowledgePrompt}
            onChange={(e) => setAiKnowledgePrompt(e.target.value)}
            className="bg-background/80 border-0 min-h-[120px] resize-none mb-3 text-sm"
            placeholder={`Soy Manel, trader profesional desde 2018. Enseño trading de criptomonedas.

Mis productos:
- Curso Trading Pro: 297€ (20h vídeo, comunidad Telegram, Q&A semanales, plantillas, acceso de por vida)
- Mentoría 1:1: 500€/mes

Garantía: 30 días. Pagos: Stripe, PayPal, Bizum. Horario: L-V 9:00-18:00`}
          />

          <Button
            onClick={handleGenerateKnowledge}
            disabled={isGeneratingKnowledge || !aiKnowledgePrompt.trim()}
            className="bg-gradient-to-r from-primary to-accent hover:opacity-90"
          >
            {isGeneratingKnowledge ? (
              <>
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                Generando...
              </>
            ) : (
              <>
                <Wand2 className="w-4 h-4 mr-2" />
                Generar FAQs + Perfil
              </>
            )}
          </Button>
        </div>

        {/* Separator */}
        <div className="flex items-center gap-4">
          <div className="flex-1 h-px bg-border"></div>
          <span className="text-muted-foreground text-xs">o añade manualmente</span>
          <div className="flex-1 h-px bg-border"></div>
        </div>

        {/* Quick Templates */}
        <div className="flex flex-wrap gap-2">
          {faqTemplates.map((template, idx) => (
            <button
              key={idx}
              onClick={() => handleSelectTemplate(template)}
              className="px-3 py-1.5 text-xs rounded-full bg-secondary hover:bg-secondary/80 border border-border transition-colors"
            >
              {template.question}
            </button>
          ))}
        </div>

        {/* Manual Form */}
        {faqModalOpen && (
          <div className="rounded-lg p-4 bg-secondary/50 border border-border space-y-3">
            <Input
              value={faqQuestion}
              onChange={(e) => setFaqQuestion(e.target.value)}
              placeholder="Pregunta"
              className="bg-background border-border"
            />
            <Textarea
              value={faqAnswer}
              onChange={(e) => setFaqAnswer(e.target.value)}
              placeholder="Respuesta completa y específica..."
              className="bg-background border-border min-h-[80px] resize-none"
            />
            <div className="flex gap-2">
              <Button
                onClick={handleAddFAQ}
                disabled={!faqQuestion.trim() || !faqAnswer.trim() || addFAQMutation.isPending}
                size="sm"
              >
                {addFAQMutation.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                Añadir
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => { setFaqModalOpen(false); setFaqQuestion(""); setFaqAnswer(""); }}
              >
                Cancelar
              </Button>
            </div>
          </div>
        )}

        {!faqModalOpen && (
          <button
            onClick={() => setFaqModalOpen(true)}
            className="flex items-center gap-2 text-primary hover:text-primary/80 text-sm transition-colors"
          >
            <Plus className="w-4 h-4" />
            Añadir FAQ manualmente
          </button>
        )}

        {/* FAQs List */}
        {knowledgeLoading ? (
          <div className="space-y-3 animate-pulse">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-20 rounded-lg bg-muted/20 border border-border/20" />
            ))}
          </div>
        ) : (knowledgeData?.faqs || []).length > 0 ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              FAQs guardadas ({(knowledgeData?.faqs || []).length}):
            </p>
            {(knowledgeData?.faqs || []).map((faq) => (
              <div key={faq.id} className="rounded-lg p-4 bg-secondary/30 border border-border/50">
                {editingFaq?.id === faq.id ? (
                  <div className="space-y-3">
                    <Input
                      value={editingFaq.question}
                      onChange={(e) => setEditingFaq({ ...editingFaq, question: e.target.value })}
                      placeholder="Pregunta"
                      className="bg-background border-border"
                    />
                    <Textarea
                      value={editingFaq.answer}
                      onChange={(e) => setEditingFaq({ ...editingFaq, answer: e.target.value })}
                      placeholder="Respuesta"
                      className="bg-background border-border min-h-[80px]"
                    />
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditingFaq(null)}
                      >
                        Cancelar
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleUpdateFAQ}
                        disabled={updateFAQMutation.isPending || !editingFaq.question.trim() || !editingFaq.answer.trim()}
                      >
                        {updateFAQMutation.isPending ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <>
                            <Check className="w-4 h-4 mr-1" />
                            Guardar
                          </>
                        )}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex justify-between items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-primary">{faq.question}</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        {faq.answer.length > 200 ? `${faq.answer.slice(0, 200)}...` : faq.answer}
                      </p>
                    </div>
                    <div className="flex shrink-0">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setEditingFaq({ id: faq.id, question: faq.question, answer: faq.answer })}
                        className="text-muted-foreground hover:text-primary"
                      >
                        <Pencil className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDeleteFAQ(faq.id)}
                        disabled={deleteFAQMutation.isPending}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : !faqModalOpen ? (
          <div className="text-center py-8 text-muted-foreground">
            <HelpCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>No hay FAQs todavía</p>
            <p className="text-sm">Genera con IA o añade manualmente</p>
          </div>
        ) : null}
      </div>

      {/* 3. PRODUCTOS AUTO-SYNC */}
      <div className="metric-card">
        <div className="flex items-center gap-2 mb-4">
          <Package className="w-5 h-5 text-success" />
          <h3 className="font-semibold">Tus productos</h3>
          <span className="text-xs bg-secondary px-2 py-0.5 rounded-full text-muted-foreground flex items-center gap-1">
            <RefreshCw className="w-3 h-3" /> Auto-sync
          </span>
        </div>

        {products.length > 0 ? (
          <div className="space-y-2">
            {products.map((product) => (
              <div key={product.id} className="flex justify-between items-center p-3 bg-secondary/30 rounded-lg">
                <div>
                  <span className="font-medium">{product.name}</span>
                  {product.description && (
                    <p className="text-xs text-muted-foreground">{product.description.slice(0, 50)}...</p>
                  )}
                </div>
                <span className="text-success font-medium">{product.price}€</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">No hay productos. Añádelos en la página Products.</p>
        )}

        <p className="text-xs text-muted-foreground mt-3">El bot usará esta información automáticamente</p>
      </div>
    </div>
  );
}
