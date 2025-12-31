import { useState } from "react";
import { Calendar as CalendarIcon, Clock, Video, Users, CheckCircle2, XCircle, Loader2, AlertCircle, Plus, X, Trash2, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCalendarStats, useBookings, useBookingLinks, useCreateBookingLink, useDeleteBookingLink, useCancelBooking, useConnections } from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { useNavigate } from "react-router-dom";

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString("es-ES", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

function formatTime(dateString: string): string {
  return new Date(dateString).toLocaleTimeString("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

const statusColors: Record<string, string> = {
  scheduled: "bg-primary/10 text-primary",
  completed: "bg-success/10 text-success",
  cancelled: "bg-destructive/10 text-destructive",
  no_show: "bg-yellow-500/10 text-yellow-600",
};

const statusIcons: Record<string, React.ReactNode> = {
  scheduled: <Clock className="w-4 h-4" />,
  completed: <CheckCircle2 className="w-4 h-4" />,
  cancelled: <XCircle className="w-4 h-4" />,
  no_show: <AlertCircle className="w-4 h-4" />,
};

// Service type options
const SERVICE_TYPES = [
  { value: "discovery", label: "Discovery Call", slug: "discovery" },
  { value: "coaching", label: "Coaching Session", slug: "coaching" },
  { value: "sales", label: "Sales Call", slug: "sales" },
  { value: "consultation", label: "Consultation", slug: "consultation" },
  { value: "demo", label: "Demo", slug: "demo" },
  { value: "followup", label: "Follow-up", slug: "followup" },
  { value: "qa", label: "Q&A Session", slug: "qa-session" },
  { value: "strategy", label: "Strategy Call", slug: "strategy" },
  { value: "onboarding", label: "Onboarding", slug: "onboarding" },
  { value: "other", label: "Other (custom)", slug: "" },
];

// Duration options
const DURATIONS = [
  { value: 15, label: "15 min" },
  { value: 30, label: "30 min" },
  { value: 45, label: "45 min" },
  { value: 60, label: "60 min" },
  { value: 90, label: "90 min" },
  { value: -1, label: "Custom" },
];

// Price options
const PRICES = [
  { value: 0, label: "Free" },
  { value: 10, label: "10€" },
  { value: 25, label: "25€" },
  { value: 50, label: "50€" },
  { value: 75, label: "75€" },
  { value: 100, label: "100€" },
  { value: 150, label: "150€" },
  { value: 200, label: "200€" },
  { value: -1, label: "Custom" },
];

// Platform logos - official brand colors and SVG paths
const PlatformLogo = ({ platform, size = 24 }: { platform: string; size?: number }) => {
  switch (platform) {
    case "google-meet":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <path d="M12 4L4 8v8l8 4 8-4V8l-8-4z" fill="#00897B"/>
          <path d="M12 4l8 4v8" fill="#00AC47"/>
          <path d="M12 4L4 8v8" fill="#4285F4"/>
          <path d="M12 20l8-4" fill="#FFBA00"/>
          <path d="M12 20L4 16" fill="#EA4335"/>
          <circle cx="12" cy="12" r="3" fill="white"/>
        </svg>
      );
    case "clonnect":
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <rect width="24" height="24" rx="4" fill="#6366F1"/>
          <circle cx="12" cy="12" r="4" stroke="white" strokeWidth="2"/>
        </svg>
      );
    default:
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <rect width="24" height="24" rx="4" fill="#6366F1"/>
          <path d="M10 8l4 4-4 4" stroke="white" strokeWidth="2" strokeLinecap="round"/>
        </svg>
      );
  }
};

