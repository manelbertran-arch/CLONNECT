/**
 * ProfilePanel - Audience Intelligence Profile Component
 *
 * SPRINT2-T2.1: Displays unified follower profile with:
 * - Narrative context
 * - Auto-detected segments
 * - Recommended actions
 * - Objection handling suggestions
 *
 * Designed to be used in Inbox sidebar and Leads modal
 */
import { X, Mail, Phone, MessageSquare, Clock, AlertTriangle, CheckCircle2, Zap, User, Tag } from "lucide-react";
import { useAudienceProfile } from "@/hooks/useAudience";
import type { AudienceProfile } from "@/services/api";

interface ProfilePanelProps {
  creatorId: string;
  followerId: string;
  onClose?: () => void;
  showCloseButton?: boolean;
  className?: string;
}

// Priority colors
const priorityColors = {
  urgent: "bg-red-100 text-red-800 border-red-200",
  high: "bg-orange-100 text-orange-800 border-orange-200",
  medium: "bg-yellow-100 text-yellow-800 border-yellow-200",
  low: "bg-green-100 text-green-800 border-green-200",
};

const priorityLabels = {
  urgent: "Urgente",
  high: "Alta",
  medium: "Media",
  low: "Baja",
};

// Segment colors
const segmentColors: Record<string, string> = {
  hot_lead: "bg-red-100 text-red-700",
  warm_lead: "bg-orange-100 text-orange-700",
  ghost: "bg-gray-100 text-gray-700",
  price_objector: "bg-purple-100 text-purple-700",
  time_objector: "bg-blue-100 text-blue-700",
  customer: "bg-emerald-100 text-emerald-700",
  new: "bg-sky-100 text-sky-700",
};

const segmentLabels: Record<string, string> = {
  hot_lead: "Hot Lead",
  warm_lead: "Warm Lead",
  ghost: "Ghost",
  price_objector: "Obj. Precio",
  time_objector: "Obj. Tiempo",
  customer: "Cliente",
  new: "Nuevo",
};

