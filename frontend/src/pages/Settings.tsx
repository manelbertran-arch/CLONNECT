import { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Bot, Link2, Package, User, Save, RefreshCw, Loader2, AlertCircle, Plus, Pencil, Trash2, BookOpen, Check } from "lucide-react";

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
    case "calendly":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="12" fill="#006BFF"/>
          <path d="M12 6v6l4 2" stroke="white" strokeWidth="2" strokeLinecap="round"/>
        </svg>
      );
    case "zoom":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <rect width="24" height="24" rx="4" fill="#2D8CFF"/>
          <rect x="4" y="8" width="10" height="8" rx="1" fill="white"/>
          <path d="M14 10l5-2v8l-5-2v-4z" fill="white"/>
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
    key: "calendly",
    name: "Calendly",
    icon: "📅",
    description: "Sync your booking calendar",
    oauth: true,
    section: "scheduling",
  },
  {
    key: "zoom",
    name: "Zoom",
    icon: "📹",
    description: "Create video meetings automatically",
    oauth: true,
    section: "scheduling",
  },
  {
    key: "google",
    name: "Google Meet",
    icon: "🎥",
    description: "Create Meet links via Calendar API",
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

  // Bot config toggles
  const [autoReply, setAutoReply] = useState(true);
  const [leadScoring, setLeadScoring] = useState(true);
  const [autoQualify, setAutoQualify] = useState(true);
  const [afterHoursMode, setAfterHoursMode] = useState(false);
  const [humanTakeoverAlerts, setHumanTakeoverAlerts] = useState(true);

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
      setAutoReply(config.clone_active ?? true);
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

  const handleSavePersonality = async () => {
    try {
      await updateConfig.mutateAsync({
        clone_name: botName,
        clone_tone: tone,
        clone_vocabulary: vocabulary,
      });
      toast({
        title: "Settings saved",
        description: "Your bot personality has been updated.",
      });
      // Invalidate onboarding to refresh status and redirect to home
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      navigate("/");
    } catch (error) {
      toast({
        title: "Error saving settings",
        description: error instanceof Error ? error.message : "Failed to save settings",
        variant: "destructive",
      });
    }
  };

  const handleToggleBotConfig = async (key: string, value: boolean) => {
    switch (key) {
      case "autoReply":
        setAutoReply(value);
        break;
      case "leadScoring":
        setLeadScoring(value);
        break;
      case "autoQualify":
        setAutoQualify(value);
        break;
      case "afterHoursMode":
        setAfterHoursMode(value);
        break;
      case "humanTakeoverAlerts":
        setHumanTakeoverAlerts(value);
        break;
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
            <TabsTrigger value="bot" className="rounded-lg data-[state=active]:bg-card text-xs sm:text-sm">
              <Bot className="w-4 h-4 mr-1 sm:mr-2" />
              Config
            </TabsTrigger>
            <TabsTrigger value="products" className="rounded-lg data-[state=active]:bg-card text-xs sm:text-sm">
              <Package className="w-4 h-4 mr-1 sm:mr-2" />
              <span className="hidden sm:inline">Products</span>
              <span className="sm:hidden">Prod</span>
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
          <div className="metric-card space-y-6">
            <div className="space-y-2">
              <Label htmlFor="botName">Bot Name</Label>
              <Input
                id="botName"
                value={botName}
                onChange={(e) => setBotName(e.target.value)}
                className="bg-secondary border-0"
                placeholder="Enter bot name..."
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="tone">Communication Tone</Label>
              <Select value={tone} onValueChange={setTone}>
                <SelectTrigger className="bg-secondary border-0">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="friendly">Friendly & Warm</SelectItem>
                  <SelectItem value="professional">Professional</SelectItem>
                  <SelectItem value="casual">Casual & Fun</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="vocabulary">Custom Vocabulary & Rules</Label>
              <Textarea
                id="vocabulary"
                value={vocabulary}
                onChange={(e) => setVocabulary(e.target.value)}
                className="bg-secondary border-0 min-h-[120px]"
                placeholder="Add custom instructions for your bot..."
              />
            </div>

            <div className="pt-4 border-t border-border/50">
              <div className="flex items-center justify-between mb-4">
                <Label>Preview Bot Response</Label>
                <Button variant="outline" size="sm" onClick={generatePreview}>
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Generate Preview
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
            className="bg-gradient-to-r from-primary to-accent hover:opacity-90 transition-opacity"
            onClick={handleSavePersonality}
            disabled={updateConfig.isPending}
          >
            {updateConfig.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Save className="w-4 h-4 mr-2" />
            )}
            Save Changes
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
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">💬</span>
                  <div>
                    <h3 className="font-semibold text-lg">Social & Messaging</h3>
                    <p className="text-sm text-muted-foreground">Connect your communication channels</p>
                  </div>
                </div>
                <div className="metric-card space-y-1 p-2">
                  {connectionConfigs.filter(c => c.section === "messaging").map((conn) => {
                    const status = connectionsData?.[conn.key as keyof typeof connectionsData];
                    const isConnected = status?.connected || false;
                    const isEditing = editingConnection === conn.key;

                    return (
                      <div key={conn.key}>
                        <div className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors">
                          <div className="flex items-center gap-3">
                            <PlatformLogo platform={conn.key} size={24} />
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
                          <div className="mx-3 mb-3 p-3 rounded-lg bg-muted/30 space-y-3">
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
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">💰</span>
                  <div>
                    <h3 className="font-semibold text-lg">Payments</h3>
                    <p className="text-sm text-muted-foreground">Track and manage payments</p>
                  </div>
                </div>
                <div className="metric-card space-y-1 p-2">
                  {/* OAuth payments (Stripe, PayPal) */}
                  {connectionConfigs.filter(c => c.section === "payments").map((conn) => {
                    const status = connectionsData?.[conn.key as keyof typeof connectionsData];
                    const isConnected = status?.connected || false;

                    return (
                      <div
                        key={conn.key}
                        className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors"
                      >
                        <div className="flex items-center gap-3">
                          <PlatformLogo platform={conn.key} size={24} />
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

                  {/* Separator */}
                  <div className="border-t border-border/50 my-2 mx-3" />

                  {/* Manual payment methods */}
                  {/* Bizum */}
                  <div>
                    <div className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className="w-6 h-6 rounded bg-orange-500 flex items-center justify-center text-white text-xs font-bold">B</div>
                        <div>
                          <p className="font-medium">Bizum</p>
                          <p className="text-sm text-muted-foreground">
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
                      <div className="mx-3 mb-3 p-3 rounded-lg bg-muted/30 flex gap-2">
                        <Input placeholder="Phone" value={otherPaymentMethods.bizum.phone} onChange={(e) => setOtherPaymentMethods(p => ({ ...p, bizum: { ...p.bizum, phone: e.target.value } }))} />
                        <Input placeholder="Name" value={otherPaymentMethods.bizum.holder_name} onChange={(e) => setOtherPaymentMethods(p => ({ ...p, bizum: { ...p.bizum, holder_name: e.target.value } }))} />
                        <Button onClick={() => handleSavePaymentMethods(true)}>Save</Button>
                      </div>
                    )}
                  </div>

                  {/* Bank Transfer */}
                  <div>
                    <div className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className="w-6 h-6 rounded bg-blue-600 flex items-center justify-center text-white text-sm">🏦</div>
                        <div>
                          <p className="font-medium">Bank Transfer</p>
                          <p className="text-sm text-muted-foreground">
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
                      <div className="mx-3 mb-3 p-3 rounded-lg bg-muted/30 flex gap-2">
                        <Input placeholder="IBAN" value={otherPaymentMethods.bank_transfer.iban} onChange={(e) => setOtherPaymentMethods(p => ({ ...p, bank_transfer: { ...p.bank_transfer, iban: e.target.value } }))} className="flex-1" />
                        <Input placeholder="Holder" value={otherPaymentMethods.bank_transfer.holder_name} onChange={(e) => setOtherPaymentMethods(p => ({ ...p, bank_transfer: { ...p.bank_transfer, holder_name: e.target.value } }))} className="w-32" />
                        <Button onClick={() => handleSavePaymentMethods(true)}>Save</Button>
                      </div>
                    )}
                  </div>

                  {/* Revolut */}
                  <div>
                    <div className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className="w-6 h-6 rounded bg-black flex items-center justify-center text-white text-xs font-bold">R</div>
                        <div>
                          <p className="font-medium">Revolut / Wise</p>
                          <p className="text-sm text-muted-foreground">
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
                      <div className="mx-3 mb-3 p-3 rounded-lg bg-muted/30 flex gap-2">
                        <Input placeholder="@username or link" value={otherPaymentMethods.revolut.link} onChange={(e) => setOtherPaymentMethods(p => ({ ...p, revolut: { ...p.revolut, link: e.target.value } }))} className="flex-1" />
                        <Button onClick={() => handleSavePaymentMethods(true)}>Save</Button>
                      </div>
                    )}
                  </div>

                  {/* Other */}
                  <div>
                    <div className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className="w-6 h-6 rounded bg-gray-500 flex items-center justify-center text-white text-sm">📝</div>
                        <div>
                          <p className="font-medium">Other</p>
                          <p className="text-sm text-muted-foreground truncate max-w-[200px]">
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
                      <div className="mx-3 mb-3 p-3 rounded-lg bg-muted/30 space-y-2">
                        <Textarea placeholder="Custom payment instructions..." value={otherPaymentMethods.other.instructions} onChange={(e) => setOtherPaymentMethods(p => ({ ...p, other: { ...p.other, instructions: e.target.value } }))} className="min-h-[80px]" />
                        <Button onClick={() => handleSavePaymentMethods(true)}>Save</Button>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Scheduling Section */}
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">📅</span>
                  <div>
                    <h3 className="font-semibold text-lg">Scheduling</h3>
                    <p className="text-sm text-muted-foreground">Calendar and video call integrations</p>
                  </div>
                </div>
                <div className="metric-card space-y-1 p-2">
                  {connectionConfigs.filter(c => c.section === "scheduling").map((conn) => {
                    const status = connectionsData?.[conn.key as keyof typeof connectionsData];
                    const isConnected = status?.connected || false;

                    return (
                      <div
                        key={conn.key}
                        className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors"
                      >
                        <div className="flex items-center gap-3">
                          <PlatformLogo platform={conn.key} size={24} />
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

        {/* Bot Config Tab */}
        <TabsContent value="bot" className="space-y-6 animate-fade-in">
          <div className="metric-card space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">Auto-Reply</p>
                <p className="text-sm text-muted-foreground">Automatically respond to new messages</p>
              </div>
              <Switch
                checked={autoReply}
                onCheckedChange={(v) => handleToggleBotConfig("autoReply", v)}
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">Lead Scoring</p>
                <p className="text-sm text-muted-foreground">Automatically score leads based on engagement</p>
              </div>
              <Switch
                checked={leadScoring}
                onCheckedChange={(v) => handleToggleBotConfig("leadScoring", v)}
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">Auto-Qualify</p>
                <p className="text-sm text-muted-foreground">Move high-intent leads to Hot automatically</p>
              </div>
              <Switch
                checked={autoQualify}
                onCheckedChange={(v) => handleToggleBotConfig("autoQualify", v)}
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">After-Hours Mode</p>
                <p className="text-sm text-muted-foreground">Send different responses outside business hours</p>
              </div>
              <Switch
                checked={afterHoursMode}
                onCheckedChange={(v) => handleToggleBotConfig("afterHoursMode", v)}
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">Human Takeover Alerts</p>
                <p className="text-sm text-muted-foreground">Get notified when bot can't handle a query</p>
              </div>
              <Switch
                checked={humanTakeoverAlerts}
                onCheckedChange={(v) => handleToggleBotConfig("humanTakeoverAlerts", v)}
              />
            </div>
          </div>
        </TabsContent>

        {/* Products Tab */}
        <TabsContent value="products" className="animate-fade-in">
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
              <h3 className="font-semibold">Your Products</h3>
              <Button onClick={openAddProduct} className="w-full sm:w-auto">
                <Plus className="w-4 h-4 mr-2" />
                Add Product
              </Button>
            </div>

            {productsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
              </div>
            ) : products.length === 0 ? (
              <div className="metric-card text-center py-8 text-muted-foreground">
                <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>No products configured</p>
                <p className="text-sm mt-2">Add your first product to get started</p>
              </div>
            ) : (
              products.map((product) => (
                <div
                  key={product.id}
                  className="metric-card flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="flex items-center gap-4">
                    <div className={cn(
                      "w-12 h-12 rounded-xl flex items-center justify-center text-xl font-bold shrink-0",
                      (product.is_active ?? product.active)
                        ? "bg-gradient-to-br from-primary/20 to-accent/20 text-primary"
                        : "bg-secondary text-muted-foreground"
                    )}>
                      {product.currency === "EUR" ? "€" : "$"}
                    </div>
                    <div className="min-w-0">
                      <p className="font-semibold truncate">{product.name}</p>
                      <p className="text-sm text-muted-foreground truncate">
                        {product.currency === "EUR" ? "€" : "$"}{product.price}
                        {product.description && ` - ${product.description.slice(0, 30)}...`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 ml-16 sm:ml-0">
                    <span className={cn(
                      "text-xs px-2 py-1 rounded-full",
                      (product.is_active ?? product.active) ? "bg-success/10 text-success" : "bg-yellow-500/10 text-yellow-600"
                    )}>
                      {(product.is_active ?? product.active) ? "Active" : "Draft"}
                    </span>
                    <Button variant="ghost" size="icon" onClick={() => openEditProduct(product)}>
                      <Pencil className="w-4 h-4" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => confirmDelete(product)}>
                      <Trash2 className="w-4 h-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>
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
