import { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Bot, Link2, Package, User, Save, RefreshCw, Loader2, AlertCircle, Plus, Pencil, Trash2, BookOpen, Check, Sparkles } from "lucide-react";

// Platform SVG Logos
const PlatformLogo = ({ platform, size = 20 }: { platform: string; size?: number }) => {
  switch (platform) {
    case "instagram":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <defs>
            <linearGradient id="ig-grad" x1="0%" y1="100%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#FFDC80"/>
              <stop offset="25%" stopColor="#F77737"/>
              <stop offset="50%" stopColor="#E1306C"/>
              <stop offset="75%" stopColor="#C13584"/>
              <stop offset="100%" stopColor="#833AB4"/>
            </linearGradient>
          </defs>
          <rect width="24" height="24" rx="6" fill="url(#ig-grad)"/>
          <circle cx="12" cy="12" r="4" stroke="white" strokeWidth="2" fill="none"/>
          <circle cx="17.5" cy="6.5" r="1.5" fill="white"/>
        </svg>
      );
    case "telegram":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="12" fill="#0088CC"/>
          <path d="M5 12l2.5 2 2-4 7-3-1.5 9-4-2-2 3-1-4z" fill="white"/>
        </svg>
      );
    case "whatsapp":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="12" fill="#25D366"/>
          <path d="M17 14.5c-.3-.15-1.7-.85-2-1-.3-.1-.5-.15-.7.15-.2.3-.8 1-.95 1.2-.2.2-.35.2-.65.05-.3-.15-1.3-.5-2.4-1.5-.9-.8-1.5-1.8-1.7-2.1-.15-.3 0-.45.15-.6.1-.1.3-.3.4-.45.15-.15.2-.25.3-.45.1-.2 0-.35-.05-.5-.05-.15-.7-1.7-.95-2.3-.25-.6-.5-.5-.7-.5h-.6c-.2 0-.5.05-.75.35-.25.3-1 1-1 2.4s1 2.8 1.15 3c.15.2 2 3 4.8 4.2.7.3 1.2.5 1.65.6.7.2 1.3.15 1.8.1.55-.1 1.7-.7 1.95-1.4.25-.7.25-1.25.15-1.4-.05-.1-.25-.2-.55-.35z" fill="white"/>
        </svg>
      );
    case "stripe":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <rect width="24" height="24" rx="4" fill="#635BFF"/>
          <path d="M11 8c-1.5 0-2.5.5-2.5 1.5 0 2 4 1.5 4 3 0 .7-.7 1.5-2.5 1.5-1.5 0-2.5-.5-3-1v2c.5.5 1.5 1 3 1 2 0 3.5-1 3.5-2.5 0-2.5-4-2-4-3.5 0-.5.5-1 1.5-1 1 0 2 .3 2.5.7V8.5c-.5-.3-1.5-.5-2.5-.5z" fill="white"/>
        </svg>
      );
    case "paypal":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <rect width="24" height="24" rx="4" fill="#003087"/>
          <path d="M9 6h4c2 0 3 1 3 2.5S15 11 13 11h-2l-.5 3H8l1-8zm2 3h1.5c.5 0 1-.3 1-.8 0-.4-.3-.7-.8-.7H11l-.2 1.5h.2z" fill="white"/>
          <path d="M7 9h4c2 0 3 1 3 2.5S13 14 11 14H9l-.5 3H6l1-8z" fill="#009CDE"/>
        </svg>
      );
    case "google":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <rect width="24" height="24" rx="4" fill="#fff"/>
          <path d="M12 4L4 8v8l8 4 8-4V8l-8-4z" fill="#00897B"/>
          <path d="M12 4l8 4v8" fill="#00AC47"/>
          <path d="M12 4L4 8v8" fill="#4285F4"/>
          <path d="M12 20l8-4" fill="#FFBA00"/>
          <path d="M12 20L4 16" fill="#EA4335"/>
          <circle cx="12" cy="12" r="3" fill="white"/>
        </svg>
      );
    default:
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <rect width="24" height="24" rx="4" fill="#6366F1"/>
          <circle cx="12" cy="12" r="4" stroke="white" strokeWidth="2"/>
        </svg>
      );
  }
};
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useCreatorConfig, useProducts, useUpdateConfig, useAddProduct, useUpdateProduct, useDeleteProduct, useAddContent, useKnowledge, useDeleteKnowledge, useConnections, useUpdateConnection, useDisconnectPlatform } from "@/hooks/useApi";
import { startOAuth } from "@/services/api";
import { useToast } from "@/hooks/use-toast";
import type { Product } from "@/types/api";

interface ConnectionConfig {
  key: string;
  name: string;
  icon: string;
  description: string;
  oauth: boolean;  // true = OAuth flow, false = manual token
  comingSoon?: boolean;  // true = show "Coming Soon" badge
  oauthHelp?: string;  // Help text for manual entry
  section: "messaging" | "payments" | "scheduling";  // Section grouping
  fields?: Array<{
    name: string;
    label: string;
    placeholder: string;
    type: "token" | "page_id" | "phone_id" | "link" | "meeting_id";
  }>;
}

