import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Check, Instagram, Send, MessageCircle } from 'lucide-react';
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

export default function ConexionesSection({ onBack }: Props) {
  const creatorId = CREATOR_ID;
  const queryClient = useQueryClient();
  const [configuring, setConfiguring] = useState<string | null>(null);
  const [formData, setFormData] = useState({ token: '', page_id: '', phone_id: '' });

  const { data: connections, isLoading } = useQuery({
    queryKey: ['connections', creatorId],
    queryFn: () => getConnections(creatorId),
  });

  const connectMutation = useMutation({
    mutationFn: ({
      platform,
      data,
    }: {
      platform: string;
      data: { token?: string; page_id?: string; phone_id?: string };
    }) => updateConnection(creatorId, platform, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connections', creatorId] });
      setConfiguring(null);
      setFormData({ token: '', page_id: '', phone_id: '' });
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
    if (platform === 'instagram') {
      handleStartOAuth('instagram');
    } else {
      setConfiguring(platform);
    }
  };

  const handleSave = (platform: string) => {
    connectMutation.mutate({ platform, data: formData });
  };

  const handleDisconnect = (platform: string) => {
    if (confirm(`¿Seguro que quieres desconectar ${platform}?`)) {
      disconnectMutation.mutate(platform);
    }
  };

  const platforms = [
    {
      id: 'instagram',
      name: 'Instagram',
      description: 'Responde DMs automáticamente',
      connected: connections?.instagram?.connected,
      username: connections?.instagram?.username,
      icon: Instagram,
      iconColor: 'text-pink-500',
      bgColor: 'bg-pink-500/20',
      useOAuth: true,
    },
    {
      id: 'telegram',
      name: 'Telegram',
      description: 'Bot de Telegram',
      connected: connections?.telegram?.connected,
      username: connections?.telegram?.username,
      icon: Send,
      iconColor: 'text-blue-500',
      bgColor: 'bg-blue-500/20',
      useOAuth: false,
      fields: ['token'],
    },
    {
      id: 'whatsapp',
      name: 'WhatsApp',
      description: 'WhatsApp Business API',
      connected: connections?.whatsapp?.connected,
      username: connections?.whatsapp?.username,
      icon: MessageCircle,
      iconColor: 'text-green-500',
      bgColor: 'bg-green-500/20',
      useOAuth: false,
      fields: ['token', 'phone_id'],
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={onBack}>
          <ArrowLeft className="text-gray-400" />
        </button>
        <h1 className="text-xl font-bold text-white">Conexiones</h1>
      </div>

      <p className="text-gray-400 text-sm">
        Conecta tus redes sociales para que tu clon pueda responder mensajes.
      </p>

      {isLoading ? (
        <p className="text-gray-500 text-center py-4">Cargando...</p>
      ) : (
        <div className="space-y-3">
          {platforms.map((platform) => (
            <div
              key={platform.id}
              className="bg-gray-900 rounded-xl p-4 border border-gray-800"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className={`w-10 h-10 rounded-lg ${platform.bgColor} flex items-center justify-center`}
                  >
                    <platform.icon className={platform.iconColor} size={20} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-white">{platform.name}</h3>
                      {platform.connected && (
                        <Check className="text-green-500" size={16} />
                      )}
                    </div>
                    <p className="text-sm text-gray-400">
                      {platform.connected && platform.username
                        ? `@${platform.username}`
                        : platform.description}
                    </p>
                  </div>
                </div>
                {platform.connected ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDisconnect(platform.id)}
                    className="border-red-500/50 text-red-500 hover:bg-red-500/10"
                  >
                    Desconectar
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    onClick={() => handleConnect(platform.id)}
                    className="bg-purple-500 hover:bg-purple-600"
                  >
                    Conectar
                  </Button>
                )}
              </div>

              {/* Configuration form */}
              {configuring === platform.id && !platform.useOAuth && (
                <div className="mt-4 pt-4 border-t border-gray-800 space-y-3">
                  {platform.fields?.includes('token') && (
                    <div>
                      <label className="text-sm text-gray-400 block mb-2">
                        {platform.id === 'telegram'
                          ? 'Bot Token (de @BotFather)'
                          : 'Access Token'}
                      </label>
                      <Input
                        type="password"
                        placeholder="Token..."
                        value={formData.token}
                        onChange={(e) =>
                          setFormData({ ...formData, token: e.target.value })
                        }
                        className="bg-gray-800 border-gray-700"
                      />
                    </div>
                  )}
                  {platform.fields?.includes('phone_id') && (
                    <div>
                      <label className="text-sm text-gray-400 block mb-2">
                        Phone Number ID
                      </label>
                      <Input
                        placeholder="Phone ID..."
                        value={formData.phone_id}
                        onChange={(e) =>
                          setFormData({ ...formData, phone_id: e.target.value })
                        }
                        className="bg-gray-800 border-gray-700"
                      />
                    </div>
                  )}
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setConfiguring(null);
                        setFormData({ token: '', page_id: '', phone_id: '' });
                      }}
                      className="border-gray-700"
                    >
                      Cancelar
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => handleSave(platform.id)}
                      disabled={!formData.token || connectMutation.isPending}
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
          💡 <strong className="text-white">Instagram</strong> requiere una cuenta
          Business o Creator conectada a una página de Facebook.
        </p>
      </div>
    </div>
  );
}
