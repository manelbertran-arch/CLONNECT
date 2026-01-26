import { useState } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { RefreshCw, Download, FileText, Loader2, AlertCircle } from 'lucide-react';

import { SummaryKPIs } from './components/SummaryKPIs';
import { InstagramTab } from './tabs/InstagramTab';
import { AudienceTab } from './tabs/AudienceTab';
import { SalesTab } from './tabs/SalesTab';
import { PredictionsTab } from './tabs/PredictionsTab';
import { ReportsTab } from './tabs/ReportsTab';

import { useAnalyticsSummary } from '@/hooks/useAnalytics';
import { getCreatorId } from '@/services/api';

export default function AnalyticsDashboard() {
  const creatorId = getCreatorId();
  const [period, setPeriod] = useState('30d');
  const [activeTab, setActiveTab] = useState('audience');

  const { data: summary, isLoading, isError, error, refetch } = useAnalyticsSummary(creatorId, period);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground mb-1">Business Intelligence</p>
          <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        </div>

        <div className="flex items-center gap-3">
          {/* Period Selector */}
          <div className="flex bg-muted/50 rounded-lg p-1">
            {[
              { value: 'today', label: 'Hoy' },
              { value: '7d', label: '7d' },
              { value: '30d', label: '30d' },
              { value: '90d', label: '90d' },
              { value: 'year', label: 'Año' }
            ].map((p) => (
              <button
                key={p.value}
                onClick={() => setPeriod(p.value)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                  period === p.value
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Actualizar
          </Button>

          <Button variant="outline" size="sm">
            <Download className="w-4 h-4 mr-2" />
            Exportar
          </Button>
        </div>
      </div>

      {/* Loading State */}
      {isLoading && !summary && (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Error State */}
      {isError && (
        <div className="flex flex-col items-center justify-center h-32 gap-2">
          <AlertCircle className="w-6 h-6 text-destructive" />
          <p className="text-sm text-muted-foreground">{(error as Error)?.message || 'Error al cargar datos'}</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>Reintentar</Button>
        </div>
      )}

      {/* Content */}
      {!isLoading && !isError && (
        <>
          {/* KPIs Summary */}
          <SummaryKPIs data={summary?.kpis} isLoading={isLoading} />

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-6">
            <TabsList className="bg-muted/50 p-1 h-auto">
              <TabsTrigger value="instagram" className="data-[state=active]:bg-background px-4 py-2">
                📸 Instagram
              </TabsTrigger>
              <TabsTrigger value="audience" className="data-[state=active]:bg-background px-4 py-2">
                💬 Audiencia
              </TabsTrigger>
              <TabsTrigger value="sales" className="data-[state=active]:bg-background px-4 py-2">
                🛒 Ventas
              </TabsTrigger>
              <TabsTrigger value="predictions" className="data-[state=active]:bg-background px-4 py-2">
                🔮 Predicciones
              </TabsTrigger>
              <TabsTrigger value="reports" className="data-[state=active]:bg-background px-4 py-2">
                📋 Informes
              </TabsTrigger>
            </TabsList>

            <div className="mt-6">
              <TabsContent value="instagram" className="m-0">
                <InstagramTab creatorId={creatorId} period={period} />
              </TabsContent>

              <TabsContent value="audience" className="m-0">
                <AudienceTab creatorId={creatorId} period={period} />
              </TabsContent>

              <TabsContent value="sales" className="m-0">
                <SalesTab creatorId={creatorId} period={period} />
              </TabsContent>

              <TabsContent value="predictions" className="m-0">
                <PredictionsTab creatorId={creatorId} />
              </TabsContent>

              <TabsContent value="reports" className="m-0">
                <ReportsTab creatorId={creatorId} />
              </TabsContent>
            </div>
          </Tabs>
        </>
      )}
    </div>
  );
}
