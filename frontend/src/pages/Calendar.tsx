import { useState } from "react";
import { Calendar as CalendarIcon, Clock, Video, Users, CheckCircle2, XCircle, Loader2, AlertCircle, ExternalLink, Plus, X, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCalendarStats, useBookings, useBookingLinks, useCreateBookingLink, useDeleteBookingLink, useCalendlySyncStatus } from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

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

// Platform options for booking links
const PLATFORMS = [
  { value: "calendly", label: "Calendly", placeholder: "https://calendly.com/tu-usuario/30min" },
  { value: "cal.com", label: "Cal.com", placeholder: "https://cal.com/tu-usuario/30min" },
  { value: "zoom", label: "Zoom Scheduler", placeholder: "https://zoom.us/schedule/..." },
  { value: "hubspot", label: "HubSpot Meetings", placeholder: "https://meetings.hubspot.com/..." },
  { value: "acuity", label: "Acuity Scheduling", placeholder: "https://acuityscheduling.com/..." },
  { value: "tidycal", label: "TidyCal", placeholder: "https://tidycal.com/tu-usuario/..." },
  { value: "savvycal", label: "SavvyCal", placeholder: "https://savvycal.com/tu-usuario/..." },
  { value: "manual", label: "Manual (link personalizado)", placeholder: "https://..." },
];

// Meeting type options with auto-generated slugs
const MEETING_TYPES = [
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
  { value: -1, label: "Other" },
];

