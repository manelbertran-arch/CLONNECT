import { useState } from "react";
import { Calendar as CalendarIcon, Clock, Video, Users, CheckCircle2, XCircle, Loader2, AlertCircle, ExternalLink, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCalendarStats, useBookings, useBookingLinks, useCreateBookingLink } from "@/hooks/useApi";
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

export default function Calendar() {
  const { data: statsData, isLoading: statsLoading, error: statsError } = useCalendarStats();
  const { data: bookingsData, isLoading: bookingsLoading } = useBookings(undefined, true);
  const { data: linksData, isLoading: linksLoading, refetch: refetchLinks } = useBookingLinks();
  const createBookingLink = useCreateBookingLink();
  const { toast } = useToast();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newLink, setNewLink] = useState({
    meeting_type: "discovery",
    title: "Discovery Call",
    url: "",
    platform: "calendly",
    duration_minutes: 30,
    description: "",
  });

  const today = new Date();
  const formattedDate = today.toLocaleDateString("es-ES", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const handleCreateLink = async () => {
    if (!newLink.url) {
      toast({ title: "Error", description: "URL is required", variant: "destructive" });
      return;
    }
    try {
      await createBookingLink.mutateAsync(newLink);
      toast({ title: "Success", description: "Booking link created" });
      setShowCreateForm(false);
      setNewLink({ meeting_type: "discovery", title: "Discovery Call", url: "", platform: "calendly", duration_minutes: 30, description: "" });
      refetchLinks();
    } catch (error: any) {
      toast({ title: "Error", description: error.message || "Failed to create link", variant: "destructive" });
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
              <input
                type="text"
                placeholder="Title (e.g. Discovery Call)"
                value={newLink.title}
                onChange={(e) => setNewLink(prev => ({ ...prev, title: e.target.value }))}
                className="px-3 py-2 rounded border bg-background text-sm"
              />
              <input
                type="text"
                placeholder="Meeting Type (e.g. discovery)"
                value={newLink.meeting_type}
                onChange={(e) => setNewLink(prev => ({ ...prev, meeting_type: e.target.value }))}
                className="px-3 py-2 rounded border bg-background text-sm"
              />
              <input
                type="url"
                placeholder="Calendly/Cal.com URL"
                value={newLink.url}
                onChange={(e) => setNewLink(prev => ({ ...prev, url: e.target.value }))}
                className="px-3 py-2 rounded border bg-background text-sm sm:col-span-2"
              />
              <select
                value={newLink.platform}
                onChange={(e) => setNewLink(prev => ({ ...prev, platform: e.target.value }))}
                className="px-3 py-2 rounded border bg-background text-sm"
              >
                <option value="calendly">Calendly</option>
                <option value="cal.com">Cal.com</option>
                <option value="other">Other</option>
              </select>
              <input
                type="number"
                placeholder="Duration (minutes)"
                value={newLink.duration_minutes}
                onChange={(e) => setNewLink(prev => ({ ...prev, duration_minutes: parseInt(e.target.value) || 30 }))}
                className="px-3 py-2 rounded border bg-background text-sm"
              />
            </div>
            <div className="flex justify-end mt-3">
              <Button onClick={handleCreateLink} disabled={createBookingLink.isPending}>
                {createBookingLink.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                Create Link
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
            <p className="text-sm mt-2 mb-4">Add your Calendly or Cal.com links</p>
            <Button variant="outline" onClick={() => setShowCreateForm(true)}>
              <Plus className="w-4 h-4 mr-2" /> Create Booking Link
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {links.map((link) => (
              <div
                key={link.meeting_type}
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
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => window.open(link.url, "_blank")}
                  >
                    <ExternalLink className="w-4 h-4" />
                  </Button>
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