const connectionConfigs: ConnectionConfig[] = [
  // Social & Messaging
  {
    key: "instagram",
    name: "Instagram",
    icon: "📸",
    description: "Automate your Instagram DMs",
    oauth: true,
    section: "messaging",
  },
  {
    key: "telegram",
    name: "Telegram",
    icon: "✈️",
    description: "Create bot in 1 min via @BotFather",
    oauth: false,
    section: "messaging",
    oauthHelp: "🤖 Setup rápido (1 minuto):\n\n1. Abre Telegram y busca @BotFather\n2. Envía /newbot y sigue instrucciones\n3. Copia el token y pégalo aquí",
    fields: [
      { name: "token", label: "Bot Token", placeholder: "123456:ABC-DEF...", type: "token" },
    ],
  },
  {
    key: "whatsapp",
    name: "WhatsApp",
    icon: "💬",
    description: "WhatsApp Business API",
    oauth: true,
    section: "messaging",
  },
  // Payments
  {
    key: "stripe",
    name: "Stripe",
    icon: "💳",
    description: "Track payments automatically",
    oauth: true,
    section: "payments",
  },
  {
    key: "paypal",
    name: "PayPal",
    icon: "🅿️",
    description: "Track PayPal payments",
    oauth: true,
    section: "payments",
  },
  // Scheduling
  {
    key: "google",
    name: "Google Calendar + Meet",
    icon: "🎥",
    description: "Auto-create Google Meet links for bookings",
    oauth: true,
    section: "scheduling",
  },
];

// Section labels
const sectionLabels = {
  messaging: { title: "Social & Messaging", icon: "💬", description: "Connect your communication channels" },
  payments: { title: "Payments", icon: "💰", description: "Track and manage payments" },
  scheduling: { title: "Scheduling", icon: "📅", description: "Calendar and video call integrations" },
};

interface ProductFormData {
  name: string;
  description: string;
  price: number;
  currency: string;
  payment_link: string;  // Backend expects payment_link, not url
  is_active: boolean;    // Backend expects is_active, not active
}

const emptyProduct: ProductFormData = {
  name: "",
  description: "",
  price: 0,
  currency: "EUR",
  payment_link: "",
  is_active: true,
};

