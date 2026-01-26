import { useReports, useGenerateReport } from '@/hooks/useAnalytics';
import { Loader2, FileText, Calendar, Eye, Download, RefreshCw, CheckCircle, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useState } from 'react';

interface ReportsTabProps {
  creatorId: string;
}

export function ReportsTab({ creatorId }: ReportsTabProps) {
  const { data, isLoading, isError, refetch } = useReports(creatorId);
  const generateReport = useGenerateReport(creatorId);
  const [selectedReport, setSelectedReport] = useState<any>(null);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
        <p>Error al cargar informes</p>
      </div>
    );
  }

  const handleGenerate = async () => {
    try {
      await generateReport.mutateAsync();
      refetch();
    } catch (error) {
      console.error('Error generating report:', error);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium">Informes Automaticos</h3>
          <p className="text-sm text-muted-foreground">Informes semanales generados por IA</p>
        </div>
        <Button onClick={handleGenerate} disabled={generateReport.isPending}>
          {generateReport.isPending ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Generando...
            </>
          ) : (
            <>
              <RefreshCw className="w-4 h-4 mr-2" />
              Generar Informe
            </>
          )}
        </Button>
      </div>

      {/* Reports List */}
      {data?.reports?.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Reports List */}
          <div className="lg:col-span-1 space-y-3">
            {data.reports.map((report: any) => (
              <div
                key={report.id}
                onClick={() => setSelectedReport(report)}
                className={cn(
                  "p-4 rounded-xl border cursor-pointer transition-all",
                  selectedReport?.id === report.id
                    ? "bg-primary/5 border-primary/30"
                    : "bg-card border-border/50 hover:border-border"
                )}
              >
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "w-10 h-10 rounded-lg flex items-center justify-center",
                    selectedReport?.id === report.id ? "bg-primary/10" : "bg-muted"
                  )}>
                    <FileText className={cn(
                      "w-5 h-5",
                      selectedReport?.id === report.id ? "text-primary" : "text-muted-foreground"
                    )} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">Informe Semanal</p>
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {report.week_start ? new Date(report.week_start).toLocaleDateString() : 'N/A'} -
                      {report.week_end ? new Date(report.week_end).toLocaleDateString() : 'N/A'}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Selected Report Detail */}
          <div className="lg:col-span-2">
            {selectedReport ? (
              <div className="p-6 rounded-xl bg-card border border-border/50 space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-medium">Informe Semanal</h3>
                    <p className="text-sm text-muted-foreground">
                      {selectedReport.week_start ? new Date(selectedReport.week_start).toLocaleDateString() : ''} -
                      {selectedReport.week_end ? new Date(selectedReport.week_end).toLocaleDateString() : ''}
                    </p>
                  </div>
                  <Button variant="outline" size="sm">
                    <Download className="w-4 h-4 mr-2" />
                    Exportar PDF
                  </Button>
                </div>

                {/* Executive Summary */}
                {selectedReport.executive_summary && (
                  <div className="p-4 bg-muted/30 rounded-lg">
                    <h4 className="text-sm font-medium mb-2">Resumen Ejecutivo</h4>
                    <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                      {selectedReport.executive_summary}
                    </p>
                  </div>
                )}

                {/* Key Metrics */}
                {selectedReport.metrics_summary && (
                  <div>
                    <h4 className="text-sm font-medium mb-3">Metricas Clave</h4>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      {Object.entries(selectedReport.metrics_summary).slice(0, 8).map(([key, value]: [string, any]) => (
                        <div key={key} className="p-3 bg-muted/30 rounded-lg">
                          <p className="text-xs text-muted-foreground capitalize">{key.replace(/_/g, ' ')}</p>
                          <p className="text-lg font-semibold">
                            {typeof value === 'number' ? value.toLocaleString() : String(value)}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Key Wins */}
                {selectedReport.key_wins?.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
                      <CheckCircle className="w-4 h-4 text-emerald-500" />
                      Victorias
                    </h4>
                    <ul className="space-y-2">
                      {selectedReport.key_wins.map((win: string, i: number) => (
                        <li key={i} className="flex items-start gap-2 text-sm">
                          <span className="text-emerald-500">•</span>
                          {win}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Areas to Improve */}
                {selectedReport.areas_to_improve?.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 text-amber-500" />
                      Areas de Mejora
                    </h4>
                    <ul className="space-y-2">
                      {selectedReport.areas_to_improve.map((area: string, i: number) => (
                        <li key={i} className="flex items-start gap-2 text-sm">
                          <span className="text-amber-500">•</span>
                          {area}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <p className="text-xs text-muted-foreground">
                  Generado: {selectedReport.created_at ? new Date(selectedReport.created_at).toLocaleString() : 'N/A'}
                </p>
              </div>
            ) : (
              <div className="p-6 rounded-xl bg-card border border-border/50 text-center">
                <FileText className="w-12 h-12 mx-auto mb-3 text-muted-foreground opacity-50" />
                <p className="text-muted-foreground">Selecciona un informe para ver los detalles</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>No hay informes generados</p>
          <p className="text-sm mt-1">Genera tu primer informe haciendo click en el boton</p>
          <Button onClick={handleGenerate} disabled={generateReport.isPending} className="mt-4">
            {generateReport.isPending ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Generando...
              </>
            ) : (
              <>
                <RefreshCw className="w-4 h-4 mr-2" />
                Generar Primer Informe
              </>
            )}
          </Button>
        </div>
      )}
    </div>
  );
}
