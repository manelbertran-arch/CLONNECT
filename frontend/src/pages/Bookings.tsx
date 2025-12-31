import { useState } from "react";
import { Calendar as CalendarIcon, Clock, Video, Users, CheckCircle2, XCircle, Loader2, AlertCircle, Plus, X, Trash2, Settings, Mail, History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCalendarStats, useBookings, useBookingLinks, useCreateBookingLink, useDeleteBookingLink, useCancelBooking, useClearBookingHistory, useDeleteHistoryItem, useConnections } from "@/hooks/useApi";
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

function formatDateTimeFull(dateString: string, durationMinutes: number): string {
  const date = new Date(dateString);
  const endDate = new Date(date.getTime() + durationMinutes * 60000);

  const weekday = date.toLocaleDateString("es-ES", { weekday: "short" }).toUpperCase();
  const day = date.getDate();
  const month = date.toLocaleDateString("es-ES", { month: "short" }).toUpperCase();
  const startTime = date.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
  const endTime = endDate.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });

  return `${weekday}, ${day} ${month} • ${startTime} - ${endTime}`;
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
  const clearHistoryMutation = useClearBookingHistory();
  const deleteHistoryItemMutation = useDeleteHistoryItem();
  const { toast } = useToast();

  // Check if Google Calendar is connected (for auto Meet link generation)
  const googleConnected = connectionsData?.google?.connected ?? false;

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
    platform: "clonnect",  // Always use internal Clonnect system
    duration_minutes: 30,
    description: "",
    price: 0,
  });

  // Platform is always "clonnect" - no user choice needed
  const hasConnectedPlatforms = true;

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
      toast({ title: "Success", description: "Service created" });
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
    if (!confirm(`Cancel "${title}"?\n\nThis will:\n• Remove it from your calendar\n• Delete the Google Calendar event\n• Notify the client via email\n\nThis action cannot be undone.`)) return;
    try {
      await cancelBookingMutation.mutateAsync(bookingId);
      toast({ title: "Booking Cancelled", description: "The client has been notified" });
    } catch (error: any) {
      toast({ title: "Error", description: error.message || "Failed to cancel booking", variant: "destructive" });
    }
  };

  const handleClearHistory = async () => {
    if (!confirm("Clear all booking history? This cannot be undone.")) return;
    try {
      const result = await clearHistoryMutation.mutateAsync();
      toast({ title: "Cleared", description: `Removed ${result.deleted_count} history items` });
    } catch (error: any) {
      toast({ title: "Error", description: error.message || "Failed to clear history", variant: "destructive" });
    }
  };

  const handleDeleteHistoryItem = async (bookingId: string) => {
    try {
      await deleteHistoryItemMutation.mutateAsync(bookingId);
      toast({ title: "Deleted", description: "History item removed" });
    } catch (error: any) {
      toast({ title: "Error", description: error.message || "Failed to delete", variant: "destructive" });
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
            <div className="w-10 h-10 rounded-lg bg-destructive/10 flex items-center justify-center">
              <XCircle className="w-5 h-5 text-destructive" />
            </div>
          </div>
          <p className="text-3xl font-bold text-destructive">{stats.cancelled}</p>
          <p className="text-sm text-muted-foreground">Cancelled</p>
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
          <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2">
            {bookings
              .filter(b => b.status === "scheduled" && new Date(b.scheduled_at) > new Date())
              .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())
              .map((booking) => (
              <div
                key={booking.id}
                className="p-4 rounded-lg border bg-card hover:bg-accent/5 transition-colors"
              >
                {/* Date & Time - Top */}
                <div className="flex items-center gap-2 mb-3 text-sm text-primary font-medium">
                  <CalendarIcon className="w-4 h-4" />
                  {formatDateTimeFull(booking.scheduled_at, booking.duration_minutes)}
                </div>

                {/* Service Name */}
                <h4 className="font-semibold text-base mb-2">
                  {booking.title || booking.meeting_type}
                  <span className="text-muted-foreground font-normal ml-2">
                    ({booking.duration_minutes} min)
                  </span>
                </h4>

                {/* Client Info */}
                <div className="space-y-1 mb-4">
                  <div className="flex items-center gap-2 text-sm">
                    <Users className="w-4 h-4 text-muted-foreground" />
                    <span>{booking.guest_name || booking.follower_name || "Guest"}</span>
                  </div>
                  {booking.guest_email && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Mail className="w-4 h-4" />
                      <span>{booking.guest_email}</span>
                    </div>
                  )}
                </div>

                {/* Action Buttons */}
                <div className="flex items-center gap-2 flex-wrap">
                  {booking.meeting_url && (
                    <Button
                      size="sm"
                      className="bg-primary hover:bg-primary/90"
                      onClick={() => window.open(booking.meeting_url, "_blank")}
                    >
                      <Video className="w-4 h-4 mr-1" />
                      Join Meet
                    </Button>
                  )}
                  {booking.guest_email && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => window.open(`mailto:${booking.guest_email}?subject=Reschedule: ${booking.title || booking.meeting_type}&body=Hi ${booking.guest_name || ''},\n\nI need to reschedule our upcoming call. Would any of these times work for you?\n\n- [Option 1]\n- [Option 2]\n- [Option 3]\n\nLet me know what works best.\n\nBest regards`, "_blank")}
                    >
                      <Mail className="w-4 h-4 mr-1" />
                      Contact
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
                      <Loader2 className="w-4 h-4 animate-spin mr-1" />
                    ) : (
                      <XCircle className="w-4 h-4 mr-1" />
                    )}
                    Cancel
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent History - Completed and Cancelled bookings */}
      <div className="metric-card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold flex items-center gap-2">
            <History className="w-5 h-5" />
            Recent History
          </h3>
          {bookings.filter(b => b.status === "cancelled" || b.status === "completed").length > 0 && (
            <Button
              size="sm"
              variant="ghost"
              className="text-muted-foreground hover:text-destructive"
              onClick={handleClearHistory}
              disabled={clearHistoryMutation.isPending}
            >
              {clearHistoryMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin mr-1" />
              ) : (
                <Trash2 className="w-4 h-4 mr-1" />
              )}
              Clear All
            </Button>
          )}
        </div>
        {bookingsLoading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="w-6 h-6 animate-spin text-primary" />
          </div>
        ) : bookings.filter(b => b.status === "cancelled" || b.status === "completed").length === 0 ? (
          <div className="text-center py-6 text-muted-foreground">
            <p className="text-sm">No booking history yet</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-[300px] overflow-y-auto pr-2">
            {bookings
              .filter(b => b.status === "cancelled" || b.status === "completed")
              .sort((a, b) => new Date(b.scheduled_at).getTime() - new Date(a.scheduled_at).getTime())
              .slice(0, 10) // Show last 10
              .map((booking) => (
              <div
                key={booking.id}
                className={cn(
                  "flex items-center justify-between gap-3 p-3 rounded-lg border",
                  booking.status === "cancelled" ? "bg-destructive/5 border-destructive/20" : "bg-success/5 border-success/20"
                )}
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  {/* Status icon */}
                  <div className={cn(
                    "w-10 h-10 rounded-lg flex items-center justify-center shrink-0",
                    booking.status === "cancelled" ? "bg-destructive/10" : "bg-success/10"
                  )}>
                    {booking.status === "cancelled" ? (
                      <XCircle className="w-5 h-5 text-destructive" />
                    ) : (
                      <CheckCircle2 className="w-5 h-5 text-success" />
                    )}
                  </div>
                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className={cn(
                        "font-medium truncate",
                        booking.status === "cancelled" && "line-through text-muted-foreground"
                      )}>
                        {booking.guest_name || "Guest"}
                      </span>
                      <span className={cn(
                        "text-xs px-1.5 py-0.5 rounded font-medium",
                        booking.status === "cancelled" ? "bg-destructive/10 text-destructive" : "bg-success/10 text-success"
                      )}>
                        {booking.status === "cancelled" ? "Cancelled" : "Completed"}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {booking.title || booking.meeting_type} • {formatDate(booking.scheduled_at)} {formatTime(booking.scheduled_at)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  {/* Contact button for cancelled - maybe they want to reschedule */}
                  {booking.status === "cancelled" && booking.guest_email && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => window.open(`mailto:${booking.guest_email}?subject=Reschedule your booking?&body=Hi ${booking.guest_name || ''},\n\nI noticed you cancelled your booking. Would you like to reschedule for another time?\n\nBest regards`, "_blank")}
                      title="Offer to reschedule"
                    >
                      <Mail className="w-4 h-4 mr-1" />
                      Reschedule?
                    </Button>
                  )}
                  {/* Delete individual history item */}
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-muted-foreground hover:text-destructive h-8 w-8 p-0"
                    onClick={() => handleDeleteHistoryItem(booking.id)}
                    disabled={deleteHistoryItemMutation.isPending}
                    title="Remove from history"
                  >
                    <X className="w-4 h-4" />
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
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
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

                {/* Booking system info */}
                <div className="mt-3 flex items-center gap-2 px-3 py-2 rounded bg-primary/10 text-sm text-primary">
                  <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                  <span>
                    Customers book via your Clonnect page
                    {googleConnected && " • Google Meet link auto-generated"}
                  </span>
                </div>
                {!googleConnected && (
                  <div className="mt-2 flex items-center gap-2 px-3 py-2 rounded bg-secondary text-sm text-muted-foreground">
                    <Video className="w-4 h-4 flex-shrink-0" />
                    <span>Connect Google Calendar in Settings to auto-generate Meet links</span>
                  </div>
                )}

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
