/**
 * Tu Audiencia Page
 *
 * SPRINT4-T4.2: Aggregated audience intelligence page with 8 tabs
 * Shows what the audience talks about, their frustrations, competition mentions, etc.
 */
import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { TopicCard } from "@/components/TopicCard";
import {
  useAudienciaTopics,
  useAudienciaPassions,
  useAudienciaFrustrations,
  useAudienciaCompetition,
  useAudienciaTrends,
  useAudienciaContentRequests,
  useAudienciaPurchaseObjections,
  useAudienciaPerception,
} from "@/hooks/useAudiencia";
import {
  MessageCircle,
  Heart,
  AlertCircle,
  Users,
  TrendingUp,
  FileText,
  ShoppingCart,
  ThumbsUp,
} from "lucide-react";

const tabs = [
  { id: "topics", label: "De qué hablan", icon: MessageCircle, emoji: "💬" },
  { id: "passions", label: "Qué les apasiona", icon: Heart, emoji: "❤️" },
  { id: "frustrations", label: "Qué les frustra", icon: AlertCircle, emoji: "😤" },
  { id: "competition", label: "Competencia", icon: Users, emoji: "👀" },
  { id: "trends", label: "Tendencias", icon: TrendingUp, emoji: "📈" },
  { id: "content", label: "Contenido que piden", icon: FileText, emoji: "📝" },
  { id: "objections", label: "Por qué no compran", icon: ShoppingCart, emoji: "🛒" },
  { id: "perception", label: "Qué piensan de ti", icon: ThumbsUp, emoji: "🪞" },
];

function LoadingGrid() {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {[1, 2, 3, 4, 5, 6].map((i) => (
        <Card key={i}>
          <CardHeader className="pb-2">
            <Skeleton className="h-5 w-3/4" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-4 w-1/4 mb-3" />
            <Skeleton className="h-3 w-full mb-2" />
            <Skeleton className="h-3 w-2/3" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <Card className="col-span-full">
      <CardContent className="flex flex-col items-center justify-center py-12 text-center">
        <div className="text-4xl mb-4">🔍</div>
        <p className="text-muted-foreground">{message}</p>
        <p className="text-xs text-muted-foreground mt-2">
          Los datos aparecerán cuando tengas más conversaciones
        </p>
      </CardContent>
    </Card>
  );
}

function TopicsTab() {
  const { data, isLoading } = useAudienciaTopics();

  if (isLoading) return <LoadingGrid />;
  if (!data?.topics?.length) return <EmptyState message="No hay temas detectados aún" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Basado en</span>
        <Badge variant="secondary">{data.total_conversations} conversaciones</Badge>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {data.topics.map((topic, i) => (
          <TopicCard
            key={i}
            title={topic.topic}
            count={topic.count}
            percentage={topic.percentage}
            quotes={topic.quotes}
            users={topic.users}
            emoji="💬"
          />
        ))}
      </div>
    </div>
  );
}

function PassionsTab() {
  const { data, isLoading } = useAudienciaPassions();

  if (isLoading) return <LoadingGrid />;
  if (!data?.topics?.length) return <EmptyState message="No hay pasiones detectadas aún" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Temas con mayor engagement</span>
        <Badge variant="secondary">{data.total_conversations} conversaciones</Badge>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {data.topics.map((topic, i) => (
          <TopicCard
            key={i}
            title={topic.topic}
            count={topic.count}
            percentage={topic.percentage}
            quotes={topic.quotes}
            users={topic.users}
            emoji="❤️"
          />
        ))}
      </div>
    </div>
  );
}

function FrustrationsTab() {
  const { data, isLoading } = useAudienciaFrustrations();

  if (isLoading) return <LoadingGrid />;
  if (!data?.objections?.length) return <EmptyState message="No hay frustraciones detectadas aún" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Detectadas en</span>
        <Badge variant="secondary">{data.total_with_objections} conversaciones</Badge>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {data.objections.map((obj, i) => (
          <TopicCard
            key={i}
            title={obj.objection}
            count={obj.count}
            percentage={obj.percentage}
            quotes={obj.quotes}
            suggestion={obj.suggestion}
            emoji="😤"
          />
        ))}
      </div>
    </div>
  );
}

function CompetitionTab() {
  const { data, isLoading } = useAudienciaCompetition();

  if (isLoading) return <LoadingGrid />;
  if (!data?.competitors?.length) return <EmptyState message="No hay menciones de competencia aún" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Total de menciones:</span>
        <Badge variant="secondary">{data.total_mentions}</Badge>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {data.competitors.map((comp, i) => (
          <TopicCard
            key={i}
            title={comp.competitor}
            count={comp.count}
            quotes={comp.context}
            suggestion={comp.suggestion}
            sentiment={comp.sentiment}
            emoji="👀"
          />
        ))}
      </div>
    </div>
  );
}

function TrendsTab() {
  const { data, isLoading } = useAudienciaTrends();

  if (isLoading) return <LoadingGrid />;
  if (!data?.trends?.length) return <EmptyState message="No hay tendencias detectadas aún" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Período:</span>
        <Badge variant="secondary">{data.period}</Badge>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {data.trends.map((trend, i) => (
          <TopicCard
            key={i}
            title={trend.term}
            count={trend.count_this_week}
            quotes={trend.quotes}
            growth={trend.growth_percentage}
            emoji="📈"
          />
        ))}
      </div>
    </div>
  );
}