export function ProfilePanel({
  creatorId,
  followerId,
  onClose,
  showCloseButton = true,
  className = "",
}: ProfilePanelProps) {
  const { data: profile, isLoading, isError, error } = useAudienceProfile(followerId, creatorId);

  if (isLoading) {
    return (
      <div className={`p-4 ${className}`}>
        <ProfilePanelSkeleton />
      </div>
    );
  }

  if (isError) {
    return (
      <div className={`p-4 ${className}`}>
        <div className="text-center text-gray-500">
          <AlertTriangle className="w-8 h-8 mx-auto mb-2 text-yellow-500" />
          <p className="text-sm">Error cargando perfil</p>
          <p className="text-xs text-gray-400 mt-1">{String(error)}</p>
        </div>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={`p-4 ${className}`}>
        <div className="text-center text-gray-500">
          <User className="w-8 h-8 mx-auto mb-2" />
          <p className="text-sm">Perfil no encontrado</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`bg-white rounded-lg shadow-sm border ${className}`}>
      {/* Header */}
      <div className="p-4 border-b">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            {profile.profile_pic_url ? (
              <img
                src={profile.profile_pic_url}
                alt={profile.name || profile.username || "Avatar"}
                className="w-12 h-12 rounded-full object-cover"
              />
            ) : (
              <div className="w-12 h-12 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white font-semibold text-lg">
                {(profile.name || profile.username || "?")[0].toUpperCase()}
              </div>
            )}
            <div>
              <h3 className="font-semibold text-gray-900">
                {profile.name || profile.username || "Sin nombre"}
              </h3>
              {profile.username && profile.name && (
                <p className="text-sm text-gray-500">@{profile.username}</p>
              )}
              {profile.platform && (
                <span className="text-xs text-gray-400 capitalize">{profile.platform}</span>
              )}
            </div>
          </div>
          {showCloseButton && onClose && (
            <button
              onClick={onClose}
              className="p-1 hover:bg-gray-100 rounded-full transition-colors"
            >
              <X className="w-5 h-5 text-gray-400" />
            </button>
          )}
        </div>
      </div>

      {/* Narrative */}
      {profile.narrative && (
        <div className="p-4 border-b bg-gray-50">
          <p className="text-sm text-gray-700 italic">"{profile.narrative}"</p>
        </div>
      )}

      {/* Segments */}
      {profile.segments && profile.segments.length > 0 && (
        <div className="p-4 border-b">
          <div className="flex items-center gap-2 mb-2">
            <Tag className="w-4 h-4 text-gray-400" />
            <span className="text-xs font-medium text-gray-500 uppercase">Segmentos</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {profile.segments.map((segment) => (
              <span
                key={segment}
                className={`px-2 py-1 text-xs font-medium rounded-full ${
                  segmentColors[segment] || "bg-gray-100 text-gray-700"
                }`}
              >
                {segmentLabels[segment] || segment}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Recommended Action */}
      {profile.recommended_action && (
        <div className="p-4 border-b">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-gray-400" />
            <span className="text-xs font-medium text-gray-500 uppercase">Acción Recomendada</span>
            {profile.action_priority && (
              <span
                className={`px-2 py-0.5 text-xs font-medium rounded border ${
                  priorityColors[profile.action_priority]
                }`}
              >
                {priorityLabels[profile.action_priority]}
              </span>
            )}
          </div>
          <p className="text-sm text-gray-700">{profile.recommended_action}</p>
        </div>
      )}

      {/* Objections */}
      {profile.objections && profile.objections.length > 0 && (
        <div className="p-4 border-b">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-4 h-4 text-gray-400" />
            <span className="text-xs font-medium text-gray-500 uppercase">Objeciones</span>
          </div>
          <div className="space-y-3">
            {profile.objections.map((objection, idx) => (
              <div key={idx} className="text-sm">
                <div className="flex items-center gap-2 mb-1">
                  {objection.handled ? (
                    <CheckCircle2 className="w-4 h-4 text-green-500" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 text-amber-500" />
                  )}
                  <span className={`font-medium ${objection.handled ? "text-green-700" : "text-amber-700"}`}>
                    {objection.type}
                  </span>
                  <span className="text-xs text-gray-400">
                    {objection.handled ? "(resuelta)" : "(pendiente)"}
                  </span>
                </div>
                {!objection.handled && objection.suggestion && (
                  <p className="text-gray-600 text-xs ml-6 mt-1">
                    <span className="font-medium">Sugerencia:</span> {objection.suggestion}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Contact Info */}
      {(profile.email || profile.phone) && (
        <div className="p-4 border-b">
          <div className="space-y-2">
            {profile.email && (
              <div className="flex items-center gap-2 text-sm">
                <Mail className="w-4 h-4 text-gray-400" />
                <a href={`mailto:${profile.email}`} className="text-blue-600 hover:underline">
                  {profile.email}
                </a>
              </div>
            )}
            {profile.phone && (
              <div className="flex items-center gap-2 text-sm">
                <Phone className="w-4 h-4 text-gray-400" />
                <a href={`tel:${profile.phone}`} className="text-blue-600 hover:underline">
                  {profile.phone}
                </a>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="p-4">
        <div className="grid grid-cols-2 gap-4 text-center">
          <div>
            <div className="flex items-center justify-center gap-1 text-gray-400 mb-1">
              <MessageSquare className="w-4 h-4" />
            </div>
            <div className="text-lg font-semibold text-gray-900">{profile.total_messages}</div>
            <div className="text-xs text-gray-500">Mensajes</div>
          </div>
          <div>
            <div className="flex items-center justify-center gap-1 text-gray-400 mb-1">
              <Clock className="w-4 h-4" />
            </div>
            <div className="text-lg font-semibold text-gray-900">
              {profile.days_inactive === 0 ? "Hoy" : `${profile.days_inactive}d`}
            </div>
            <div className="text-xs text-gray-500">Último contacto</div>
          </div>
        </div>

        {/* Intent Score Bar */}
        <div className="mt-4">
          <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
            <span>Intención de compra</span>
            <span className="font-medium">{Math.round(profile.purchase_intent_score * 100)}%</span>
          </div>
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                profile.purchase_intent_score >= 0.7
                  ? "bg-red-500"
                  : profile.purchase_intent_score >= 0.4
                  ? "bg-yellow-500"
                  : "bg-gray-300"
              }`}
              style={{ width: `${profile.purchase_intent_score * 100}%` }}
            />
          </div>
        </div>
      </div>

      {/* Notes */}
      {profile.notes && (
        <div className="p-4 border-t bg-gray-50">
          <p className="text-xs text-gray-500 mb-1">Notas</p>
          <p className="text-sm text-gray-700">{profile.notes}</p>
        </div>
      )}
    </div>
  );
}

// Skeleton loader for loading state
function ProfilePanelSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-12 h-12 rounded-full bg-gray-200" />
        <div className="flex-1">
          <div className="h-4 bg-gray-200 rounded w-24 mb-2" />
          <div className="h-3 bg-gray-200 rounded w-16" />
        </div>
      </div>
      <div className="h-16 bg-gray-100 rounded mb-4" />
      <div className="flex gap-2 mb-4">
        <div className="h-6 bg-gray-200 rounded-full w-20" />
        <div className="h-6 bg-gray-200 rounded-full w-16" />
      </div>
      <div className="h-20 bg-gray-100 rounded mb-4" />
      <div className="grid grid-cols-2 gap-4">
        <div className="h-16 bg-gray-200 rounded" />
        <div className="h-16 bg-gray-200 rounded" />
      </div>
    </div>
  );
}

export default ProfilePanel;
