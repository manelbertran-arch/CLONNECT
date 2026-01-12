import { useConversations } from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Users } from "lucide-react";

export default function Leads() {
  const { data, isLoading, error } = useConversations();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (error) {
    return <div className="text-red-500">Error loading leads</div>;
  }

  const conversations = data?.conversations || [];

  // Simple categorization without complex useMemo
  const hot = conversations.filter((c: any) => c.purchase_intent >= 0.7);
  const warm = conversations.filter((c: any) => c.purchase_intent >= 0.3 && c.purchase_intent < 0.7);
  const cold = conversations.filter((c: any) => c.purchase_intent < 0.3);

  const LeadCard = ({ lead }: { lead: any }) => (
    <div className="p-3 bg-muted/50 rounded-lg mb-2">
      <div className="font-medium">{lead.username || lead.name || lead.follower_id}</div>
      <div className="text-sm text-muted-foreground">
        Score: {Math.round((lead.purchase_intent || 0) * 100)}%
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2">
        <Users className="h-6 w-6" />
        Leads ({conversations.length})
      </h1>

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-red-500">Hot ({hot.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {hot.map((lead: any) => (
              <LeadCard key={lead.follower_id} lead={lead} />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-yellow-500">Warm ({warm.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {warm.map((lead: any) => (
              <LeadCard key={lead.follower_id} lead={lead} />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-blue-500">Cold ({cold.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {cold.map((lead: any) => (
              <LeadCard key={lead.follower_id} lead={lead} />
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
