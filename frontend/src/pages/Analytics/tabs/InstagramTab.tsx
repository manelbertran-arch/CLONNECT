import { useInstagramAnalytics } from '@/hooks/useAnalytics';
import { Loader2, Image, Heart, MessageCircle, Clock, TrendingUp, Zap } from 'lucide-react';
import { cn } from '@/lib/utils';

interface InstagramTabProps {
  creatorId: string;
  period: string;
}

export function InstagramTab({ creatorId, period }: InstagramTabProps) {
  const { data, isLoading, isError } = useInstagramAnalytics(creatorId, period);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Image className="w-12 h-12 mx-auto mb-3 opacity-50" />
        <p>No hay datos de Instagram disponibles</p>
        <p className="text-sm mt-1">Conecta tu cuenta de Instagram para ver analytics</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Posts" value={data.total_posts} icon={Image} />
        <StatCard
          label="Mejor Hora"
          value={data.best_time?.hour || '--'}
          icon={Clock}
          subtitle={data.best_time?.day}
        />
        <StatCard label="Posts RAG" value={data.rag_documents_count || 0} icon={Zap} />
        <StatCard
          label="DMs Generados"
          value={data.post_to_dm_correlation?.reduce((sum: number, p: any) => sum + p.dms_generated, 0) || 0}
          icon={MessageCircle}
        />
      </div>

      {/* Content by Type */}
      {Object.keys(data.by_type || {}).length > 0 && (
        <div className="p-5 rounded-xl bg-card border border-border/50">
          <h3 className="text-sm font-medium mb-4">Engagement por Tipo de Contenido</h3>
          <div className="space-y-3">
            {Object.entries(data.by_type).map(([type, stats]: [string, any]) => (
              <div key={type} className="flex items-center gap-4">
                <span className="w-24 text-sm text-muted-foreground capitalize">{type.toLowerCase()}</span>
                <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full transition-all"
                    style={{ width: `${Math.min((stats.avg_engagement / 100) * 100, 100)}%` }}
                  />
                </div>
                <span className="text-sm font-medium w-20 text-right">
                  {stats.count} posts ({stats.avg_engagement.toFixed(0)} avg)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top Posts */}
      {data.top_posts?.length > 0 && (
        <div className="p-5 rounded-xl bg-card border border-border/50">
          <h3 className="text-sm font-medium mb-4">Top Posts por Engagement</h3>
          <div className="space-y-3">
            {data.top_posts.slice(0, 5).map((post: any, i: number) => (
              <div
                key={post.id}
                className="flex items-center gap-4 p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
              >
                <span className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-xs font-medium text-primary">
                  {i + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{post.caption || 'Sin caption'}</p>
                  <p className="text-xs text-muted-foreground">
                    {post.media_type} • {post.created_at ? new Date(post.created_at).toLocaleDateString() : 'N/A'}
                  </p>
                </div>
                <div className="flex items-center gap-4 text-sm">
                  <span className="flex items-center gap-1 text-rose-500">
                    <Heart className="w-3.5 h-3.5" /> {post.likes}
                  </span>
                  <span className="flex items-center gap-1 text-blue-500">
                    <MessageCircle className="w-3.5 h-3.5" /> {post.comments}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Post to DM Correlation */}
      {data.post_to_dm_correlation?.length > 0 && (
        <div className="p-5 rounded-xl bg-card border border-border/50">
          <h3 className="text-sm font-medium mb-4">Correlacion Post → DMs (48h)</h3>
          <div className="space-y-2">
            {data.post_to_dm_correlation.map((item: any, i: number) => (
              <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">{item.caption || 'Post'}</p>
                  <p className="text-xs text-muted-foreground">{item.media_type}</p>
                </div>
                <span className={cn(
                  "text-sm font-medium",
                  item.dms_generated > 10 ? "text-emerald-500" : "text-muted-foreground"
                )}>
                  {item.dms_generated} DMs
                </span>
              </div>
            ))}
          </div>
          {data.best_time?.insight && (
            <div className="mt-4 p-3 bg-primary/5 border border-primary/20 rounded-lg">
              <p className="text-sm text-primary">{data.best_time.insight}</p>
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {data.total_posts === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <Image className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>No hay posts en este periodo</p>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, icon: Icon, subtitle }: { label: string; value: string | number; icon: any; subtitle?: string }) {
  return (
    <div className="p-4 rounded-xl bg-card border border-border/50">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-muted-foreground uppercase tracking-wide">{label}</span>
        <Icon className="w-4 h-4 text-muted-foreground" />
      </div>
      <p className="text-2xl font-semibold">{value}</p>
      {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
    </div>
  );
}