export default function Calendar() {
  const { data: statsData, isLoading: statsLoading, error: statsError } = useCalendarStats();
  const { data: bookingsData, isLoading: bookingsLoading } = useBookings(undefined, true);
  const { data: linksData, isLoading: linksLoading, refetch: refetchLinks } = useBookingLinks();
  const { data: syncStatus } = useCalendlySyncStatus();
  const createBookingLink = useCreateBookingLink();
  const deleteBookingLinkMutation = useDeleteBookingLink();
  const { toast } = useToast();

  // Check if Calendly is connected
  const calendlyConnected = syncStatus?.calendly_connected ?? false;

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedMeetingType, setSelectedMeetingType] = useState("discovery");
  const [customMeetingType, setCustomMeetingType] = useState("");
  const [selectedDuration, setSelectedDuration] = useState(30);
  const [customDuration, setCustomDuration] = useState(30);
  const [newLink, setNewLink] = useState({
    meeting_type: "discovery",
    title: "Discovery Call",
    url: "",
    platform: "calendly",
    duration_minutes: 30,
    description: "",
  });

  // Handle meeting type change
  const handleMeetingTypeChange = (value: string) => {
    setSelectedMeetingType(value);
    const meetingType = MEETING_TYPES.find(m => m.value === value);
    if (meetingType && value !== "other") {
      setNewLink(prev => ({
        ...prev,
        meeting_type: meetingType.slug,
        title: meetingType.label
      }));
    }
  };

  // Handle custom meeting type
  const handleCustomMeetingType = (value: string) => {
    setCustomMeetingType(value);
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

  const today = new Date();
  const formattedDate = today.toLocaleDateString("es-ES", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const handleCreateLink = async () => {
    // Validate URL - not required if Calendly is connected and platform is Calendly
    const isCalendlyAutoCreate = newLink.platform === "calendly" && calendlyConnected;
    if (!newLink.url && !isCalendlyAutoCreate) {
      toast({ title: "Error", description: "Booking URL is required", variant: "destructive" });
      return;
    }

    // Validate meeting type for custom
    if (selectedMeetingType === "other" && !customMeetingType.trim()) {
      toast({ title: "Error", description: "Please enter a custom meeting type name", variant: "destructive" });
      return;
    }

    // Check limit of 5 booking links
    if (links.length >= 5) {
      toast({ title: "Error", description: "Maximum 5 booking links allowed. Delete one first.", variant: "destructive" });
      return;
    }

    try {
      const result = await createBookingLink.mutateAsync(newLink);
      const message = result.calendly_auto_created
        ? "Link created automatically in Calendly!"
        : "Booking link created";
      toast({ title: "Success", description: message });
      setShowCreateForm(false);
      // Reset form
      setSelectedMeetingType("discovery");
      setCustomMeetingType("");
      setSelectedDuration(30);
      setCustomDuration(30);
      setNewLink({ meeting_type: "discovery", title: "Discovery Call", url: "", platform: "calendly", duration_minutes: 30, description: "" });
      refetchLinks();
    } catch (error: any) {
      toast({ title: "Error", description: error.message || "Failed to create link", variant: "destructive" });
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight">Calendar</h1>
          <p className="text-muted-foreground text-sm sm:text-base">{formattedDate}</p>
        </div>
        {links.length > 0 && (
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

      {/* Upcoming Bookings */}
      <div className="metric-card">
        <h3 className="font-semibold mb-4">Upcoming Calls</h3>
        {bookingsLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-primary" />
          </div>
        ) : bookings.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <CalendarIcon className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>No upcoming calls scheduled</p>
          </div>
        ) : (
          <div className="space-y-3">
            {bookings.slice(0, 5).map((booking) => (
              <div
                key={booking.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-lg border bg-card hover:bg-accent/5 transition-colors"
              >
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-lg bg-primary/10 flex flex-col items-center justify-center shrink-0">
                    <span className="text-xs text-muted-foreground">
                      {formatDate(booking.scheduled_at).split(" ")[0]}
                    </span>
                    <span className="text-lg font-bold">
                      {new Date(booking.scheduled_at).getDate()}
                    </span>
                  </div>
                  <div className="min-w-0">
                    <p className="font-medium truncate">
                      {booking.follower_name || booking.title || booking.meeting_type}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {formatTime(booking.scheduled_at)} - {booking.duration_minutes} min
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3 ml-16 sm:ml-0">
                  <span
                    className={cn(
                      "text-xs px-2 py-1 rounded-full flex items-center gap-1",
                      statusColors[booking.status]
                    )}
                  >
                    {statusIcons[booking.status]}
                    {booking.status}
                  </span>
                  {booking.meeting_url && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => window.open(booking.meeting_url, "_blank")}
                    >
                      <Video className="w-4 h-4 mr-1" />
                      Join
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Booking Links */}
      <div className="metric-card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">Your Booking Links</h3>
          <Button size="sm" variant="outline" onClick={() => setShowCreateForm(true)}>
            <Plus className="w-4 h-4 mr-1" /> Add Link
          </Button>
        </div>

        {/* Create Form */}
        {showCreateForm && (
          <div className="mb-4 p-4 rounded-lg border bg-secondary/30">
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-medium">Add Booking Link</h4>
              <Button variant="ghost" size="sm" onClick={() => setShowCreateForm(false)}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* Meeting Type Dropdown */}
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Meeting Type</label>
                <select
                  value={selectedMeetingType}
                  onChange={(e) => handleMeetingTypeChange(e.target.value)}
                  className="w-full px-3 py-2 rounded border bg-background text-sm"
                >
                  {MEETING_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
              </div>

              {/* Custom Meeting Type (if "Other" selected) */}
              {selectedMeetingType === "other" ? (
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Custom Name</label>
                  <input
                    type="text"
                    placeholder="e.g. VIP Consultation"
                    value={customMeetingType}
                    onChange={(e) => handleCustomMeetingType(e.target.value)}
                    className="w-full px-3 py-2 rounded border bg-background text-sm"
                  />
                </div>
              ) : (
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Slug (auto-generated)</label>
                  <input
                    type="text"
                    value={newLink.meeting_type}
                    onChange={(e) => setNewLink(prev => ({ ...prev, meeting_type: e.target.value }))}
                    className="w-full px-3 py-2 rounded border bg-background text-sm"
                    placeholder="discovery"
                  />
                </div>
              )}

              {/* Platform Dropdown */}
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Platform</label>
                <select
                  value={newLink.platform}
                  onChange={(e) => setNewLink(prev => ({ ...prev, platform: e.target.value, url: "" }))}
                  className="w-full px-3 py-2 rounded border bg-background text-sm"
                >
                  {PLATFORMS.map(platform => (
                    <option key={platform.value} value={platform.value}>{platform.label}</option>
                  ))}
                </select>
              </div>

              {/* Duration Dropdown */}
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Duration</label>
                <div className="flex gap-2">
                  <select
                    value={selectedDuration}
                    onChange={(e) => handleDurationChange(parseInt(e.target.value))}
                    className="flex-1 px-3 py-2 rounded border bg-background text-sm"
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
                      className="w-20 px-3 py-2 rounded border bg-background text-sm"
                      placeholder="min"
                    />
                  )}
                </div>
              </div>

              {/* URL Field - conditional based on Calendly connection */}
              {newLink.platform === "calendly" && calendlyConnected ? (
                <div className="space-y-1 sm:col-span-2">
                  <div className="flex items-center gap-2 px-3 py-3 rounded border bg-success/10 border-success/30 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
                    <span className="text-success">
                      Calendly connected - link will be created automatically
                    </span>
                  </div>
                </div>
              ) : newLink.platform === "calendly" && !calendlyConnected ? (
                <div className="space-y-1 sm:col-span-2">
                  <div className="flex flex-col gap-2 px-3 py-3 rounded border bg-yellow-500/10 border-yellow-500/30 text-sm">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 text-yellow-600 flex-shrink-0" />
                      <span className="text-yellow-600">
                        Connect Calendly in Settings for auto-creation
                      </span>
                    </div>
                    <input
                      type="url"
                      placeholder="Or paste your Calendly link manually"
                      value={newLink.url}
                      onChange={(e) => setNewLink(prev => ({ ...prev, url: e.target.value }))}
                      className="w-full px-3 py-2 rounded border bg-background text-sm"
                    />
                  </div>
                </div>
              ) : (
                <div className="space-y-1 sm:col-span-2">
                  <label className="text-xs text-muted-foreground">Booking URL</label>
                  <input
                    type="url"
                    placeholder={PLATFORMS.find(p => p.value === newLink.platform)?.placeholder || "https://..."}
                    value={newLink.url}
                    onChange={(e) => setNewLink(prev => ({ ...prev, url: e.target.value }))}
                    className="w-full px-3 py-2 rounded border bg-background text-sm"
                  />
                </div>
              )}
            </div>
            <div className="flex justify-end mt-4">
              <Button onClick={handleCreateLink} disabled={createBookingLink.isPending}>
                {createBookingLink.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                {newLink.platform === "calendly" && calendlyConnected ? "Create in Calendly" : "Create Link"}
              </Button>
            </div>
          </div>
        )}

        {linksLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-primary" />
          </div>
        ) : links.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Video className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>No booking links configured</p>
            <p className="text-sm mt-2 mb-4">Add your Calendly, Cal.com, TidyCal or WhatsApp booking links</p>
            <Button variant="outline" onClick={() => setShowCreateForm(true)}>
              <Plus className="w-4 h-4 mr-2" /> Create Booking Link
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {links.map((link) => (
              <div
                key={link.id}
                className="p-4 rounded-lg border bg-card hover:bg-accent/5 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-medium">{link.title}</p>
                    <p className="text-sm text-muted-foreground mt-1">
                      {link.duration_minutes} min - {link.platform}
                    </p>
                    {link.description && (
                      <p className="text-sm text-muted-foreground mt-2">
                        {link.description}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => window.open(link.url, "_blank")}
                    >
                      <ExternalLink className="w-4 h-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive hover:text-destructive hover:bg-destructive/10"
                      onClick={() => handleDeleteLink(link.id, link.title)}
                      disabled={deleteBookingLinkMutation.isPending}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Stats Breakdown */}
      <div className="grid grid-cols-2 gap-4">
        <div className="metric-card">
          <h3 className="font-semibold mb-4">Outcome Breakdown</h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-success" /> Completed
              </span>
              <span className="font-medium">{stats.completed}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm flex items-center gap-2">
                <XCircle className="w-4 h-4 text-destructive" /> Cancelled
              </span>
              <span className="font-medium">{stats.cancelled}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-yellow-600" /> No-Show
              </span>
              <span className="font-medium">{stats.no_show}</span>
            </div>
          </div>
        </div>

        <div className="metric-card">
          <h3 className="font-semibold mb-4">Show Rate</h3>
          <div className="flex items-center justify-center h-24">
            <div className="text-center">
              <div className="text-5xl font-bold text-success">{stats.show_rate.toFixed(0)}%</div>
              <p className="text-sm text-muted-foreground mt-2">of bookings completed</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
