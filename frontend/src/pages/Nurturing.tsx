import { useState } from "react";
import {
  Play, Users, CheckCircle2, Loader2, AlertCircle, Clock, Mail,
  Snowflake, DollarSign, Timer, HelpCircle, CalendarClock, ShoppingCart,
  RefreshCw, Gift, ChevronDown, ChevronUp, Edit2, X, Save, Trash2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  useNurturingSequences,
  useNurturingStats,
  useToggleNurturingSequence,
  useUpdateNurturingSequence,
  useCancelNurturing
} from "@/hooks/useApi";
import { getNurturingEnrolled } from "@/services/api";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

// Unique icons for each sequence type
const sequenceIcons: Record<string, React.ReactNode> = {
  interest_cold: <Snowflake className="w-5 h-5" />,
  objection_price: <DollarSign className="w-5 h-5" />,
  objection_time: <Timer className="w-5 h-5" />,
  objection_doubt: <HelpCircle className="w-5 h-5" />,
  objection_later: <CalendarClock className="w-5 h-5" />,
  abandoned: <ShoppingCart className="w-5 h-5" />,
  re_engagement: <RefreshCw className="w-5 h-5" />,
  post_purchase: <Gift className="w-5 h-5" />,
};

// Colors for each sequence type
const sequenceColors: Record<string, string> = {
  interest_cold: "text-blue-400 bg-blue-400/10",
  objection_price: "text-green-400 bg-green-400/10",
  objection_time: "text-orange-400 bg-orange-400/10",
  objection_doubt: "text-purple-400 bg-purple-400/10",
  objection_later: "text-yellow-400 bg-yellow-400/10",
  abandoned: "text-red-400 bg-red-400/10",
  re_engagement: "text-cyan-400 bg-cyan-400/10",
  post_purchase: "text-pink-400 bg-pink-400/10",
};

// Descriptions for sequence types
const sequenceDescriptions: Record<string, string> = {
  interest_cold: "Follow up with leads who showed interest but didn't convert",
  objection_price: "Address price concerns with value propositions",
  objection_time: "Help busy leads see how they can fit this in",
  objection_doubt: "Resolve doubts and build confidence",
  objection_later: "Re-engage leads who said they'd think about it",
  abandoned: "Recover leads who almost purchased",
  re_engagement: "Win back inactive leads",
  post_purchase: "Nurture customers after purchase",
};

interface EnrolledUser {
  follower_id: string;
  next_scheduled: string;
  pending_steps: Array<{ step: number; scheduled_at: string; message_preview: string }>;
}

