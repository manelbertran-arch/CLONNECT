// Minimal test to isolate Inbox slowness
// If this is slow: problem is in useConversations hook
// If this is fast: problem is in Inbox.tsx page code

import { useConversations } from "@/hooks/useApi";

export default function InboxTest() {
  const { data, isLoading, error } = useConversations();

  if (isLoading) {
    return (
      <div style={{ padding: '20px', fontFamily: 'monospace' }}>
        <h1>Inbox Test - Loading...</h1>
        <p>Check browser console for timing logs</p>
        <p>Timestamp: {Date.now()}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '20px', fontFamily: 'monospace', color: 'red' }}>
        <h1>Inbox Test - Error</h1>
        <p>Error: {String(error)}</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '20px', fontFamily: 'monospace' }}>
      <h1>Inbox Test - Loaded!</h1>
      <p><strong>Conversations loaded:</strong> {data?.conversations?.length || 0}</p>
      <p><strong>Timestamp:</strong> {Date.now()}</p>
      <hr />
      <details>
        <summary>Raw Data (click to expand)</summary>
        <pre style={{ fontSize: '12px', maxHeight: '400px', overflow: 'auto' }}>
          {JSON.stringify(data, null, 2)}
        </pre>
      </details>
    </div>
  );
}
