import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Check, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  getConnections,
  updateConnection,
  disconnectPlatform,
  startOAuth,
  CREATOR_ID,
} from '@/services/api';

interface Props {
  onBack: () => void;
}

export default function PagosSection({ onBack }: Props) {
  const creatorId = CREATOR_ID;
  const queryClient = useQueryClient();
  const [configuring, setConfiguring] = useState<string | null>(null);
  const [token, setToken] = useState('');

  const { data: connections, isLoading } = useQuery({
    queryKey: ['connections', creatorId],
    queryFn: () => getConnections(creatorId),
  });

  const connectMutation = useMutation({
    mutationFn: ({ platform, data }: { platform: string; data: { token?: string } }) =>
      updateConnection(creatorId, platform, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connections', creatorId] });
      setConfiguring(null);
      setToken('');
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: (platform: string) => disconnectPlatform(creatorId, platform),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connections', creatorId] });
    },
  });

  const handleStartOAuth = async (platform: string) => {
    try {
      const { auth_url } = await startOAuth(platform, creatorId);
      window.open(auth_url, '_blank');
    } catch (error) {
      console.error('OAuth error:', error);
    }
  };

  const handleConnect = (platform: string) => {
    if (platform === 'stripe') {
      handleStartOAuth('stripe');
    } else {
      setConfiguring(platform);
    }
  };

  const handleSaveToken = (platform: string) => {
    connectMutation.mutate({ platform, data: { token } });
  };

  const handleDisconnect = (platform: string) => {
    if (confirm(`¿Seguro que quieres desconectar ${platform}?`)) {
      disconnectMutation.mutate(platform);
    }
  };

  const paymentMethods = [
    {
      id: 'stripe',
      name: 'Stripe',
      description: 'Pagos con tarjeta de crédito',
      connected: connections?.stripe?.connected,
      icon: '💳',
      useOAuth: true,
    },
    {
      id: 'paypal',
      name: 'PayPal',
      description: 'Pagos con PayPal',
      connected: connections?.paypal?.connected,
      icon: '🅿️',
      useOAuth: false,
    },
    {
      id: 'hotmart',
      name: 'Hotmart',
      description: 'Productos digitales',
      connected: connections?.hotmart?.connected,
      icon: '🔥',
      useOAuth: false,
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={onBack}>
          <ArrowLeft className="text-gray-400" />
        </button>
        <h1 className="text-xl font-bold text-white">Métodos de pago</h1>
      </div>

      <p className="text-gray-400 text-sm">
        Conecta tus pasarelas de pago para que tu clon pueda enviar links de compra.
      </p>

      {isLoading ? (
        <p className="text-gray-500 text-center py-4">Cargando...</p>
      ) : (
        <div className="space-y-3">
          {paymentMethods.map((method) => (
            <div
              key={method.id}
              className="bg-gray-900 rounded-xl p-4 border border-gray-800"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{method.icon}</span>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-white">{method.name}</h3>
                      {method.connected && (
                        <Check className="text-green-500" size={16} />
                      )}
                    </div>
                    <p className="text-sm text-gray-400">{method.description}</p>
                  </div>
                </div>
                {method.connected ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDisconnect(method.id)}
                    className="border-red-500/50 text-red-500 hover:bg-red-500/10"
                  >
                    Desconectar
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    onClick={() => handleConnect(method.id)}
                    className="bg-purple-500 hover:bg-purple-600"
                  >
                    Conectar
                  </Button>
                )}
              </div>

              {/* Configuration form */}
              {configuring === method.id && !method.useOAuth && (
                <div className="mt-4 pt-4 border-t border-gray-800 space-y-3">
                  <div>
                    <label className="text-sm text-gray-400 block mb-2">
                      API Key / Token
                    </label>
                    <Input
                      type="password"
                      placeholder="Introduce tu API key..."
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      className="bg-gray-800 border-gray-700"
                    />
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setConfiguring(null);
                        setToken('');
                      }}
                      className="border-gray-700"
                    >
                      Cancelar
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => handleSaveToken(method.id)}
                      disabled={!token || connectMutation.isPending}
                      className="bg-purple-500 hover:bg-purple-600"
                    >
                      Guardar
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
        <p className="text-sm text-gray-400">
          💡 <strong className="text-white">Tip:</strong> Stripe es el método más
          recomendado para cobros con tarjeta. Hotmart es ideal si vendes cursos o
          productos digitales.
        </p>
      </div>
    </div>
  );
}