export default function Nurturing() {
  const { data: sequencesData, isLoading: sequencesLoading, error: sequencesError } = useNurturingSequences();
  const { data: statsData, isLoading: statsLoading } = useNurturingStats();
  const toggleSequence = useToggleNurturingSequence();
  const updateSequence = useUpdateNurturingSequence();
  const cancelNurturing = useCancelNurturing();
  const { toast } = useToast();

  const [expandedSequence, setExpandedSequence] = useState<string | null>(null);
  const [enrolledUsers, setEnrolledUsers] = useState<Record<string, EnrolledUser[]>>({});
  const [loadingEnrolled, setLoadingEnrolled] = useState<string | null>(null);
  const [editingSequence, setEditingSequence] = useState<string | null>(null);
  const [editSteps, setEditSteps] = useState<Array<{ delay_hours: number; message: string }>>([]);

  // Loading state
  if (sequencesLoading || statsLoading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  // Error state
  if (sequencesError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <AlertCircle className="w-12 h-12 text-destructive" />
        <p className="text-muted-foreground">Failed to load nurturing data</p>
        <p className="text-sm text-destructive">{sequencesError.message}</p>
      </div>
    );
  }

  const sequences = sequencesData?.sequences || [];
  const stats = statsData || { total: 0, pending: 0, sent: 0, cancelled: 0 };

  const activeSequences = sequences.filter(s => s.is_active !== false).length;
  const totalEnrolled = sequences.reduce((sum, s) => sum + (s.enrolled_count || 0), 0);
  const totalSent = sequences.reduce((sum, s) => sum + (s.sent_count || 0), 0);

  const handleToggle = async (sequenceType: string) => {
    try {
      await toggleSequence.mutateAsync(sequenceType);
      toast({
        title: "Sequence toggled",
        description: "Sequence status updated successfully",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to toggle sequence",
        variant: "destructive",
      });
    }
  };

  const handleExpand = async (sequenceType: string) => {
    if (expandedSequence === sequenceType) {
      setExpandedSequence(null);
      return;
    }

    setExpandedSequence(sequenceType);

    if (!enrolledUsers[sequenceType]) {
      setLoadingEnrolled(sequenceType);
      try {
        const data = await getNurturingEnrolled(undefined, sequenceType);
        setEnrolledUsers(prev => ({ ...prev, [sequenceType]: data.enrolled || [] }));
      } catch (error) {
        console.error("Failed to load enrolled users", error);
      }
      setLoadingEnrolled(null);
    }
  };

  const handleEditStart = (seq: any) => {
    setEditingSequence(seq.type);
    // Deep copy steps to avoid mutating original
    setEditSteps(seq.steps?.map((s: any) => ({ ...s })) || []);
  };

  const handleEditSave = async () => {
    if (!editingSequence) return;

    console.log("Saving sequence:", editingSequence);
    console.log("Steps to save:", editSteps);

    try {
      await updateSequence.mutateAsync({
        sequenceType: editingSequence,
        steps: editSteps,
      });
      toast({
        title: "Sequence updated",
        description: "Steps saved successfully",
      });
      setEditingSequence(null);
    } catch (error) {
      console.error("Save error:", error);
      toast({
        title: "Error",
        description: "Failed to update sequence",
        variant: "destructive",
      });
    }
  };

  const handleCancelFollowup = async (followerId: string, sequenceType: string) => {
    try {
      await cancelNurturing.mutateAsync({ followerId, sequenceType });
      setEnrolledUsers(prev => ({
        ...prev,
        [sequenceType]: prev[sequenceType]?.filter(u => u.follower_id !== followerId) || []
      }));
      toast({
        title: "Cancelled",
        description: "Followup cancelled for this user",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to cancel followup",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Nurturing Sequences</h1>
        <p className="text-muted-foreground">Automated follow-up sequences for lead nurturing</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="metric-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
              <Play className="w-5 h-5 text-primary" />
            </div>
            <div>
              <p className="text-2xl font-bold">{activeSequences}</p>
              <p className="text-sm text-muted-foreground">Active Sequences</p>
            </div>
          </div>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center">
              <Users className="w-5 h-5 text-accent" />
            </div>
            <div>
              <p className="text-2xl font-bold">{totalEnrolled}</p>
              <p className="text-sm text-muted-foreground">Pending Followups</p>
            </div>
          </div>
        </div>
        <div className="metric-card">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-success/10 flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5 text-success" />
            </div>
            <div>
              <p className="text-2xl font-bold">{totalSent}</p>
              <p className="text-sm text-muted-foreground">Messages Sent</p>
            </div>
          </div>
        </div>
      </div>

      {/* Sequences List */}
      <div>
        <h3 className="font-semibold mb-4">Available Sequences</h3>
        <div className="space-y-4">
          {sequences.map((seq) => (
            <div key={seq.id} className="metric-card">
              {/* Main row */}
              <div className="flex items-start gap-4">
                {/* Unique icon */}
                <div className={cn(
                  "w-12 h-12 rounded-xl flex items-center justify-center",
                  sequenceColors[seq.type] || "bg-secondary text-muted-foreground"
                )}>
                  {sequenceIcons[seq.type] || <Mail className="w-5 h-5" />}
                </div>

                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <h3 className="font-semibold">{seq.name}</h3>
                    <Switch
                      checked={seq.is_active !== false}
                      onCheckedChange={() => handleToggle(seq.type)}
                      disabled={toggleSequence.isPending}
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleEditStart(seq)}
                    >
                      <Edit2 className="w-4 h-4" />
                    </Button>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">
                    {sequenceDescriptions[seq.type] || seq.type}
                  </p>

                  {/* Steps preview */}
                  <div className="mt-3 flex flex-wrap gap-2">
                    {seq.steps?.slice(0, 4).map((step: any, idx: number) => (
                      <div
                        key={idx}
                        className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-secondary"
                      >
                        <Clock className="w-3 h-3" />
                        <span>{step.delay_hours}h</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="text-right flex items-center gap-4">
                  <div className="flex items-center gap-4 text-sm">
                    <div className="text-center">
                      <p className="font-semibold">{seq.enrolled_count || 0}</p>
                      <p className="text-xs text-muted-foreground">Pending</p>
                    </div>
                    <div className="text-center">
                      <p className="font-semibold text-success">{seq.sent_count || 0}</p>
                      <p className="text-xs text-muted-foreground">Sent</p>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleExpand(seq.type)}
                  >
                    {expandedSequence === seq.type ? (
                      <ChevronUp className="w-4 h-4" />
                    ) : (
                      <ChevronDown className="w-4 h-4" />
                    )}
                  </Button>
                </div>
              </div>

              {/* Expanded section - Enrolled users */}
              {expandedSequence === seq.type && (
                <div className="mt-4 pt-4 border-t">
                  <h4 className="text-sm font-medium mb-3">Enrolled Users</h4>
                  {loadingEnrolled === seq.type ? (
                    <div className="flex justify-center py-4">
                      <Loader2 className="w-5 h-5 animate-spin" />
                    </div>
                  ) : (enrolledUsers[seq.type]?.length || 0) === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No users currently enrolled
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {enrolledUsers[seq.type]?.map((user) => (
                        <div
                          key={user.follower_id}
                          className="flex items-center justify-between p-3 rounded-lg bg-secondary/50"
                        >
                          <div>
                            <p className="font-medium text-sm">{user.follower_id}</p>
                            <p className="text-xs text-muted-foreground">
                              Next: {new Date(user.next_scheduled).toLocaleString()}
                            </p>
                          </div>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive hover:text-destructive"
                            onClick={() => handleCancelFollowup(user.follower_id, seq.type)}
                            disabled={cancelNurturing.isPending}
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Edit Modal */}
      {editingSequence && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-background rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold">Edit Sequence Steps</h2>
              <Button variant="ghost" size="sm" onClick={() => setEditingSequence(null)}>
                <X className="w-4 h-4" />
              </Button>
            </div>

            <div className="space-y-4">
              {editSteps.map((step, idx) => (
                <div key={idx} className="p-4 rounded-lg border">
                  <div className="flex items-center gap-4 mb-2">
                    <label className="text-sm font-medium">Delay (hours):</label>
                    <input
                      type="number"
                      value={step.delay_hours}
                      onChange={(e) => {
                        setEditSteps(prev => prev.map((s, i) =>
                          i === idx ? { ...s, delay_hours: parseInt(e.target.value) || 0 } : s
                        ));
                      }}
                      className="w-20 px-2 py-1 rounded border bg-background"
                    />
                  </div>
                  <textarea
                    value={step.message}
                    onChange={(e) => {
                      setEditSteps(prev => prev.map((s, i) =>
                        i === idx ? { ...s, message: e.target.value } : s
                      ));
                    }}
                    className="w-full h-24 px-3 py-2 rounded border bg-background resize-none"
                    placeholder="Message template..."
                  />
                </div>
              ))}
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <Button variant="outline" onClick={() => setEditingSequence(null)}>
                Cancel
              </Button>
              <Button onClick={handleEditSave} disabled={updateSequence.isPending}>
                {updateSequence.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                ) : (
                  <Save className="w-4 h-4 mr-2" />
                )}
                Save Changes
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Info Box */}
      <div className="metric-card bg-secondary/30 border-dashed">
        <h3 className="font-semibold mb-2 flex items-center gap-2">
          <Mail className="w-4 h-4" />
          How Nurturing Works
        </h3>
        <ul className="text-sm text-muted-foreground space-y-2">
          <li>• Sequences are triggered automatically based on conversation intent</li>
          <li>• Each step is sent at the configured delay after the trigger</li>
          <li>• Sequences are cancelled if the user responds or converts</li>
          <li>• Toggle sequences on/off to control which ones are active</li>
        </ul>
      </div>
    </div>
  );
}
