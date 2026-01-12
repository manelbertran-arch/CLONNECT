// Test page: Same as Inbox structure but minimal
// If this is SLOW: problem is in useConversations + DashboardLayout combo
// If this is FAST: problem is in Inbox.tsx specific code (useMemo, useEffect, etc)

import { useConversations, useArchivedConversations } from "@/hooks/useApi";

export default function HomeWithConversations() {
  console.log('[HOME+CONV] Component render start', Date.now());

  const { data, isLoading, error } = useConversations();
  const { data: archivedData, isLoading: archivedLoading } = useArchivedConversations();

  console.log('[HOME+CONV] After hooks:', {
    isLoading,
    archivedLoading,
    count: data?.conversations?.length,
    archivedCount: archivedData?.length,
    timestamp: Date.now()
  });

  if (isLoading) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-bold">Home + Conversations Test</h1>
        <p className="text-muted-foreground mt-2">Loading... (inside DashboardLayout)</p>
        <p className="text-xs text-muted-foreground">Check console for timing</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 text-red-500">
        <h1 className="text-2xl font-bold">Error</h1>
        <p>{String(error)}</p>
      </div>
    );
  }

  const conversations = data?.conversations || [];

  return (
    <div className="p-8 space-y-4">
      <h1 className="text-2xl font-bold">Home + Conversations Test</h1>
      <p className="text-success">✅ LOADED SUCCESSFULLY (inside DashboardLayout)</p>

      <div className="grid grid-cols-2 gap-4">
        <div className="p-4 bg-card rounded-lg border">
          <p className="text-muted-foreground">Conversations</p>
          <p className="text-3xl font-bold">{conversations.length}</p>
        </div>
        <div className="p-4 bg-card rounded-lg border">
          <p className="text-muted-foreground">Archived</p>
          <p className="text-3xl font-bold">{archivedData?.length || 0}</p>
        </div>
      </div>

      <div className="p-4 bg-muted/50 rounded-lg">
        <p className="text-sm text-muted-foreground">Timestamp: {Date.now()}</p>
        <p className="text-sm text-muted-foreground">
          If you see this quickly, the problem is in Inbox.tsx code, not the hooks.
        </p>
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer text-sm text-muted-foreground">
          Raw data preview (click to expand)
        </summary>
        <pre className="mt-2 p-4 bg-secondary rounded text-xs overflow-auto max-h-64">
          {JSON.stringify(conversations.slice(0, 3), null, 2)}
        </pre>
      </details>
    </div>
  );
}
