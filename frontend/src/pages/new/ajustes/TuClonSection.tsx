import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Save, Plus, Trash2, RefreshCw, Send, Loader2, MessageSquare } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  getCreatorConfig,
  updateCreatorConfig,
  getKnowledge,
  addFAQ,
  deleteFAQ,
  getToneProfile,
  regenerateToneProfile,
  getContentStats,
  testClone,
  CREATOR_ID,
  type ToneProfile,
  type ContentStats,
} from '@/services/api';

interface Props {
  onBack: () => void;
}

export default function TuClonSection({ onBack }: Props) {
  const creatorId = CREATOR_ID;
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<'overview' | 'personality' | 'knowledge'>('overview');
  const [personalityForm, setPersonalityForm] = useState({
    clone_name: '',
    clone_tone: '',
    use_emojis: true,
    show_empathy: true,
  });
  const [newFaq, setNewFaq] = useState({ question: '', answer: '' });
  const [isAddingFaq, setIsAddingFaq] = useState(false);
  const [testMessage, setTestMessage] = useState('');
  const [testResponse, setTestResponse] = useState<string | null>(null);

  const { data: configData } = useQuery({
    queryKey: ['config', creatorId],
    queryFn: () => getCreatorConfig(creatorId),
  });

  const { data: knowledgeData, isLoading: isLoadingKnowledge } = useQuery({
    queryKey: ['knowledge', creatorId],
    queryFn: () => getKnowledge(creatorId),
  });

  const { data: toneData, isLoading: isLoadingTone } = useQuery({
    queryKey: ['toneProfile', creatorId],
    queryFn: () => getToneProfile(creatorId),
  });

  const { data: statsData, isLoading: isLoadingStats } = useQuery({
    queryKey: ['contentStats', creatorId],
    queryFn: () => getContentStats(creatorId),
  });

  const updateConfigMutation = useMutation({
    mutationFn: (config: any) => updateCreatorConfig(creatorId, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config', creatorId] });
    },
  });

  const regenerateToneMutation = useMutation({
    mutationFn: () => regenerateToneProfile(creatorId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['toneProfile', creatorId] });
    },
  });

  const testCloneMutation = useMutation({
    mutationFn: (message: string) => testClone(creatorId, message),
    onSuccess: (data) => {
      setTestResponse(data.response);
    },
  });

  const addFaqMutation = useMutation({
    mutationFn: ({ question, answer }: { question: string; answer: string }) =>
      addFAQ(creatorId, question, answer),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge', creatorId] });
      setNewFaq({ question: '', answer: '' });
      setIsAddingFaq(false);
    },
  });

  const deleteFaqMutation = useMutation({
    mutationFn: (id: string) => deleteFAQ(creatorId, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge', creatorId] });
    },
  });

  const config = configData?.config;
  const faqs = knowledgeData?.faqs || [];
  const toneProfile = toneData?.tone_profile;
  const contentStats = statsData?.stats;

  useEffect(() => {
    if (config) {
      setPersonalityForm({
        clone_name: config.clone_name || '',
        clone_tone: config.clone_tone || '',
        use_emojis: config.personality?.use_emojis ?? true,
        show_empathy: config.personality?.show_empathy ?? true,
      });
    }
  }, [config]);

  const handleSavePersonality = () => {
    updateConfigMutation.mutate({
      clone_name: personalityForm.clone_name,
      clone_tone: personalityForm.clone_tone,
      personality: {
        ...config?.personality,
        use_emojis: personalityForm.use_emojis,
        show_empathy: personalityForm.show_empathy,
      },
    });
  };

  const handleAddFaq = () => {
    if (newFaq.question && newFaq.answer) {
      addFaqMutation.mutate(newFaq);
    }
  };

  const handleDeleteFaq = (id: string) => {
    if (confirm('¿Seguro que quieres eliminar esta FAQ?')) {
      deleteFaqMutation.mutate(id);
    }
  };

  const handleTestClone = () => {
    if (testMessage.trim()) {
      testCloneMutation.mutate(testMessage);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={onBack} className="p-2 -ml-2">
          <ArrowLeft className="text-gray-400" />
        </button>
        <h1 className="text-xl font-bold text-white">Tu Clon</h1>
      </div>

      {/* Tabs - Mobile optimized with scroll */}
      <div className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1">
        {[
          { id: 'overview', label: 'Resumen' },
          { id: 'personality', label: 'Personalidad' },
          { id: 'knowledge', label: 'Conocimiento' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`px-4 py-2 rounded-lg text-sm whitespace-nowrap transition-colors min-h-[44px] ${
              activeTab === tab.id
                ? 'bg-purple-500 text-white'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-4">
          {/* Tone Profile Card */}
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <span className="text-2xl">🎭</span>
                <h3 className="font-medium text-white">Perfil de Tono</h3>
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => regenerateToneMutation.mutate()}
                disabled={regenerateToneMutation.isPending}
                className="text-purple-400 hover:text-purple-300 min-h-[44px]"
              >
                {regenerateToneMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <RefreshCw className="w-4 h-4" />
                )}
              </Button>
            </div>

            {isLoadingTone ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 text-purple-500 animate-spin" />
              </div>
            ) : toneProfile ? (
              <div className="space-y-4">
                {/* Tone summary */}
                <p className="text-sm text-gray-300 bg-gray-800 rounded-lg p-3">
                  {toneProfile.summary}
                </p>

                {/* Tone bars */}
                <div className="space-y-3">
                  <ToneBar label="Formalidad" value={toneProfile.formality} color="bg-blue-500" />
                  <ToneBar label="Energía" value={toneProfile.energy} color="bg-yellow-500" />
                  <ToneBar label="Calidez" value={toneProfile.warmth} color="bg-pink-500" />
                  <ToneBar label="Uso de emojis" value={toneProfile.emoji_usage} color="bg-green-500" />
                </div>
              </div>
            ) : (
              <div className="text-center py-6">
                <p className="text-gray-500 text-sm mb-4">
                  No hay perfil de tono generado
                </p>
                <Button
                  onClick={() => regenerateToneMutation.mutate()}
                  disabled={regenerateToneMutation.isPending}
                  className="bg-purple-500 hover:bg-purple-600 min-h-[44px]"
                >
                  {regenerateToneMutation.isPending ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Generando...
                    </>
                  ) : (
                    'Generar perfil de tono'
                  )}
                </Button>
              </div>
            )}
          </div>

          {/* Content Stats Card */}
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-2xl">📚</span>
              <h3 className="font-medium text-white">Contenido Indexado</h3>
            </div>

            {isLoadingStats ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 text-purple-500 animate-spin" />
              </div>
            ) : contentStats ? (
              <div className="grid grid-cols-2 gap-3">
                <StatBox value={contentStats.posts_count} label="Posts" icon="📸" />
                <StatBox value={contentStats.videos_count} label="Videos" icon="🎬" />
                <StatBox value={contentStats.pdfs_count} label="PDFs" icon="📄" />
                <StatBox value={contentStats.audios_count} label="Audios" icon="🎙️" />
              </div>
            ) : (
              <p className="text-gray-500 text-sm text-center py-4">
                Sin estadísticas disponibles
              </p>
            )}
          </div>

          {/* Test Clone Card */}
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-2xl">💬</span>
              <h3 className="font-medium text-white">Probar tu Clon</h3>
            </div>

            <div className="space-y-3">
              <div className="flex gap-2">
                <Input
                  placeholder="Escribe un mensaje de prueba..."
                  value={testMessage}
                  onChange={(e) => setTestMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleTestClone();
                    }
                  }}
                  className="bg-gray-800 border-gray-700 flex-1 min-h-[44px]"
                />
                <Button
                  onClick={handleTestClone}
                  disabled={!testMessage.trim() || testCloneMutation.isPending}
                  className="bg-purple-500 hover:bg-purple-600 min-h-[44px] min-w-[44px]"
                >
                  {testCloneMutation.isPending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                </Button>
              </div>

              {testResponse && (
                <div className="bg-gray-800 rounded-lg p-3 border border-gray-700">
                  <div className="flex items-start gap-2">
                    <MessageSquare className="w-4 h-4 text-purple-400 mt-0.5 flex-shrink-0" />
                    <p className="text-sm text-gray-300">{testResponse}</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Personality Tab */}
      {activeTab === 'personality' && (
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-2">
              Nombre del clon
            </label>
            <Input
              placeholder="Ej: Alex (asistente de Manel)"
              value={personalityForm.clone_name}
              onChange={(e) =>
                setPersonalityForm({ ...personalityForm, clone_name: e.target.value })
              }
              className="bg-gray-900 border-gray-800 min-h-[44px]"
            />
          </div>

          <div>
            <label className="text-sm text-gray-400 block mb-2">
              Tono de comunicación
            </label>
            <Textarea
              placeholder="Ej: Amigable, profesional, cercano pero directo..."
              value={personalityForm.clone_tone}
              onChange={(e) =>
                setPersonalityForm({ ...personalityForm, clone_tone: e.target.value })
              }
              className="bg-gray-900 border-gray-800 min-h-[100px]"
            />
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-gray-900 rounded-lg min-h-[64px]">
              <div>
                <p className="text-white">Usar emojis</p>
                <p className="text-sm text-gray-400">
                  El clon usará emojis en sus respuestas
                </p>
              </div>
              <Switch
                checked={personalityForm.use_emojis}
                onCheckedChange={(checked) =>
                  setPersonalityForm({ ...personalityForm, use_emojis: checked })
                }
              />
            </div>

            <div className="flex items-center justify-between p-3 bg-gray-900 rounded-lg min-h-[64px]">
              <div>
                <p className="text-white">Mostrar empatía</p>
                <p className="text-sm text-gray-400">
                  Respuestas más empáticas y personales
                </p>
              </div>
              <Switch
                checked={personalityForm.show_empathy}
                onCheckedChange={(checked) =>
                  setPersonalityForm({ ...personalityForm, show_empathy: checked })
                }
              />
            </div>
          </div>

          <Button
            onClick={handleSavePersonality}
            disabled={updateConfigMutation.isPending}
            className="w-full bg-purple-500 hover:bg-purple-600 min-h-[48px]"
          >
            <Save className="mr-2" size={18} />
            Guardar cambios
          </Button>
        </div>
      )}

      {/* Knowledge Tab */}
      {activeTab === 'knowledge' && (
        <div className="space-y-4">
          <p className="text-gray-400 text-sm">
            Preguntas frecuentes que tu clon puede responder automáticamente.
          </p>

          {isLoadingKnowledge ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 text-purple-500 animate-spin" />
            </div>
          ) : (
            <>
              {/* FAQ List */}
              <div className="space-y-3">
                {faqs.length === 0 ? (
                  <p className="text-gray-500 text-center py-4">
                    No hay FAQs configuradas
                  </p>
                ) : (
                  faqs.map((faq) => (
                    <div
                      key={faq.id}
                      className="bg-gray-900 rounded-xl p-4 border border-gray-800"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1">
                          <p className="font-medium text-white">{faq.question}</p>
                          <p className="text-sm text-gray-400 mt-1">{faq.answer}</p>
                        </div>
                        <button
                          onClick={() => handleDeleteFaq(faq.id)}
                          className="p-2 text-gray-400 hover:text-red-500 transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
                        >
                          <Trash2 size={18} />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* Add FAQ Form */}
              {isAddingFaq ? (
                <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 space-y-3">
                  <div>
                    <label className="text-sm text-gray-400 block mb-2">
                      Pregunta
                    </label>
                    <Input
                      placeholder="¿Cuánto cuesta el curso?"
                      value={newFaq.question}
                      onChange={(e) =>
                        setNewFaq({ ...newFaq, question: e.target.value })
                      }
                      className="bg-gray-800 border-gray-700 min-h-[44px]"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-400 block mb-2">
                      Respuesta
                    </label>
                    <Textarea
                      placeholder="El curso tiene un precio de..."
                      value={newFaq.answer}
                      onChange={(e) =>
                        setNewFaq({ ...newFaq, answer: e.target.value })
                      }
                      className="bg-gray-800 border-gray-700 min-h-[80px]"
                    />
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      onClick={() => {
                        setIsAddingFaq(false);
                        setNewFaq({ question: '', answer: '' });
                      }}
                      className="flex-1 border-gray-700 min-h-[48px]"
                    >
                      Cancelar
                    </Button>
                    <Button
                      onClick={handleAddFaq}
                      disabled={
                        !newFaq.question ||
                        !newFaq.answer ||
                        addFaqMutation.isPending
                      }
                      className="flex-1 bg-purple-500 hover:bg-purple-600 min-h-[48px]"
                    >
                      Añadir
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  onClick={() => setIsAddingFaq(true)}
                  className="w-full bg-purple-500 hover:bg-purple-600 min-h-[48px]"
                >
                  <Plus className="mr-2" size={18} />
                  Añadir FAQ
                </Button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// Helper components
function ToneBar({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span className="text-gray-400">{label}</span>
        <span className="text-gray-300">{value}%</span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full ${color} rounded-full transition-all duration-500`}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

function StatBox({
  value,
  label,
  icon,
}: {
  value: number;
  label: string;
  icon: string;
}) {
  return (
    <div className="bg-gray-800 rounded-lg p-3 text-center">
      <div className="text-xl mb-1">{icon}</div>
      <div className="text-xl font-bold text-white">{value}</div>
      <div className="text-xs text-gray-400">{label}</div>
    </div>
  );
}
