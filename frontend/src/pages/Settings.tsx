import { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Bot, Link2, Package, User, Save, RefreshCw, Loader2, AlertCircle, Plus, Pencil, Trash2, BookOpen } from "lucide-react";
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
  fields?: Array<{
    name: string;
    label: string;
    placeholder: string;
    type: "token" | "page_id" | "phone_id";
  }>;
}

const connectionConfigs: ConnectionConfig[] = [
  {
    key: "instagram",
    name: "Instagram",
    icon: "📸",
    description: "Automate your Instagram DMs",
    oauth: true,
  },
  {
    key: "telegram",
    name: "Telegram",
    icon: "✈️",
    description: "Create bot in 1 min via @BotFather",
    oauth: false,
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
  },
  {
    key: "stripe",
    name: "Stripe",
    icon: "💳",
    description: "Track payments automatically",
    oauth: true,
  },
  {
    key: "paypal",
    name: "PayPal",
    icon: "🅿️",
    description: "Track PayPal payments",
    oauth: true,
  },
  {
    key: "calendly",
    name: "Calendly",
    icon: "📅",
    description: "Sync your booking calendar",
    oauth: true,
  },
];

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
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">Configure your bot personality and integrations</p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="bg-secondary p-1 rounded-xl">
          <TabsTrigger value="personality" className="rounded-lg data-[state=active]:bg-card">
            <User className="w-4 h-4 mr-2" />
            Personality
          </TabsTrigger>
          <TabsTrigger value="connections" className="rounded-lg data-[state=active]:bg-card">
            <Link2 className="w-4 h-4 mr-2" />
            Connections
          </TabsTrigger>
          <TabsTrigger value="bot" className="rounded-lg data-[state=active]:bg-card">
            <Bot className="w-4 h-4 mr-2" />
            Bot Config
          </TabsTrigger>
          <TabsTrigger value="products" className="rounded-lg data-[state=active]:bg-card">
            <Package className="w-4 h-4 mr-2" />
            Products
          </TabsTrigger>
          <TabsTrigger value="knowledge" className="rounded-lg data-[state=active]:bg-card">
            <BookOpen className="w-4 h-4 mr-2" />
            Knowledge
          </TabsTrigger>
        </TabsList>

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
          <div className="space-y-4">
            {connectionsLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
              </div>
            ) : (
              connectionConfigs.map((conn) => {
                const status = connectionsData?.[conn.key as keyof typeof connectionsData];
                const isConnected = status?.connected || false;
                const isEditing = editingConnection === conn.key;

                const handleOAuthConnect = async () => {
                  try {
                    const response = await startOAuth(conn.key);
                    // Redirect to OAuth provider
                    window.location.href = response.auth_url;
                  } catch (error) {
                    toast({
                      title: "Connection failed",
                      description: error instanceof Error ? error.message : "OAuth not configured",
                      variant: "destructive",
                    });
                  }
                };

                return (
                  <div key={conn.key} className="metric-card">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <span className="text-2xl">{conn.icon}</span>
                        <div>
                          <p className="font-semibold">{conn.name}</p>
                          <p className="text-sm text-muted-foreground">
                            {isConnected
                              ? status?.username || `Connected ${status?.masked_token ? `(${status.masked_token})` : "✓"}`
                              : conn.description}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {isConnected && (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                disconnectMutation.mutate(conn.key, {
                                  onSuccess: () => {
                                    toast({ title: `${conn.name} disconnected` });
                                  },
                                });
                              }}
                              disabled={disconnectMutation.isPending}
                              className="text-destructive hover:bg-destructive/10"
                            >
                              Disconnect
                            </Button>
                            <span className="text-sm text-success font-medium">Connected ✓</span>
                          </>
                        )}
                        {!isConnected && conn.comingSoon && (
                          <span className="text-xs bg-muted text-muted-foreground px-3 py-1.5 rounded-full">
                            Coming Soon
                          </span>
                        )}
                        {!isConnected && !conn.comingSoon && conn.oauth && (
                          <Button
                            size="sm"
                            onClick={handleOAuthConnect}
                          >
                            Connect
                          </Button>
                        )}
                        {!isConnected && !conn.oauth && (
                          <Button
                            variant={isEditing ? "outline" : "default"}
                            size="sm"
                            onClick={() => {
                              if (isEditing) {
                                setEditingConnection(null);
                                setConnectionForm({});
                              } else {
                                setEditingConnection(conn.key);
                                setConnectionForm({});
                              }
                            }}
                          >
                            {isEditing ? "Cancel" : "Connect"}
                          </Button>
                        )}
                      </div>
                    </div>

                    {/* Manual Connection Form (for non-OAuth platforms like Telegram) */}
                    {isEditing && !conn.oauth && conn.fields && (
                      <div className="mt-4 pt-4 border-t border-border space-y-4">
                        {conn.oauthHelp && (
                          <div className="text-sm text-muted-foreground bg-muted/50 p-3 rounded-lg whitespace-pre-line">
                            {conn.oauthHelp}
                          </div>
                        )}
                        {conn.fields.map((field) => (
                          <div key={field.name} className="space-y-2">
                            <Label htmlFor={`${conn.key}-${field.name}`}>{field.label}</Label>
                            <Input
                              id={`${conn.key}-${field.name}`}
                              type="password"
                              placeholder={field.placeholder}
                              value={connectionForm[field.type] || ""}
                              onChange={(e) =>
                                setConnectionForm((prev) => ({
                                  ...prev,
                                  [field.type]: e.target.value,
                                }))
                              }
                            />
                          </div>
                        ))}
                        <Button
                          className="w-full"
                          onClick={async () => {
                            try {
                              await updateConnectionMutation.mutateAsync({
                                platform: conn.key,
                                data: connectionForm,
                              });
                              toast({
                                title: `${conn.name} connected`,
                                description: "Connection saved successfully.",
                              });
                              setEditingConnection(null);
                              setConnectionForm({});
                              await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
                              navigate("/");
                            } catch (error) {
                              toast({
                                title: "Connection failed",
                                description: error instanceof Error ? error.message : "Failed to connect",
                                variant: "destructive",
                              });
                            }
                          }}
                          disabled={
                            updateConnectionMutation.isPending ||
                            !conn.fields?.some((f) => connectionForm[f.type])
                          }
                        >
                          {updateConnectionMutation.isPending ? (
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                          ) : (
                            <Save className="w-4 h-4 mr-2" />
                          )}
                          Save Connection
                        </Button>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
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
            <div className="flex justify-between items-center">
              <h3 className="font-semibold">Your Products</h3>
              <Button onClick={openAddProduct}>
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
                  className="metric-card flex items-center justify-between"
                >
                  <div className="flex items-center gap-4">
                    <div className={cn(
                      "w-12 h-12 rounded-xl flex items-center justify-center text-xl font-bold",
                      (product.is_active ?? product.active)
                        ? "bg-gradient-to-br from-primary/20 to-accent/20 text-primary"
                        : "bg-secondary text-muted-foreground"
                    )}>
                      {product.currency === "EUR" ? "€" : "$"}
                    </div>
                    <div>
                      <p className="font-semibold">{product.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {product.currency === "EUR" ? "€" : "$"}{product.price}
                        {product.description && ` - ${product.description.slice(0, 30)}...`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
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
