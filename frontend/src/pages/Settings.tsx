import { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Bot, Link2, Package, Save, RefreshCw, Loader2, AlertCircle, Plus, Trash2, BookOpen, Check, Sparkles, Wand2, HelpCircle, User, ChevronDown } from "lucide-react";

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
import { useCreatorConfig, useProducts, useUpdateConfig, useAddProduct, useUpdateProduct, useDeleteProduct, useKnowledge, useAddFAQ, useDeleteFAQ, useGenerateKnowledge, useConnections, useUpdateConnection, useDisconnectPlatform } from "@/hooks/useApi";
import { startOAuth, API_URL } from "@/services/api";
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
  const { data: knowledgeData, isLoading: knowledgeLoading } = useKnowledge();
  const addFAQMutation = useAddFAQ();
  const deleteFAQMutation = useDeleteFAQ();
  const generateKnowledgeMutation = useGenerateKnowledge();
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
  const [selectedPreset, setSelectedPreset] = useState<string | null>("amigo");
  const [aiPrompt, setAiPrompt] = useState("");
  const [isGeneratingAI, setIsGeneratingAI] = useState(false);
  const [rules, setRules] = useState("");

  // Personality presets (4 opciones, sin Custom separado)
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

  // Product modal state
  const [productModalOpen, setProductModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [productForm, setProductForm] = useState<ProductFormData>(emptyProduct);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [productToDelete, setProductToDelete] = useState<Product | null>(null);

  // Knowledge base state
  const [faqQuestion, setFaqQuestion] = useState("");
  const [faqAnswer, setFaqAnswer] = useState("");
  const [faqModalOpen, setFaqModalOpen] = useState(false);
  const [aiKnowledgePrompt, setAiKnowledgePrompt] = useState("");
  const [isGeneratingKnowledge, setIsGeneratingKnowledge] = useState(false);

  // About section state
  const [aboutOpen, setAboutOpen] = useState(false);
  const [aboutData, setAboutData] = useState({
    bio: "",
    specialties: "",
    experience: "",
    audience: ""
  });

  // FAQ Templates
  const faqTemplates = [
    { question: "¿Cuánto cuesta?", answer: "" },
    { question: "¿Qué incluye?", answer: "" },
    { question: "¿Hay garantía?", answer: "" },
    { question: "¿Cómo pago?", answer: "" },
    { question: "¿Cuál es el horario?", answer: "" },
    { question: "¿Ofrecen soporte?", answer: "" },
  ];

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
      setRules(config.clone_vocabulary || "");
      // Try to match a preset
      const matchingPreset = personalityPresets.find(p => p.rules === config.clone_vocabulary);
      setSelectedPreset(matchingPreset?.id || null);
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
      // Call AI endpoint to generate rules
      const response = await fetch("/api/ai/generate-rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: aiPrompt }),
      });

      if (response.ok) {
        const data = await response.json();
        setRules(data.rules || "");
        setSelectedPreset(null); // Ya no es un preset, es custom
        setAiPrompt("");
        toast({
          title: "Instrucciones generadas",
          description: "Puedes editarlas antes de guardar.",
        });
      } else {
        throw new Error("Error al generar");
      }
    } catch (error) {
      // Fallback: generar localmente si el endpoint no existe
      const generatedRules = `- ${aiPrompt.split(',').map(s => s.trim()).filter(Boolean).join('\n- ')}`;
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
        clone_vocabulary: rules, // Guardamos las rules como vocabulary
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

  // FAQ handlers
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
      // Use new endpoint that generates both FAQs and About
      const response = await fetch(`${API_URL}/api/ai/generate-knowledge-full`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: aiKnowledgePrompt }),
      });

      if (!response.ok) throw new Error("Error generating knowledge");

      const result = await response.json();

      // Add generated FAQs
      if (result.faqs && result.faqs.length > 0) {
        for (const faq of result.faqs) {
          await addFAQMutation.mutateAsync({
            question: faq.question,
            answer: faq.answer,
          });
        }
      }

      // Update About data if returned
      if (result.about) {
        setAboutData(prev => ({
          bio: result.about.bio || prev.bio,
          specialties: result.about.specialties || prev.specialties,
          experience: result.about.experience || prev.experience,
          audience: result.about.audience || prev.audience,
        }));
        setAboutOpen(true); // Open to show the user
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
              <Bot className="w-4 h-4 mr-1 sm:mr-2" />
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
          {/* Bot Name */}
          <div className="metric-card">
            <Label htmlFor="botName" className="text-base font-semibold mb-3 block">Nombre del bot</Label>
            <Input
              id="botName"
              value={botName}
              onChange={(e) => setBotName(e.target.value)}
              className="bg-secondary border-0"
              placeholder="Tu nombre o marca"
            />
          </div>

          {/* Presets - 4 opciones */}
          <div className="metric-card">
            <h3 className="text-lg font-semibold mb-2">Estilo de comunicación</h3>
            <p className="text-muted-foreground text-sm mb-4">Elige un estilo base o personaliza con IA</p>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {personalityPresets.map((preset) => (
                <button
                  key={preset.id}
                  onClick={() => handlePresetSelect(preset.id)}
                  className={cn(
                    "p-4 rounded-xl border-2 text-center transition-all hover:scale-105",
                    selectedPreset === preset.id
                      ? "border-primary bg-primary/10 shadow-lg shadow-primary/20"
                      : "border-border/50 bg-secondary/30 hover:border-primary/30"
                  )}
                >
                  <span className="text-2xl block mb-2">{preset.emoji}</span>
                  <span className="text-sm font-medium">{preset.label}</span>
                  {selectedPreset === preset.id && (
                    <Check className="w-4 h-4 text-primary mx-auto mt-2" />
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Personalizar con IA - gradient background */}
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

        {/* Knowledge Base Tab - Complete Redesign */}
        <TabsContent value="knowledge" className="animate-fade-in space-y-6">

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
                      placeholder="Trading, criptomonedas, análisis técnico"
                      className="bg-secondary border-0"
                    />
                  </div>
                  <div>
                    <Label className="text-sm text-muted-foreground mb-2 block">Experiencia</Label>
                    <Input
                      value={aboutData.experience}
                      onChange={(e) => setAboutData({...aboutData, experience: e.target.value})}
                      placeholder="6 años"
                      className="bg-secondary border-0"
                    />
                  </div>
                </div>

                <div>
                  <Label className="text-sm text-muted-foreground mb-2 block">Público objetivo</Label>
                  <Input
                    value={aboutData.audience}
                    onChange={(e) => setAboutData({...aboutData, audience: e.target.value})}
                    placeholder="Personas que quieren aprender a invertir"
                    className="bg-secondary border-0"
                  />
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
                placeholder="Soy Manel, trader profesional desde 2018. Enseño trading de criptomonedas.

Mis productos:
- Curso Trading Pro: 297€ (20h vídeo, comunidad Telegram, Q&A semanales, plantillas, acceso de por vida)
- Mentoría 1:1: 500€/mes

Garantía: 30 días. Pagos: Stripe, PayPal, Bizum. Horario: L-V 9:00-18:00"
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
              <div className="flex justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
              </div>
            ) : (knowledgeData?.faqs || []).length > 0 ? (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  FAQs guardadas ({(knowledgeData?.faqs || []).length}):
                </p>
                {(knowledgeData?.faqs || []).map((faq) => (
                  <div key={faq.id} className="rounded-lg p-4 bg-secondary/30 border border-border/50">
                    <div className="flex justify-between items-start gap-3">
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-primary">{faq.question}</p>
                        <p className="text-sm text-muted-foreground mt-1">
                          {faq.answer.length > 200 ? `${faq.answer.slice(0, 200)}...` : faq.answer}
                        </p>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDeleteFAQ(faq.id)}
                        disabled={deleteFAQMutation.isPending}
                        className="shrink-0 text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
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