export default function Bookings() {
  const navigate = useNavigate();
  const { data: statsData, isLoading: statsLoading, error: statsError } = useCalendarStats();
  const { data: bookingsData, isLoading: bookingsLoading } = useBookings(undefined, true);
  const { data: linksData, isLoading: linksLoading, refetch: refetchLinks } = useBookingLinks();
  const { data: connectionsData } = useConnections();
  const createBookingLink = useCreateBookingLink();
  const deleteBookingLinkMutation = useDeleteBookingLink();
  const cancelBookingMutation = useCancelBooking();
  const { toast } = useToast();

  // Check connected platforms - only Google Meet is supported
  const googleConnected = connectionsData?.google?.connected ?? false;

  // Build available platforms based on connections
  // Always include Clonnect (internal), optionally Google Meet
  const connectedPlatforms = [
    { value: "clonnect", label: "Clonnect" },
    ...(googleConnected ? [{ value: "google-meet", label: "Google Meet" }] : []),
  ];

  // Always have at least Clonnect platform available
  const hasConnectedPlatforms = true;

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedServiceType, setSelectedServiceType] = useState("discovery");
  const [customServiceType, setCustomServiceType] = useState("");
  const [selectedDuration, setSelectedDuration] = useState(30);
  const [customDuration, setCustomDuration] = useState(30);
  const [selectedPrice, setSelectedPrice] = useState(0);
  const [customPrice, setCustomPrice] = useState(0);
  const [newLink, setNewLink] = useState({
    meeting_type: "discovery",
    title: "Discovery Call",
    url: "",
    platform: "clonnect",
    duration_minutes: 30,
    description: "",
    price: 0,
  });

  // Handle service type change
  const handleServiceTypeChange = (value: string) => {
    setSelectedServiceType(value);
    const serviceType = SERVICE_TYPES.find(m => m.value === value);
    if (serviceType && value !== "other") {
      setNewLink(prev => ({
        ...prev,
        meeting_type: serviceType.slug,
        title: serviceType.label
      }));
    }
  };

  // Handle custom service type
  const handleCustomServiceType = (value: string) => {
    setCustomServiceType(value);
    const slug = value.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
    setNewLink(prev => ({
      ...prev,
      meeting_type: slug,
      title: value
    }));
  };

  // Handle duration change
  const handleDurationChange = (value: number) => {
    setSelectedDuration(value);
    if (value !== -1) {
      setNewLink(prev => ({ ...prev, duration_minutes: value }));
    }
  };

  // Handle custom duration
  const handleCustomDuration = (value: number) => {
    setCustomDuration(value);
    setNewLink(prev => ({ ...prev, duration_minutes: value }));
  };

  // Handle price change
  const handlePriceChange = (value: number) => {
    setSelectedPrice(value);
    if (value !== -1) {
      setNewLink(prev => ({ ...prev, price: value }));
    }
  };

  // Handle custom price
  const handleCustomPrice = (value: number) => {
    setCustomPrice(value);
    setNewLink(prev => ({ ...prev, price: value }));
  };

  const today = new Date();
  const formattedDate = today.toLocaleDateString("es-ES", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const handleCreateLink = async () => {
    // Clonnect and google-meet don't require URLs (auto-created on booking)
    const isAutoCreate = newLink.platform === "clonnect" || (newLink.platform === "google-meet" && googleConnected);

    if (!newLink.url && !isAutoCreate) {
      toast({ title: "Error", description: "Booking URL is required", variant: "destructive" });
      return;
    }

    // Validate service type for custom
    if (selectedServiceType === "other" && !customServiceType.trim()) {
      toast({ title: "Error", description: "Please enter a custom service name", variant: "destructive" });
      return;
    }

    // Check limit of 5 services
    if (links.length >= 5) {
      toast({ title: "Error", description: "Maximum 5 services allowed. Delete one first.", variant: "destructive" });
      return;
    }

    try {
      await createBookingLink.mutateAsync(newLink);
      const platformName = newLink.platform === "google-meet" ? "Google Meet" : "Clonnect";
      toast({ title: "Success", description: `Service created (${platformName})` });
      setShowCreateForm(false);
      // Reset form
      setSelectedServiceType("discovery");
      setCustomServiceType("");
      setSelectedDuration(30);
      setCustomDuration(30);
      setSelectedPrice(0);
      setCustomPrice(0);
      setNewLink({
        meeting_type: "discovery",
        title: "Discovery Call",
        url: "",
        platform: "clonnect",
        duration_minutes: 30,
        description: "",
        price: 0,
      });
      refetchLinks();
    } catch (error: any) {
      toast({ title: "Error", description: error.message || "Failed to create service", variant: "destructive" });
    }
  };

  const handleDeleteLink = async (linkId: string, title: string) => {
    if (!confirm(`Delete "${title}"?`)) return;
    try {
      await deleteBookingLinkMutation.mutateAsync(linkId);
      toast({ title: "Deleted", description: `"${title}" removed` });
      refetchLinks();
    } catch (error: any) {
      toast({ title: "Error", description: error.message || "Failed to delete", variant: "destructive" });
    }
  };

  const handleCancelBooking = async (bookingId: string, title: string) => {
    if (!confirm(`Cancel "${title}"? This cannot be undone.`)) return;
    try {
      await cancelBookingMutation.mutateAsync(bookingId);
      toast({ title: "Cancelled", description: `"${title}" has been cancelled` });
    } catch (error: any) {
      toast({ title: "Error", description: error.message || "Failed to cancel booking", variant: "destructive" });
    }
  };

  // Loading state
  if (statsLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  // Error state
  if (statsError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <AlertCircle className="w-12 h-12 text-destructive" />
        <p className="text-muted-foreground">Failed to load calendar data</p>
        <p className="text-sm text-destructive">{statsError.message}</p>
      </div>
    );
  }

  const stats = statsData || {
    total_bookings: 0,
    completed: 0,
    cancelled: 0,
    no_show: 0,
    show_rate: 0,
    upcoming: 0,
  };
  const bookings = bookingsData?.bookings || [];
  const links = linksData?.links || [];

  const formatPrice = (price: number) => {
    if (price === 0) return "FREE";
    return `${price}€`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Bookings</h1>
          <p className="text-muted-foreground text-sm sm:text-base">{formattedDate}</p>
        </div>
        {links.length > 0 && links[0].url && (
          <Button
            className="bg-gradient-to-r from-primary to-accent hover:opacity-90 transition-opacity w-full sm:w-auto"
            onClick={() => window.open(links[0].url, "_blank")}
          >
            <CalendarIcon className="w-4 h-4 mr-2" />
            Schedule Call
          </Button>
        )}
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="metric-card">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
              <CalendarIcon className="w-5 h-5 text-primary" />
            </div>
          </div>
          <p className="text-3xl font-bold">{stats.total_bookings}</p>
          <p className="text-sm text-muted-foreground">Total Bookings</p>
        </div>

        <div className="metric-card">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-success/10 flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5 text-success" />
            </div>
          </div>
          <p className="text-3xl font-bold text-success">{stats.completed}</p>
          <p className="text-sm text-muted-foreground">Completed</p>
        </div>

        <div className="metric-card">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center">
              <Clock className="w-5 h-5 text-accent" />
            </div>
          </div>
          <p className="text-3xl font-bold">{stats.upcoming}</p>
          <p className="text-sm text-muted-foreground">Upcoming</p>
        </div>

        <div className="metric-card">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
              <Users className="w-5 h-5 text-primary" />
            </div>
          </div>
          <p className="text-3xl font-bold">{stats.show_rate.toFixed(0)}%</p>
          <p className="text-sm text-muted-foreground">Show Rate</p>
        </div>
      </div>

      {/* Upcoming Bookings - Only show scheduled calls in the future */}
      <div className="metric-card">
        <h3 className="font-semibold mb-4">Upcoming Calls</h3>
        {bookingsLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-primary" />
          </div>
        ) : bookings.filter(b => b.status === "scheduled" && new Date(b.scheduled_at) > new Date()).length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <CalendarIcon className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>No upcoming calls scheduled</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2">
            {bookings
              .filter(b => b.status === "scheduled" && new Date(b.scheduled_at) > new Date())
              .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())
              .map((booking) => (
              <div
                key={booking.id}
                className="flex items-center justify-between gap-3 p-4 rounded-lg border bg-card hover:bg-accent/5 transition-colors"
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  {/* Date box */}
                  <div className="w-14 h-14 rounded-lg bg-primary/10 flex flex-col items-center justify-center shrink-0">
                    <span className="text-[10px] text-muted-foreground uppercase">
                      {formatDate(booking.scheduled_at).split(" ")[0]}
                    </span>
                    <span className="text-xl font-bold leading-none">
                      {new Date(booking.scheduled_at).getDate()}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {formatTime(booking.scheduled_at)}
                    </span>
                  </div>
                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold truncate">
                        {booking.guest_name || booking.follower_name || "Guest"}
                      </span>
                      <span className="text-xs px-1.5 py-0.5 rounded bg-secondary text-muted-foreground">
                        {booking.duration_minutes} min
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground truncate">
                      {booking.title || booking.meeting_type}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      {booking.guest_email && (
                        <span className="text-xs text-muted-foreground truncate">
                          {booking.guest_email}
                        </span>
                      )}
                      {booking.platform && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary capitalize">
                          {booking.platform}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {booking.meeting_url && (
                    <Button
                      size="sm"
                      className="bg-primary hover:bg-primary/90"
                      onClick={() => window.open(booking.meeting_url, "_blank")}
                    >
                      <Video className="w-4 h-4 mr-1" />
                      Join Call
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive hover:bg-destructive/10"
                    onClick={() => handleCancelBooking(booking.id, booking.title || booking.meeting_type)}
                    disabled={cancelBookingMutation.isPending}
                  >
                    {cancelBookingMutation.isPending ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Trash2 className="w-4 h-4" />
                    )}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Services */}
      <div className="metric-card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">Your Services</h3>
          {links.length > 0 && links.length < 5 && !showCreateForm && (
            <Button size="sm" onClick={() => setShowCreateForm(true)}>
              <Plus className="w-4 h-4 mr-1" />
              New Service
            </Button>
          )}
        </div>

        {/* Create Form */}
        {showCreateForm && (
          <div className="mb-4 p-4 rounded-lg border bg-secondary/30">
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-medium">Add Service</h4>
              <Button variant="ghost" size="sm" onClick={() => setShowCreateForm(false)}>
                <X className="w-4 h-4" />
              </Button>
            </div>

            {!hasConnectedPlatforms ? (
              <div className="text-center py-6">
                <AlertCircle className="w-10 h-10 mx-auto mb-3 text-yellow-500" />
                <p className="text-sm text-muted-foreground mb-3">
                  Connect a platform in Settings first
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => navigate("/settings?tab=connections")}
                >
                  <Settings className="w-4 h-4 mr-2" />
                  Go to Settings
                </Button>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {/* Service Type */}
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Service Type</label>
                    <select
                      value={selectedServiceType}
                      onChange={(e) => handleServiceTypeChange(e.target.value)}
                      className="w-full px-3 py-2 rounded border bg-background text-sm"
                    >
                      {SERVICE_TYPES.map(type => (
                        <option key={type.value} value={type.value}>{type.label}</option>
                      ))}
                    </select>
                  </div>

                  {/* Duration */}
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Duration</label>
                    <div className="flex gap-1">
                      <select
                        value={selectedDuration}
                        onChange={(e) => handleDurationChange(parseInt(e.target.value))}
                        className={cn("px-3 py-2 rounded border bg-background text-sm", selectedDuration === -1 ? "w-1/2" : "w-full")}
                      >
                        {DURATIONS.map(dur => (
                          <option key={dur.value} value={dur.value}>{dur.label}</option>
                        ))}
                      </select>
                      {selectedDuration === -1 && (
                        <input
                          type="number"
                          min="5"
                          max="480"
                          value={customDuration}
                          onChange={(e) => handleCustomDuration(parseInt(e.target.value) || 30)}
                          className="w-1/2 px-2 py-2 rounded border bg-background text-sm"
                          placeholder="min"
                        />
                      )}
                    </div>
                  </div>

                  {/* Price */}
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Price</label>
                    <div className="flex gap-1">
                      <select
                        value={selectedPrice}
                        onChange={(e) => handlePriceChange(parseInt(e.target.value))}
                        className={cn("px-3 py-2 rounded border bg-background text-sm", selectedPrice === -1 ? "w-1/2" : "w-full")}
                      >
                        {PRICES.map(p => (
                          <option key={p.value} value={p.value}>{p.label}</option>
                        ))}
                      </select>
                      {selectedPrice === -1 && (
                        <input
                          type="number"
                          min="0"
                          value={customPrice}
                          onChange={(e) => handleCustomPrice(parseInt(e.target.value) || 0)}
                          className="w-1/2 px-2 py-2 rounded border bg-background text-sm"
                          placeholder="€"
                        />
                      )}
                    </div>
                  </div>

                  {/* Platform */}
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Platform</label>
                    <select
                      value={newLink.platform}
                      onChange={(e) => setNewLink(prev => ({ ...prev, platform: e.target.value, url: "" }))}
                      className="w-full px-3 py-2 rounded border bg-background text-sm"
                    >
                      {connectedPlatforms.map(platform => (
                        <option key={platform.value} value={platform.value}>{platform.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Custom service name if "other" selected */}
                {selectedServiceType === "other" && (
                  <div className="mt-3">
                    <input
                      type="text"
                      placeholder="Custom service name (e.g. VIP Consultation)"
                      value={customServiceType}
                      onChange={(e) => handleCustomServiceType(e.target.value)}
                      className="w-full px-3 py-2 rounded border bg-background text-sm"
                    />
                  </div>
                )}

                {/* URL info based on platform */}
                {newLink.platform === "clonnect" ? (
                  <div className="mt-3 flex items-center gap-2 px-3 py-2 rounded bg-success/10 text-sm text-success">
                    <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                    <span>Internal Clonnect booking system - customers book via your booking page</span>
                  </div>
                ) : newLink.platform === "google-meet" && googleConnected ? (
                  <div className="mt-3 flex items-center gap-2 px-3 py-2 rounded bg-success/10 text-sm text-success">
                    <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                    <span>Google Meet connected - video link will be created automatically when booked</span>
                  </div>
                ) : newLink.platform === "google-meet" && !googleConnected ? (
                  <div className="mt-3 flex items-center gap-2 px-3 py-2 rounded bg-yellow-500/10 text-sm text-yellow-600">
                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                    <span>Connect Google in Settings to auto-generate Meet links</span>
                  </div>
                ) : null}

                <div className="flex justify-end mt-4">
                  <Button onClick={handleCreateLink} disabled={createBookingLink.isPending}>
                    {createBookingLink.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
                    Create Service
                  </Button>
                </div>
              </>
            )}
          </div>
        )}

        {linksLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-primary" />
          </div>
        ) : links.length === 0 && !showCreateForm ? (
          <div className="text-center py-12">
            <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
              <CalendarIcon className="w-8 h-8 text-primary" />
            </div>
            <h4 className="text-lg font-semibold mb-2">Create your first Service</h4>
            <p className="text-muted-foreground text-sm max-w-sm mx-auto mb-4">
              Set up call services for your followers to book with you
            </p>
            <Button
              className="bg-gradient-to-r from-primary to-accent hover:opacity-90"
              onClick={() => setShowCreateForm(true)}
            >
              <Plus className="w-4 h-4 mr-2" />
              New Service
            </Button>
          </div>
        ) : links.length > 0 ? (
          <div className="space-y-2">
            {links.map((link) => (
              <div
                key={link.id}
                className="flex items-center justify-between gap-3 p-3 rounded-lg border bg-card hover:bg-accent/5 transition-colors"
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0">
                    <PlatformLogo platform={link.platform} size={32} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium truncate">{link.title}</span>
                      <span className="text-xs text-muted-foreground">{link.duration_minutes} min</span>
                      <span className={cn(
                        "text-xs font-medium px-1.5 py-0.5 rounded",
                        (link as any).price === 0 ? "bg-success/10 text-success" : "bg-primary/10 text-primary"
                      )}>
                        {formatPrice((link as any).price || 0)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground capitalize">
                      {link.platform === "google-meet" ? "Google Meet" : link.platform === "clonnect" ? "Clonnect" : link.platform}
                    </p>
                  </div>
                </div>
                <div className="flex gap-1 flex-shrink-0">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive hover:bg-destructive/10"
                    onClick={() => handleDeleteLink(link.id, link.title)}
                    disabled={deleteBookingLinkMutation.isPending}
                    title="Delete"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
