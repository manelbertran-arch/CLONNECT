import { useState, useEffect } from "react";
import { Loader2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { startOAuth, exchangeWhatsAppEmbeddedSignup, getWhatsAppConfig } from "@/services/api";
import PlatformLogo from "./PlatformLogo";

type ToastFn = (opts: {
  title?: string;
  description?: string;
  variant?: "default" | "destructive";
}) => void;

interface ConnectionStatus {
  connected?: boolean;
  username?: string;
  masked_token?: string;
  days_remaining?: number;
}

interface ConnectionsTabProps {
  config: Record<string, any> | undefined;
  connectionsData: Record<string, ConnectionStatus> | undefined;
  connectionsLoading: boolean;
  updateConnectionMutation: {
    mutateAsync: (args: { platform: string; data: Record<string, string> }) => Promise<any>;
  };
  disconnectMutation: {
    mutate: (platform: string, options?: { onSettled?: () => void }) => void;
    isPending: boolean;
  };
  toast: ToastFn;
  queryClient: {
    invalidateQueries: (options: { queryKey: string[] }) => Promise<void>;
  };
  updateConfig: {
    mutateAsync: (data: Record<string, any>) => Promise<any>;
  };
}

interface ConnectionConfig {
  key: string;
  name: string;
  icon: string;
  description: string;
  oauth: boolean;
  comingSoon?: boolean;
  oauthHelp?: string;
  section: "messaging" | "payments" | "scheduling";
  fields?: Array<{
    name: string;
    label: string;
    placeholder: string;
    type: "token" | "page_id" | "phone_id" | "link" | "meeting_id";
  }>;
}

const connectionConfigs: ConnectionConfig[] = [
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
  {
    key: "google",
    name: "Google Calendar + Meet",
    icon: "🎥",
    description: "Auto-create Google Meet links for bookings",
    oauth: true,
    section: "scheduling",
  },
];

export default function ConnectionsTab({
  config,
  connectionsData,
  connectionsLoading,
  updateConnectionMutation,
  disconnectMutation,
  toast,
  queryClient,
  updateConfig,
}: ConnectionsTabProps) {
  const [editingConnection, setEditingConnection] = useState<string | null>(null);
  const [connectionForm, setConnectionForm] = useState<Record<string, string>>({});
  const [disconnectConfirm, setDisconnectConfirm] = useState<string | null>(null);
  const [waConnecting, setWaConnecting] = useState(false);

  const [otherPaymentMethods, setOtherPaymentMethods] = useState({
    bizum: { enabled: false, phone: "", holder_name: "" },
    bank_transfer: { enabled: false, iban: "", holder_name: "" },
    revolut: { enabled: false, link: "" },
    other: { enabled: false, instructions: "" },
  });
  const [editingPaymentMethod, setEditingPaymentMethod] = useState<string | null>(null);

  const maskIban = (iban: string) => {
    if (!iban || iban.length < 10) return iban;
    return `${iban.slice(0, 4)}****${iban.slice(-4)}`;
  };

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
    try {
      await updateConfig.mutateAsync({
        other_payment_methods: updatedMethods,
      });
    } catch {
      setOtherPaymentMethods(otherPaymentMethods);
    }
  };

  const connectWhatsAppEmbedded = async () => {
    setWaConnecting(true);
    try {
      const waConfig = await getWhatsAppConfig();
      if (!waConfig.app_id || !waConfig.config_id) {
        toast({
          title: "WhatsApp not configured",
          description: "Missing META_APP_ID or WHATSAPP_CONFIG_ID on server.",
          variant: "destructive",
        });
        setWaConnecting(false);
        return;
      }

      const FB = (window as any).FB;
      if (!FB) {
        console.warn("FB SDK not loaded, falling back to OAuth redirect");
        const r = await startOAuth("whatsapp");
        window.location.href = r.auth_url;
        return;
      }

      FB.init({
        appId: waConfig.app_id,
        cookie: true,
        xfbml: false,
        version: "v21.0",
      });

      FB.login(
        (response: any) => {
          if (response.authResponse) {
            const code = response.authResponse.code;

            if (response.authResponse.declinedPermissions) {
              console.warn("Some permissions declined:", response.authResponse.declinedPermissions);
            }

            exchangeWhatsAppEmbeddedSignup(code, "", "")
              .then(() => {
                toast({
                  title: "WhatsApp conectado",
                  description: "Tu cuenta de WhatsApp Business se ha conectado correctamente.",
                });
                queryClient.invalidateQueries({ queryKey: ["connections"] });
              })
              .catch((err: any) => {
                console.error("WhatsApp exchange error:", err);
                toast({
                  title: "Error al conectar WhatsApp",
                  description: err.message || "No se pudo completar la conexion.",
                  variant: "destructive",
                });
              })
              .finally(() => setWaConnecting(false));
            return;
          } else {
            console.log("WhatsApp Embedded Signup cancelled or failed:", response);
            toast({
              title: "Conexion cancelada",
              description: "No se completo el proceso de WhatsApp.",
              variant: "destructive",
            });
          }
          setWaConnecting(false);
        },
        {
          config_id: waConfig.config_id,
          response_type: "code",
          override_default_response_type: true,
          extras: {
            feature: "whatsapp_embedded_signup",
            featureType: "whatsapp_business_app_onboarding",
            sessionInfoVersion: 3,
          },
        }
      );

      const sessionInfoListener = (event: MessageEvent) => {
        if (event.origin !== "https://www.facebook.com" && event.origin !== "https://web.facebook.com") return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === "WA_EMBEDDED_SIGNUP") {
            console.log("WA Embedded Signup session info:", data);
          }
        } catch {
          // Not JSON, ignore
        }
      };
      window.addEventListener("message", sessionInfoListener);
      setTimeout(() => window.removeEventListener("message", sessionInfoListener), 300000);

    } catch (err) {
      console.error("WhatsApp Embedded Signup error:", err);
      try {
        const r = await startOAuth("whatsapp");
        window.location.href = r.auth_url;
      } catch (e) {
        console.error("OAuth fallback also failed:", e);
        toast({
          title: "Error",
          description: "No se pudo iniciar la conexion de WhatsApp.",
          variant: "destructive",
        });
      }
      setWaConnecting(false);
    }
  };

  if (connectionsLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="p-5 rounded-2xl bg-muted/15 border border-border/20">
          <div className="h-5 w-40 bg-muted/30 rounded mb-4" />
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-muted/20">
                <div className="w-10 h-10 rounded-lg bg-muted/30" />
                <div className="flex-1">
                  <div className="h-4 w-28 bg-muted/40 rounded mb-1" />
                  <div className="h-3 w-20 bg-muted/30 rounded" />
                </div>
                <div className="h-8 w-20 bg-muted/20 rounded" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Social & Messaging Section */}
      <div className="metric-card">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
            <span className="text-xl">💬</span>
          </div>
          <div>
            <h3 className="font-semibold">Redes y Mensajería</h3>
            <p className="text-sm text-muted-foreground">Conecta tus canales de comunicación</p>
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
                      {isConnected && status?.days_remaining != null && (
                        <span className={`text-xs font-medium mt-0.5 inline-block px-2 py-0.5 rounded-full ${
                          status.days_remaining < 5
                            ? "bg-destructive/10 text-destructive"
                            : status.days_remaining < 15
                            ? "bg-destructive/10 text-orange-600 dark:text-orange-400"
                            : status.days_remaining < 30
                            ? "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400"
                            : "bg-success/10 text-success"
                        }`}>
                          Token expira en {status.days_remaining} días
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {isConnected ? (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setDisconnectConfirm(conn.key)}
                          disabled={disconnectMutation.isPending}
                          className="text-destructive hover:bg-destructive/10"
                        >
                          Disconnect
                        </Button>
                        <span className="text-sm text-success font-medium flex items-center gap-1">
                          <Check className="w-4 h-4" /> Connected
                        </span>
                      </>
                    ) : conn.key === "whatsapp" ? (
                      <Button
                        size="sm"
                        disabled={waConnecting}
                        onClick={connectWhatsAppEmbedded}
                      >
                        {waConnecting ? (
                          <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Connecting...</>
                        ) : (
                          "Connect"
                        )}
                      </Button>
                    ) : conn.oauth ? (
                      <Button
                        size="sm"
                        onClick={() => startOAuth(conn.key).then(r => window.location.href = r.auth_url).catch((err) => { console.error('OAuth error:', err); })}
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
            <h3 className="font-semibold">Pagos</h3>
            <p className="text-sm text-muted-foreground">Gestiona y rastrea pagos</p>
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
                        onClick={() => setDisconnectConfirm(conn.key)}
                        disabled={disconnectMutation.isPending}
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
                      onClick={() => startOAuth(conn.key).then(r => window.location.href = r.auth_url).catch((err) => { console.error('OAuth error:', err); })}
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
          <p className="text-sm font-medium mb-1">Métodos de pago alternativos</p>
          <p className="text-xs text-muted-foreground mb-4">El bot los mencionará cuando los clientes pregunten por formas de pago</p>

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
            <h3 className="font-semibold">Calendario</h3>
            <p className="text-sm text-muted-foreground">Integración con calendario y videollamadas</p>
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
                        onClick={() => setDisconnectConfirm(conn.key)}
                        disabled={disconnectMutation.isPending}
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
                      onClick={() => startOAuth(conn.key).then(r => window.location.href = r.auth_url).catch((err) => { console.error('OAuth error:', err); })}
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

      {/* Disconnect confirmation dialog */}
      <Dialog open={!!disconnectConfirm} onOpenChange={(open) => { if (!open) setDisconnectConfirm(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Desconectar {disconnectConfirm ? disconnectConfirm.charAt(0).toUpperCase() + disconnectConfirm.slice(1) : ""}?</DialogTitle>
            <DialogDescription>
              Se eliminara el token y la conexion. Puedes volver a conectar en cualquier momento.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisconnectConfirm(null)}>Cancelar</Button>
            <Button
              variant="destructive"
              disabled={disconnectMutation.isPending}
              onClick={() => {
                if (disconnectConfirm) {
                  disconnectMutation.mutate(disconnectConfirm, { onSettled: () => setDisconnectConfirm(null) });
                }
              }}
            >
              {disconnectMutation.isPending ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Desconectando...</> : "Desconectar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
