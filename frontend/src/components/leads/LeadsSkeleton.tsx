export function LeadsSkeleton() {
  return (
    <div className="space-y-4 p-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="flex flex-col items-center gap-2 p-3 rounded-xl border border-border/30 bg-card/30"
          >
            <div className="w-8 h-8 rounded-full bg-muted/40 animate-pulse" />
            <div className="w-10 h-6 rounded bg-muted/40 animate-pulse" />
            <div className="w-16 h-3 rounded bg-muted/30 animate-pulse" />
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-border/30 bg-card/30 overflow-hidden">
        <div className="h-10 border-b border-border/20 bg-muted/10" />
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-3 border-b border-border/10">
            <div className="w-9 h-9 rounded-full bg-muted/40 animate-pulse shrink-0" />
            <div className="flex-1 space-y-1.5">
              <div className="w-32 h-4 rounded bg-muted/40 animate-pulse" />
              <div className="w-20 h-3 rounded bg-muted/30 animate-pulse" />
            </div>
            <div className="hidden md:block w-40 h-3 rounded bg-muted/30 animate-pulse" />
            <div className="w-12 h-3 rounded bg-muted/30 animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}