function ContentRequestsTab() {
  const { data, isLoading } = useAudienciaContentRequests();

  if (isLoading) return <LoadingGrid />;
  if (!data?.requests?.length) return <EmptyState message="No hay solicitudes de contenido aún" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Total de solicitudes:</span>
        <Badge variant="secondary">{data.total_requests}</Badge>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {data.requests.map((req, i) => (
          <Card key={i} className="hover:shadow-md transition-shadow">
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <span>📝</span>
                <span className="line-clamp-1">{req.topic}</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-1 text-sm">
                <span className="text-lg font-bold">{req.count}</span>
                <span className="text-muted-foreground">solicitudes</span>
              </div>
              {req.questions.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-muted-foreground">Preguntas frecuentes:</p>
                  {req.questions.slice(0, 3).map((q, j) => (
                    <p key={j} className="text-xs text-muted-foreground pl-2 border-l-2 border-muted">
                      {q}
                    </p>
                  ))}
                </div>
              )}
              {req.suggestion && (
                <div className="pt-2 border-t">
                  <p className="text-xs text-primary font-medium">
                    💡 {req.suggestion}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function PurchaseObjectionsTab() {
  const { data, isLoading } = useAudienciaPurchaseObjections();

  if (isLoading) return <LoadingGrid />;
  if (!data?.objections?.length) return <EmptyState message="No hay objeciones de compra detectadas aún" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Detectadas en</span>
        <Badge variant="secondary">{data.total_with_objections} conversaciones</Badge>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {data.objections.map((obj, i) => (
          <Card key={i} className="hover:shadow-md transition-shadow">
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <span>🛒</span>
                <span className="line-clamp-1">{obj.objection}</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-4 text-sm">
                <div className="flex items-center gap-1">
                  <span className="text-lg font-bold">{obj.count}</span>
                  <span className="text-muted-foreground">menciones</span>
                </div>
                {obj.percentage > 0 && (
                  <div className="text-muted-foreground">
                    ({obj.percentage.toFixed(1)}%)
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                <Badge variant="outline" className="text-[10px] text-green-500 border-green-500/20">
                  ✓ {obj.resolved_count} resueltas
                </Badge>
                <Badge variant="outline" className="text-[10px] text-amber-500 border-amber-500/20">
                  ⏳ {obj.pending_count} pendientes
                </Badge>
              </div>
              {obj.quotes.length > 0 && (
                <div className="space-y-1.5">
                  {obj.quotes.slice(0, 2).map((quote, j) => (
                    <p key={j} className="text-xs text-muted-foreground italic line-clamp-2 pl-2 border-l-2 border-muted">
                      "{quote}"
                    </p>
                  ))}
                </div>
              )}
              {obj.suggestion && (
                <div className="pt-2 border-t">
                  <p className="text-xs text-primary font-medium">
                    💡 {obj.suggestion}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function PerceptionTab() {
  const { data, isLoading } = useAudienciaPerception();

  if (isLoading) return <LoadingGrid />;
  if (!data?.perceptions?.length) return <EmptyState message="No hay percepciones detectadas aún" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Analizado en</span>
        <Badge variant="secondary">{data.total_analyzed} conversaciones</Badge>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {data.perceptions.map((perc, i) => (
          <Card key={i} className="hover:shadow-md transition-shadow">
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <span>🪞</span>
                <span className="line-clamp-1 capitalize">{perc.aspect}</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-4 text-sm">
                <div className="flex items-center gap-1 text-green-500">
                  <ThumbsUp className="w-4 h-4" />
                  <span className="font-bold">{perc.positive_count}</span>
                </div>
                <div className="flex items-center gap-1 text-red-500">
                  <ThumbsUp className="w-4 h-4 rotate-180" />
                  <span className="font-bold">{perc.negative_count}</span>
                </div>
              </div>
              {perc.quotes_positive.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[10px] font-medium text-green-500">Positivo:</p>
                  {perc.quotes_positive.slice(0, 1).map((q, j) => (
                    <p key={j} className="text-xs text-muted-foreground italic line-clamp-2 pl-2 border-l-2 border-green-500/30">
                      "{q}"
                    </p>
                  ))}
                </div>
              )}
              {perc.quotes_negative.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[10px] font-medium text-red-500">Negativo:</p>
                  {perc.quotes_negative.slice(0, 1).map((q, j) => (
                    <p key={j} className="text-xs text-muted-foreground italic line-clamp-2 pl-2 border-l-2 border-red-500/30">
                      "{q}"
                    </p>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default function TuAudiencia() {
  const [activeTab, setActiveTab] = useState("topics");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Tu Audiencia</h1>
        <p className="text-muted-foreground">
          Descubre qué piensan, sienten y necesitan tus seguidores
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="flex flex-wrap h-auto gap-1 bg-transparent p-0">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <TabsTrigger
                key={tab.id}
                value={tab.id}
                className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground px-3 py-2 gap-2"
              >
                <Icon className="w-4 h-4" />
                <span className="hidden sm:inline">{tab.label}</span>
                <span className="sm:hidden">{tab.emoji}</span>
              </TabsTrigger>
            );
          })}
        </TabsList>

        <TabsContent value="topics" className="mt-6">
          <TopicsTab />
        </TabsContent>

        <TabsContent value="passions" className="mt-6">
          <PassionsTab />
        </TabsContent>

        <TabsContent value="frustrations" className="mt-6">
          <FrustrationsTab />
        </TabsContent>

        <TabsContent value="competition" className="mt-6">
          <CompetitionTab />
        </TabsContent>

        <TabsContent value="trends" className="mt-6">
          <TrendsTab />
        </TabsContent>

        <TabsContent value="content" className="mt-6">
          <ContentRequestsTab />
        </TabsContent>

        <TabsContent value="objections" className="mt-6">
          <PurchaseObjectionsTab />
        </TabsContent>

        <TabsContent value="perception" className="mt-6">
          <PerceptionTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