export default function Settings() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Get tab from URL params, default to "personality"
  const tabFromUrl = searchParams.get("tab") || "personality";
  const [activeTab, setActiveTab] = useState(tabFromUrl);

  const { data: configData, isLoading: configLoading, error: configError } = useCreatorConfig();
  const { data: productsData, isLoading: productsLoading } = useProducts();
  const updateConfig = useUpdateConfig();
  const addProductMutation = useAddProduct();
  const updateProductMutation = useUpdateProduct();
  const deleteProductMutation = useDeleteProduct();
  const addContentMutation = useAddContent();
  const { data: knowledgeData, isLoading: knowledgeLoading } = useKnowledge();
  const deleteKnowledgeMutation = useDeleteKnowledge();
  const { data: connectionsData, isLoading: connectionsLoading } = useConnections();
  const updateConnectionMutation = useUpdateConnection();
  const disconnectMutation = useDisconnectPlatform();
  const { toast } = useToast();

  // Extract config from response
  const config = configData?.config;

  // Connection form state
  const [editingConnection, setEditingConnection] = useState<string | null>(null);
  const [connectionForm, setConnectionForm] = useState<Record<string, string>>({});

  // Local form state
  const [botName, setBotName] = useState("");
  const [tone, setTone] = useState("friendly");
  const [vocabulary, setVocabulary] = useState("");
  const [previewMessage, setPreviewMessage] = useState("");
  const [selectedPreset, setSelectedPreset] = useState("custom");
  const [aiPrompt, setAiPrompt] = useState("");
  const [isGeneratingAI, setIsGeneratingAI] = useState(false);

  // Personality presets
  const personalityPresets = [
    {
      id: "amigo",
      emoji: "😊",
      label: "Amigo",
      tone: "friendly",
      vocabulary: "Usa un tono cercano y cálido. Tutea siempre. Usa emojis ocasionalmente. Sé empático y comprensivo. Responde como un amigo de confianza que quiere ayudar."
    },
    {
      id: "mentor",
      emoji: "🎓",
      label: "Mentor",
      tone: "professional",
      vocabulary: "Actúa como un mentor experto. Ofrece consejos valiosos basados en experiencia. Guía al usuario paso a paso. Sé inspirador pero realista. Comparte conocimiento de manera estructurada."
    },
    {
      id: "vendedor",
      emoji: "🎯",
      label: "Vendedor",
      tone: "friendly",
      vocabulary: "Enfócate en los beneficios y resultados. Crea urgencia de manera natural. Maneja objeciones con empatía. Destaca testimonios y casos de éxito. Guía hacia la conversión sin ser agresivo."
    },
    {
      id: "profesional",
      emoji: "💼",
      label: "Profesional",
      tone: "professional",
      vocabulary: "Mantén un tono formal pero accesible. Sé preciso y conciso. Evita jerga informal. Demuestra expertise y credibilidad. Responde de manera estructurada y clara."
    },
    {
      id: "custom",
      emoji: "✨",
      label: "Custom",
      tone: "friendly",
      vocabulary: ""
    },
  ];

  // Product modal state
  const [productModalOpen, setProductModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [productForm, setProductForm] = useState<ProductFormData>(emptyProduct);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [productToDelete, setProductToDelete] = useState<Product | null>(null);

  // Knowledge base state
  const [faqContent, setFaqContent] = useState("");

  // Other payment methods state
  const [otherPaymentMethods, setOtherPaymentMethods] = useState({
    bizum: { enabled: false, phone: "", holder_name: "" },
    bank_transfer: { enabled: false, iban: "", holder_name: "" },
    revolut: { enabled: false, link: "" },
    other: { enabled: false, instructions: "" },
  });
  const [editingPaymentMethod, setEditingPaymentMethod] = useState<string | null>(null);

  // Helper to mask IBAN (show first 4 and last 4 chars)
  const maskIban = (iban: string) => {
    if (!iban || iban.length < 10) return iban;
    return `${iban.slice(0, 4)}****${iban.slice(-4)}`;
  };

  // Load payment methods from config
  useEffect(() => {
    if (config?.other_payment_methods) {
      setOtherPaymentMethods(prev => ({
        ...prev,
        ...config.other_payment_methods,
      }));
    }
  }, [config]);

  const handleSavePaymentMethods = async (closeEditing = true) => {
    try {
      await updateConfig.mutateAsync({
        other_payment_methods: otherPaymentMethods,
      });
      if (closeEditing) {
        setEditingPaymentMethod(null);
      }
      toast({
        title: "Saved",
        description: "Payment method updated.",
      });
    } catch (error) {
      toast({
        title: "Error saving payment methods",
        description: error instanceof Error ? error.message : "Failed to save",
        variant: "destructive",
      });
    }
  };

  const handleTogglePaymentMethod = async (method: string, enabled: boolean) => {
    const updatedMethods = {
      ...otherPaymentMethods,
      [method]: { ...otherPaymentMethods[method as keyof typeof otherPaymentMethods], enabled }
    };
    setOtherPaymentMethods(updatedMethods);
    // Auto-save when toggling
    try {
      await updateConfig.mutateAsync({
        other_payment_methods: updatedMethods,
      });
    } catch (error) {
      // Revert on error
      setOtherPaymentMethods(otherPaymentMethods);
    }
  };

  // Sync form state with API data
  useEffect(() => {
    if (config) {
      setBotName(config.clone_name || "");
      setTone(config.clone_tone || "friendly");
      setVocabulary(config.clone_vocabulary || "");
    }
  }, [config]);

  const generatePreview = () => {
    const previews = {
      friendly: "Hey there! Super excited to chat with you. How can I help you level up your creator game today?",
      professional: "Hello! Thank you for reaching out. I'm here to assist you with any questions about our programs.",
      casual: "Yo! What's up? Got questions? I've got answers. Let's do this!",
    };
    setPreviewMessage(previews[tone as keyof typeof previews] || previews.friendly);
  };

  const handlePresetSelect = (presetId: string) => {
    setSelectedPreset(presetId);
    const preset = personalityPresets.find(p => p.id === presetId);
    if (preset && presetId !== "custom") {
      setTone(preset.tone);
      setVocabulary(preset.vocabulary);
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
      // Generate a personality based on the AI prompt
      const generatedVocabulary = `${vocabulary ? vocabulary + "\n\n" : ""}Instrucciones personalizadas: ${aiPrompt}`;
      setVocabulary(generatedVocabulary);
      setSelectedPreset("custom");
      setAiPrompt("");
      toast({
        title: "Personalidad actualizada",
        description: "Se han añadido las instrucciones a tu configuración.",
      });
    } catch (error) {
      toast({
        title: "Error generando personalidad",
        description: "Intenta de nuevo más tarde.",
        variant: "destructive",
      });
    } finally {
      setIsGeneratingAI(false);
    }
  };

  const handleSavePersonality = async () => {
    try {
      await updateConfig.mutateAsync({
        clone_name: botName,
        clone_tone: tone,
        clone_vocabulary: vocabulary,
      });
      toast({
        title: "Guardado",
        description: "La personalidad del bot ha sido actualizada.",
      });
      // Invalidate queries to refresh data
      await queryClient.invalidateQueries({ queryKey: ["creatorConfig"] });
    } catch (error) {
      toast({
        title: "Error al guardar",
        description: error instanceof Error ? error.message : "No se pudo guardar la configuración",
        variant: "destructive",
      });
    }
  };

  // Product handlers
  const openAddProduct = () => {
    setEditingProduct(null);
    setProductForm(emptyProduct);
    setProductModalOpen(true);
  };

  const openEditProduct = (product: Product) => {
    setEditingProduct(product);
    setProductForm({
      name: product.name,
      description: product.description || "",
      price: product.price,
      currency: product.currency || "EUR",
      payment_link: product.payment_link || product.url || "",
      is_active: product.is_active ?? product.active ?? true,
    });
    setProductModalOpen(true);
  };

  const handleSaveProduct = async () => {
    try {
      if (editingProduct) {
        await updateProductMutation.mutateAsync({
          productId: editingProduct.id,
          product: productForm,
        });
        toast({ title: "Product updated", description: `${productForm.name} has been updated.` });
      } else {
        await addProductMutation.mutateAsync(productForm as Omit<Product, "id">);
        toast({ title: "Product added", description: `${productForm.name} has been created.` });
      }
      setProductModalOpen(false);
      // Invalidate onboarding to refresh status and redirect to home
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      navigate("/");
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to save product",
        variant: "destructive",
      });
    }
  };

  const handleDeleteProduct = async () => {
    if (!productToDelete) return;
    try {
      await deleteProductMutation.mutateAsync(productToDelete.id);
      toast({ title: "Product deleted", description: `${productToDelete.name} has been removed.` });
      setDeleteConfirmOpen(false);
      setProductToDelete(null);
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to delete product",
        variant: "destructive",
      });
    }
  };

  const confirmDelete = (product: Product) => {
    setProductToDelete(product);
    setDeleteConfirmOpen(true);
  };

  // Knowledge base handler
  const handleAddContent = async () => {
    if (!faqContent.trim()) return;
    try {
      await addContentMutation.mutateAsync({ text: faqContent, docType: "faq" });
      toast({ title: "Content added", description: "FAQ has been added to knowledge base." });
      setFaqContent("");
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to add content",
        variant: "destructive",
      });
    }
  };

  const handleDeleteKnowledge = async (itemId: string) => {
    try {
      await deleteKnowledgeMutation.mutateAsync(itemId);
      toast({ title: "FAQ deleted", description: "Item removed from knowledge base." });
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to delete",
        variant: "destructive",
      });
    }
  };

  const products = productsData?.products || [];
  const knowledgeItems = knowledgeData?.items || [];

  // Loading state
  if (configLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  // Error state
  if (configError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <AlertCircle className="w-12 h-12 text-destructive" />
        <p className="text-muted-foreground">Failed to load settings</p>
        <p className="text-sm text-destructive">{configError.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground text-sm sm:text-base">Configure your bot personality and integrations</p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
          <TabsList className="bg-secondary p-1 rounded-xl w-max sm:w-auto">
            <TabsTrigger value="personality" className="rounded-lg data-[state=active]:bg-card text-xs sm:text-sm">
              <User className="w-4 h-4 mr-1 sm:mr-2" />
              <span className="hidden sm:inline">Personality</span>
              <span className="sm:hidden">Bot</span>
            </TabsTrigger>
            <TabsTrigger value="connections" className="rounded-lg data-[state=active]:bg-card text-xs sm:text-sm">
              <Link2 className="w-4 h-4 mr-1 sm:mr-2" />
              <span className="hidden sm:inline">Connections</span>
              <span className="sm:hidden">Links</span>
            </TabsTrigger>
            <TabsTrigger value="knowledge" className="rounded-lg data-[state=active]:bg-card text-xs sm:text-sm">
              <BookOpen className="w-4 h-4 mr-1 sm:mr-2" />
              <span className="hidden sm:inline">Knowledge</span>
              <span className="sm:hidden">KB</span>
            </TabsTrigger>
          </TabsList>
        </div>

        {/* Personality Tab */}
        <TabsContent value="personality" className="space-y-6 animate-fade-in">
          {/* Personality Presets */}
          <div className="metric-card">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <span className="text-xl">🎭</span>
              </div>
              <div>
                <h3 className="font-semibold">Elige un estilo de personalidad</h3>
                <p className="text-sm text-muted-foreground">Selecciona un preset o personaliza tu asistente</p>
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
              {personalityPresets.map((preset) => (
                <button
                  key={preset.id}
                  onClick={() => handlePresetSelect(preset.id)}
                  className={cn(
                    "flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all hover:scale-105",
                    selectedPreset === preset.id
                      ? "border-primary bg-primary/10 shadow-lg shadow-primary/20"
                      : "border-border/50 bg-secondary/30 hover:border-primary/30"
                  )}
                >
                  <span className="text-2xl">{preset.emoji}</span>
                  <span className="text-sm font-medium">{preset.label}</span>
                  {selectedPreset === preset.id && (
                    <Check className="w-4 h-4 text-primary" />
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* AI Personalization */}
          <div className="metric-card">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center">
                <span className="text-xl">🤖</span>
              </div>
              <div>
                <h3 className="font-semibold">Personalizar con IA</h3>
                <p className="text-sm text-muted-foreground">Describe cómo quieres que sea tu asistente</p>
              </div>
            </div>
            <div className="flex gap-2">
              <Input
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                className="bg-secondary border-0 flex-1"
                placeholder="Ej: Quiero que sea divertido, use memes y hable como un amigo cercano..."
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleGenerateAIPersonality();
                  }
                }}
              />
              <Button
                onClick={handleGenerateAIPersonality}
                disabled={isGeneratingAI || !aiPrompt.trim()}
                className="bg-gradient-to-r from-accent to-primary hover:opacity-90"
              >
                {isGeneratingAI ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Sparkles className="w-4 h-4" />
                )}
              </Button>
            </div>
          </div>

          {/* Bot Configuration */}
          <div className="metric-card space-y-6">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <Bot className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h3 className="font-semibold">Configuración del Bot</h3>
                <p className="text-sm text-muted-foreground">Ajusta los detalles de tu asistente</p>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="botName">Nombre del Bot</Label>
              <Input
                id="botName"
                value={botName}
                onChange={(e) => setBotName(e.target.value)}
                className="bg-secondary border-0"
                placeholder="Ej: Asistente de María..."
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="tone">Tono de comunicación</Label>
              <Select value={tone} onValueChange={(value) => {
                setTone(value);
                setSelectedPreset("custom");
              }}>
                <SelectTrigger className="bg-secondary border-0">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="friendly">😊 Amigable y cálido</SelectItem>
                  <SelectItem value="professional">💼 Profesional</SelectItem>
                  <SelectItem value="casual">😎 Casual y divertido</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="vocabulary">Instrucciones personalizadas</Label>
              <Textarea
                id="vocabulary"
                value={vocabulary}
                onChange={(e) => {
                  setVocabulary(e.target.value);
                  setSelectedPreset("custom");
                }}
                className="bg-secondary border-0 min-h-[120px]"
                placeholder="Añade instrucciones específicas para tu bot... Ej: 'Siempre menciona que tengo 5 años de experiencia', 'Ofrece una llamada gratuita de 15 minutos'..."
              />
            </div>

            <div className="pt-4 border-t border-border/50">
              <div className="flex items-center justify-between mb-4">
                <Label>Vista previa de respuesta</Label>
                <Button variant="outline" size="sm" onClick={generatePreview}>
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Generar Preview
                </Button>
              </div>
              {previewMessage && (
                <div className="p-4 rounded-xl bg-gradient-to-br from-primary/10 to-accent/10 border border-primary/20">
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center shrink-0">
                      <Bot className="w-4 h-4 text-white" />
                    </div>
                    <p className="text-sm">{previewMessage}</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          <Button
            className="w-full bg-gradient-to-r from-primary to-accent hover:opacity-90 transition-opacity"
            onClick={handleSavePersonality}
            disabled={updateConfig.isPending}
          >
            {updateConfig.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Save className="w-4 h-4 mr-2" />
            )}
            Guardar Cambios
          </Button>
        </TabsContent>

        {/* Connections Tab */}
        <TabsContent value="connections" className="animate-fade-in">
          {connectionsLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
            </div>
          ) : (
            <div className="space-y-6">
              {/* Social & Messaging Section */}
              <div className="metric-card">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                    <span className="text-xl">💬</span>
                  </div>
                  <div>
                    <h3 className="font-semibold">Social & Messaging</h3>
                    <p className="text-sm text-muted-foreground">Connect your communication channels</p>
                  </div>
                </div>
                <div className="space-y-2">
                  {connectionConfigs.filter(c => c.section === "messaging").map((conn) => {
                    const status = connectionsData?.[conn.key as keyof typeof connectionsData];
                    const isConnected = status?.connected || false;
                    const isEditing = editingConnection === conn.key;

                    return (
                      <div key={conn.key}>
                        <div className="flex items-center justify-between p-4 rounded-lg border bg-card hover:border-primary/30 transition-colors">
                          <div className="flex items-center gap-4">
                            <div className="w-10 h-10 rounded-lg bg-secondary flex items-center justify-center">
                              <PlatformLogo platform={conn.key} size={24} />
                            </div>
                            <div>
                              <p className="font-medium">{conn.name}</p>
                              <p className="text-sm text-muted-foreground">
                                {isConnected
                                  ? (status?.username || status?.masked_token || "Connected")
                                  : conn.description}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            {isConnected ? (
                              <>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => disconnectMutation.mutate(conn.key)}
                                  className="text-destructive hover:bg-destructive/10"
                                >
                                  Disconnect
                                </Button>
                                <span className="text-sm text-success font-medium flex items-center gap-1">
                                  <Check className="w-4 h-4" /> Connected
                                </span>
                              </>
                            ) : conn.oauth ? (
                              <Button
                                size="sm"
                                onClick={() => startOAuth(conn.key).then(r => window.location.href = r.auth_url)}
                              >
                                Connect
                              </Button>
                            ) : (
                              <Button
                                size="sm"
                                variant={isEditing ? "outline" : "default"}
                                onClick={() => setEditingConnection(isEditing ? null : conn.key)}
                              >
                                {isEditing ? "Cancel" : "Connect"}
                              </Button>
                            )}
                          </div>
                        </div>
                        {/* Telegram form */}
                        {isEditing && !conn.oauth && conn.fields && (
                          <div className="mt-2 p-4 rounded-lg bg-secondary/50 space-y-3">
                            {conn.oauthHelp && (
                              <p className="text-sm text-muted-foreground whitespace-pre-line">{conn.oauthHelp}</p>
                            )}
                            <div className="flex gap-2">
                              <Input
                                placeholder={conn.fields[0]?.placeholder}
                                type="password"
                                value={connectionForm.token || ""}
                                onChange={(e) => setConnectionForm({ token: e.target.value })}
                                className="flex-1"
                              />
                              <Button
                                onClick={async () => {
                                  await updateConnectionMutation.mutateAsync({ platform: conn.key, data: connectionForm });
                                  toast({ title: `${conn.name} connected` });
                                  setEditingConnection(null);
                                  setConnectionForm({});
                                }}
                                disabled={!connectionForm.token}
                              >
                                Save
                              </Button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Payments Section */}
              <div className="metric-card">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-lg bg-success/10 flex items-center justify-center">
                    <span className="text-xl">💰</span>
                  </div>
                  <div>
                    <h3 className="font-semibold">Payments</h3>
                    <p className="text-sm text-muted-foreground">Track and manage payments</p>
                  </div>
                </div>

                {/* OAuth payments (Stripe, PayPal) */}
                <div className="space-y-2 mb-4">
                  {connectionConfigs.filter(c => c.section === "payments").map((conn) => {
                    const status = connectionsData?.[conn.key as keyof typeof connectionsData];
                    const isConnected = status?.connected || false;

                    return (
                      <div
                        key={conn.key}
                        className="flex items-center justify-between p-4 rounded-lg border bg-card hover:border-primary/30 transition-colors"
                      >
                        <div className="flex items-center gap-4">
                          <div className="w-10 h-10 rounded-lg bg-secondary flex items-center justify-center">
                            <PlatformLogo platform={conn.key} size={24} />
                          </div>
                          <div>
                            <p className="font-medium">{conn.name}</p>
                            <p className="text-sm text-muted-foreground">
                              {isConnected ? "Connected" : conn.description}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {isConnected ? (
                            <>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => disconnectMutation.mutate(conn.key)}
                                className="text-destructive hover:bg-destructive/10"
                              >
                                Disconnect
                              </Button>
                              <span className="text-sm text-success font-medium flex items-center gap-1">
                                <Check className="w-4 h-4" /> Connected
                              </span>
                            </>
                          ) : (
                            <Button
                              size="sm"
                              onClick={() => startOAuth(conn.key).then(r => window.location.href = r.auth_url)}
                            >
                              Connect
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Manual payment methods sub-card */}
                <div className="p-4 rounded-lg bg-secondary/30 border border-border/50">
                  <p className="text-sm font-medium mb-1">Alternative payment methods</p>
                  <p className="text-xs text-muted-foreground mb-4">Bot will mention these when customers ask about payment</p>

                  <div className="space-y-2">
                    {/* Bizum */}
                    <div className="flex items-center justify-between p-3 rounded-lg bg-card hover:bg-accent/5 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-orange-500/20 flex items-center justify-center text-orange-500 text-xs font-bold">B</div>
                        <div>
                          <p className="font-medium text-sm">Bizum</p>
                          <p className="text-xs text-muted-foreground">
                            {otherPaymentMethods.bizum.enabled && otherPaymentMethods.bizum.phone
                              ? `${otherPaymentMethods.bizum.phone}${otherPaymentMethods.bizum.holder_name ? ` · ${otherPaymentMethods.bizum.holder_name}` : ""}`
                              : "Mobile payments"}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {otherPaymentMethods.bizum.enabled && (
                          <Button variant="ghost" size="sm" onClick={() => setEditingPaymentMethod(editingPaymentMethod === "bizum" ? null : "bizum")}>
                            Edit
                          </Button>
                        )}
                        <Switch checked={otherPaymentMethods.bizum.enabled} onCheckedChange={(c) => handleTogglePaymentMethod("bizum", c)} />
                      </div>
                    </div>
                    {editingPaymentMethod === "bizum" && (
                      <div className="p-3 rounded-lg bg-secondary/50 flex gap-2">
                        <Input placeholder="Phone" value={otherPaymentMethods.bizum.phone} onChange={(e) => setOtherPaymentMethods(p => ({ ...p, bizum: { ...p.bizum, phone: e.target.value } }))} />
                        <Input placeholder="Name" value={otherPaymentMethods.bizum.holder_name} onChange={(e) => setOtherPaymentMethods(p => ({ ...p, bizum: { ...p.bizum, holder_name: e.target.value } }))} />
                        <Button size="sm" onClick={() => handleSavePaymentMethods(true)}>Save</Button>
                      </div>
                    )}

                    {/* Bank Transfer */}
                    <div className="flex items-center justify-between p-3 rounded-lg bg-card hover:bg-accent/5 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center text-blue-500 text-sm">🏦</div>
                        <div>
                          <p className="font-medium text-sm">Bank Transfer</p>
                          <p className="text-xs text-muted-foreground">
                            {otherPaymentMethods.bank_transfer.enabled && otherPaymentMethods.bank_transfer.iban
                              ? `${maskIban(otherPaymentMethods.bank_transfer.iban)}${otherPaymentMethods.bank_transfer.holder_name ? ` · ${otherPaymentMethods.bank_transfer.holder_name}` : ""}`
                              : "Direct bank transfers"}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {otherPaymentMethods.bank_transfer.enabled && (
                          <Button variant="ghost" size="sm" onClick={() => setEditingPaymentMethod(editingPaymentMethod === "bank_transfer" ? null : "bank_transfer")}>
                            Edit
                          </Button>
                        )}
                        <Switch checked={otherPaymentMethods.bank_transfer.enabled} onCheckedChange={(c) => handleTogglePaymentMethod("bank_transfer", c)} />
                      </div>
                    </div>
                    {editingPaymentMethod === "bank_transfer" && (
                      <div className="p-3 rounded-lg bg-secondary/50 flex gap-2">
                        <Input placeholder="IBAN" value={otherPaymentMethods.bank_transfer.iban} onChange={(e) => setOtherPaymentMethods(p => ({ ...p, bank_transfer: { ...p.bank_transfer, iban: e.target.value } }))} className="flex-1" />
                        <Input placeholder="Holder" value={otherPaymentMethods.bank_transfer.holder_name} onChange={(e) => setOtherPaymentMethods(p => ({ ...p, bank_transfer: { ...p.bank_transfer, holder_name: e.target.value } }))} className="w-32" />
                        <Button size="sm" onClick={() => handleSavePaymentMethods(true)}>Save</Button>
                      </div>
                    )}

                    {/* Revolut */}
                    <div className="flex items-center justify-between p-3 rounded-lg bg-card hover:bg-accent/5 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center text-purple-500 text-xs font-bold">R</div>
                        <div>
                          <p className="font-medium text-sm">Revolut / Wise</p>
                          <p className="text-xs text-muted-foreground">
                            {otherPaymentMethods.revolut.enabled && otherPaymentMethods.revolut.link
                              ? otherPaymentMethods.revolut.link
                              : "Digital wallets"}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {otherPaymentMethods.revolut.enabled && (
                          <Button variant="ghost" size="sm" onClick={() => setEditingPaymentMethod(editingPaymentMethod === "revolut" ? null : "revolut")}>
                            Edit
                          </Button>
                        )}
                        <Switch checked={otherPaymentMethods.revolut.enabled} onCheckedChange={(c) => handleTogglePaymentMethod("revolut", c)} />
                      </div>
                    </div>
                    {editingPaymentMethod === "revolut" && (
                      <div className="p-3 rounded-lg bg-secondary/50 flex gap-2">
                        <Input placeholder="@username or link" value={otherPaymentMethods.revolut.link} onChange={(e) => setOtherPaymentMethods(p => ({ ...p, revolut: { ...p.revolut, link: e.target.value } }))} className="flex-1" />
                        <Button size="sm" onClick={() => handleSavePaymentMethods(true)}>Save</Button>
                      </div>
                    )}

                    {/* Other */}
                    <div className="flex items-center justify-between p-3 rounded-lg bg-card hover:bg-accent/5 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-gray-500/20 flex items-center justify-center text-gray-500 text-sm">📝</div>
                        <div>
                          <p className="font-medium text-sm">Other</p>
                          <p className="text-xs text-muted-foreground truncate max-w-[200px]">
                            {otherPaymentMethods.other.enabled && otherPaymentMethods.other.instructions
                              ? otherPaymentMethods.other.instructions.slice(0, 30) + "..."
                              : "Custom instructions"}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {otherPaymentMethods.other.enabled && (
                          <Button variant="ghost" size="sm" onClick={() => setEditingPaymentMethod(editingPaymentMethod === "other" ? null : "other")}>
                            Edit
                          </Button>
                        )}
                        <Switch checked={otherPaymentMethods.other.enabled} onCheckedChange={(c) => handleTogglePaymentMethod("other", c)} />
                      </div>
                    </div>
                    {editingPaymentMethod === "other" && (
                      <div className="p-3 rounded-lg bg-secondary/50 space-y-2">
                        <Textarea placeholder="Custom payment instructions..." value={otherPaymentMethods.other.instructions} onChange={(e) => setOtherPaymentMethods(p => ({ ...p, other: { ...p.other, instructions: e.target.value } }))} className="min-h-[80px]" />
                        <Button size="sm" onClick={() => handleSavePaymentMethods(true)}>Save</Button>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Scheduling Section */}
              <div className="metric-card">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center">
                    <span className="text-xl">📅</span>
                  </div>
                  <div>
                    <h3 className="font-semibold">Scheduling</h3>
                    <p className="text-sm text-muted-foreground">Calendar and video call integrations</p>
                  </div>
                </div>
                <div className="space-y-2">
                  {connectionConfigs.filter(c => c.section === "scheduling").map((conn) => {
                    const status = connectionsData?.[conn.key as keyof typeof connectionsData];
                    const isConnected = status?.connected || false;

                    return (
                      <div
                        key={conn.key}
                        className="flex items-center justify-between p-4 rounded-lg border bg-card hover:border-primary/30 transition-colors"
                      >
                        <div className="flex items-center gap-4">
                          <div className="w-10 h-10 rounded-lg bg-secondary flex items-center justify-center">
                            <PlatformLogo platform={conn.key} size={24} />
                          </div>
                          <div>
                            <p className="font-medium">{conn.name}</p>
                            <p className="text-sm text-muted-foreground">
                              {isConnected ? "Connected" : conn.description}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {isConnected ? (
                            <>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => disconnectMutation.mutate(conn.key)}
                                className="text-destructive hover:bg-destructive/10"
                              >
                                Disconnect
                              </Button>
                              <span className="text-sm text-success font-medium flex items-center gap-1">
                                <Check className="w-4 h-4" /> Connected
                              </span>
                            </>
                          ) : (
                            <Button
                              size="sm"
                              onClick={() => startOAuth(conn.key).then(r => window.location.href = r.auth_url)}
                            >
                              Connect
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </TabsContent>

        {/* Knowledge Base Tab */}
        <TabsContent value="knowledge" className="animate-fade-in space-y-6">
          <div className="metric-card space-y-4">
            <div>
              <h3 className="font-semibold mb-2">Add to Knowledge Base</h3>
              <p className="text-sm text-muted-foreground">
                Add FAQs, product info, or any content your bot should know about.
              </p>
            </div>

            <Textarea
              value={faqContent}
              onChange={(e) => setFaqContent(e.target.value)}
              className="bg-secondary border-0 min-h-[150px]"
              placeholder="Example: Q: What are your business hours? A: We're available Monday to Friday, 9am to 6pm EST..."
            />

            <Button
              onClick={handleAddContent}
              disabled={!faqContent.trim() || addContentMutation.isPending}
              className="bg-gradient-to-r from-primary to-accent hover:opacity-90"
            >
              {addContentMutation.isPending ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Plus className="w-4 h-4 mr-2" />
              )}
              Add to Knowledge Base
            </Button>
          </div>

          {/* Saved FAQs */}
          <div className="metric-card space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">Saved Knowledge ({knowledgeItems.length})</h3>
            </div>

            {knowledgeLoading ? (
              <div className="flex justify-center py-4">
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
              </div>
            ) : knowledgeItems.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                No FAQs added yet. Add your first one above!
              </p>
            ) : (
              <div className="space-y-3">
                {knowledgeItems.map((item) => (
                  <div
                    key={item.id}
                    className="p-3 rounded-lg bg-secondary/50 flex items-start justify-between gap-3"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm whitespace-pre-wrap break-words">
                        {item.content.length > 200 ? `${item.content.slice(0, 200)}...` : item.content}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {item.doc_type} • {item.created_at ? new Date(item.created_at).toLocaleDateString() : ""}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDeleteKnowledge(item.id)}
                      disabled={deleteKnowledgeMutation.isPending}
                      className="shrink-0 text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="metric-card bg-secondary/30">
            <h3 className="font-semibold mb-2">Tips for Good FAQs</h3>
            <ul className="text-sm text-muted-foreground space-y-2">
              <li>• Use Q&A format: "Q: question A: answer"</li>
              <li>• Include product details, pricing, and features</li>
              <li>• Add common objections and how to handle them</li>
              <li>• Include your business hours and contact info</li>
            </ul>
          </div>
        </TabsContent>
      </Tabs>

      {/* Product Modal */}
      <Dialog open={productModalOpen} onOpenChange={setProductModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingProduct ? "Edit Product" : "Add New Product"}</DialogTitle>
            <DialogDescription>
              {editingProduct ? "Update product details" : "Create a new product for your bot to recommend"}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="productName">Product Name</Label>
              <Input
                id="productName"
                value={productForm.name}
                onChange={(e) => setProductForm({ ...productForm, name: e.target.value })}
                placeholder="e.g., Premium Coaching Program"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="productDescription">Description</Label>
              <Textarea
                id="productDescription"
                value={productForm.description}
                onChange={(e) => setProductForm({ ...productForm, description: e.target.value })}
                placeholder="Brief description of the product..."
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="productPrice">Price</Label>
                <Input
                  id="productPrice"
                  type="number"
                  value={productForm.price}
                  onChange={(e) => setProductForm({ ...productForm, price: Number(e.target.value) })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="productCurrency">Currency</Label>
                <Select
                  value={productForm.currency}
                  onValueChange={(v) => setProductForm({ ...productForm, currency: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="EUR">EUR (€)</SelectItem>
                    <SelectItem value="USD">USD ($)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="productUrl">Payment Link</Label>
              <Input
                id="productUrl"
                value={productForm.payment_link}
                onChange={(e) => setProductForm({ ...productForm, payment_link: e.target.value })}
                placeholder="https://stripe.com/pay/..."
              />
            </div>

            <div className="flex items-center justify-between">
              <Label htmlFor="productActive">Active</Label>
              <Switch
                id="productActive"
                checked={productForm.is_active}
                onCheckedChange={(v) => setProductForm({ ...productForm, is_active: v })}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setProductModalOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSaveProduct}
              disabled={!productForm.name || addProductMutation.isPending || updateProductMutation.isPending}
            >
              {(addProductMutation.isPending || updateProductMutation.isPending) && (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              )}
              {editingProduct ? "Save Changes" : "Add Product"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Product</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{productToDelete?.name}"? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteProduct}
              disabled={deleteProductMutation.isPending}
            >
              {deleteProductMutation.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
