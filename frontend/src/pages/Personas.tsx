/**
 * Personas Page
 *
 * SPRINT4-T4.3: Audience segmentation and profile browser
 * Shows segments with counts, allows drilling into each segment
 * and viewing individual profiles
 */
import { useState, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { SegmentCard } from "@/components/SegmentCard";
import { ProfilePanel } from "@/components/ProfilePanel";
import {
  useAudienceSegments,
  useAudienceSegmentUsers,
} from "@/hooks/useAudience";
import { getCreatorId } from "@/services/api";
import type { AudienceProfile } from "@/services/api";
import {
  Search,
  ArrowLeft,
  MessageSquare,
  Clock,
  Users,
  X,
} from "lucide-react";

function LoadingSegments() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
        <Card key={i}>
          <CardContent className="p-4">
            <div className="flex items-center gap-3 mb-3">
              <Skeleton className="w-8 h-8 rounded" />
              <div className="flex-1">
                <Skeleton className="h-4 w-24 mb-1" />
                <Skeleton className="h-3 w-32" />
              </div>
            </div>
            <Skeleton className="h-8 w-12 mb-2" />
            <Skeleton className="h-4 w-20" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function LoadingUsers() {
  return (
    <div className="space-y-3">
      {[1, 2, 3, 4, 5].map((i) => (
        <Card key={i}>
          <CardContent className="p-4">
            <div className="flex justify-between">
              <div className="flex-1">
                <Skeleton className="h-5 w-32 mb-2" />
                <Skeleton className="h-4 w-24" />
              </div>
              <div className="text-right">
                <Skeleton className="h-5 w-16 mb-2" />
                <Skeleton className="h-4 w-20" />
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function UserCard({
  user,
  isSelected,
  onClick,
}: {
  user: AudienceProfile;
  isSelected: boolean;
  onClick: () => void;
}) {
  return (
    <Card
      onClick={onClick}
      className={`cursor-pointer transition-all hover:shadow-md ${
        isSelected ? "ring-2 ring-primary" : ""
      }`}
    >
      <CardContent className="p-4">
        <div className="flex justify-between items-start">
          <div className="min-w-0 flex-1">
            <div className="font-medium text-gray-900 truncate">
              {user.name || user.username || "Sin nombre"}
            </div>
            {user.username && (
              <div className="text-sm text-muted-foreground">@{user.username}</div>
            )}
          </div>
          <div className="text-right shrink-0 ml-4">
            {user.deal_value !== undefined && user.deal_value > 0 && (
              <div className="text-green-600 font-semibold">
                €{user.deal_value.toLocaleString()}
              </div>
            )}
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <MessageSquare className="w-3 h-3" />
              <span>{user.total_messages} msgs</span>
            </div>
          </div>
        </div>

        {/* Tags */}
        <div className="flex flex-wrap gap-1.5 mt-3">
          {user.segments?.slice(0, 3).map((seg) => (
            <Badge
              key={seg}
              variant="secondary"
              className="text-[10px] px-1.5 py-0"
            >
              {seg.replace(/_/g, " ")}
            </Badge>
          ))}
          {user.interests?.slice(0, 2).map((int) => (
            <Badge
              key={int}
              variant="outline"
              className="text-[10px] px-1.5 py-0 text-blue-600 border-blue-200 bg-blue-50"
            >
              {int}
            </Badge>
          ))}
        </div>

        {/* Last contact */}
        <div className="flex items-center gap-1 text-xs text-muted-foreground mt-3">
          <Clock className="w-3 h-3" />
          <span>
            Último contacto:{" "}
            {user.days_inactive === 0
              ? "Hoy"
              : `hace ${user.days_inactive} días`}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

export default function PersonasPage() {
  const creatorId = getCreatorId();
  const [searchParams, setSearchParams] = useSearchParams();

  // State
  const [selectedSegment, setSelectedSegment] = useState<string | null>(
    searchParams.get("segment") || null
  );
  const [selectedFollower, setSelectedFollower] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Data
  const { data: segments, isLoading: segmentsLoading } = useAudienceSegments(creatorId);
  const { data: segmentUsers, isLoading: usersLoading } = useAudienceSegmentUsers(
    selectedSegment || "",
    20,
    creatorId
  );

  // Total persons
  const totalPersons = useMemo(() => {
    return segments?.reduce((sum, s) => sum + s.count, 0) || 0;
  }, [segments]);

  // Filtered users based on search
  const filteredUsers = useMemo(() => {
    if (!segmentUsers || !searchQuery.trim()) return segmentUsers || [];

    const query = searchQuery.toLowerCase();
    return segmentUsers.filter((user) => {
      const name = (user.name || "").toLowerCase();
      const username = (user.username || "").toLowerCase();
      const interests = (user.interests || []).join(" ").toLowerCase();

      return (
        name.includes(query) ||
        username.includes(query) ||
        interests.includes(query)
      );
    });
  }, [segmentUsers, searchQuery]);

  // Handle segment selection with URL update
  const handleSelectSegment = (segment: string) => {
    setSelectedSegment(segment);
    setSelectedFollower(null);
    setSearchParams({ segment });
  };

  // Handle back to segments
  const handleBackToSegments = () => {
    setSelectedSegment(null);
    setSelectedFollower(null);
    setSearchParams({});
  };

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* Main Content */}
      <div className="flex-1 p-6 overflow-auto">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-2">
            <Users className="w-6 h-6 text-primary" />
            <h1 className="text-2xl font-bold tracking-tight">Personas</h1>
          </div>
          <p className="text-muted-foreground">
            {totalPersons} personas en tu audiencia
          </p>
        </div>

        {/* Search */}
        <div className="mb-6">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Buscar por nombre, interés..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        {/* Segments Grid View */}
        {!selectedSegment && (
          <>
            <h2 className="text-lg font-semibold mb-4">Segmentos</h2>
            {segmentsLoading ? (
              <LoadingSegments />
            ) : segments && segments.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {segments.map((segment) => (
                  <SegmentCard
                    key={segment.segment}
                    segment={segment.segment}
                    count={segment.count}
                    onClick={() => handleSelectSegment(segment.segment)}
                  />
                ))}
              </div>
            ) : (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                  <Users className="w-12 h-12 text-muted-foreground mb-4" />
                  <p className="text-muted-foreground">
                    No hay segmentos disponibles aún
                  </p>
                  <p className="text-xs text-muted-foreground mt-2">
                    Los segmentos aparecerán cuando tengas más conversaciones
                  </p>
                </CardContent>
              </Card>
            )}
          </>
        )}

        {/* Selected Segment Users */}
        {selectedSegment && (
          <>
            <div className="flex items-center gap-4 mb-6">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleBackToSegments}
                className="gap-2"
              >
                <ArrowLeft className="w-4 h-4" />
                Volver a segmentos
              </Button>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold capitalize">
                  {selectedSegment.replace(/_/g, " ")}
                </h2>
                <Badge variant="secondary">
                  {filteredUsers?.length || 0} personas
                </Badge>
              </div>
            </div>

            {/* Users List */}
            {usersLoading ? (
              <LoadingUsers />
            ) : filteredUsers && filteredUsers.length > 0 ? (
              <div className="space-y-3">
                {filteredUsers.map((user) => (
                  <UserCard
                    key={user.follower_id}
                    user={user}
                    isSelected={selectedFollower === user.follower_id}
                    onClick={() => setSelectedFollower(user.follower_id)}
                  />
                ))}
              </div>
            ) : (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                  <Users className="w-12 h-12 text-muted-foreground mb-4" />
                  <p className="text-muted-foreground">
                    {searchQuery
                      ? "No se encontraron personas con esos criterios"
                      : "No hay personas en este segmento"}
                  </p>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>

      {/* Profile Panel Sidebar */}
      {selectedFollower && (
        <div className="w-96 border-l bg-background overflow-auto shrink-0">
          <div className="p-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold">Perfil</h3>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setSelectedFollower(null)}
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
            <ProfilePanel
              creatorId={creatorId}
              followerId={selectedFollower}
              onClose={() => setSelectedFollower(null)}
              showCloseButton={false}
            />
          </div>
        </div>
      )}
    </div>
  );
}
