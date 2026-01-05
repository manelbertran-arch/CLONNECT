import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Save, Plus, Trash2 } from 'lucide-react';
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
  CREATOR_ID,
} from '@/services/api';

interface Props {
  onBack: () => void;
}

export default function TuClonSection({ onBack }: Props) {
  const creatorId = CREATOR_ID;
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<'personality' | 'knowledge'>('personality');
  const [personalityForm, setPersonalityForm] = useState({
    clone_name: '',
    clone_tone: '',
    use_emojis: true,
    show_empathy: true,
  });
  const [newFaq, setNewFaq] = useState({ question: '', answer: '' });
  const [isAddingFaq, setIsAddingFaq] = useState(false);

  const { data: configData } = useQuery({
    queryKey: ['config', creatorId],
    queryFn: () => getCreatorConfig(creatorId),
  });

  const { data: knowledgeData, isLoading: isLoadingKnowledge } = useQuery({
    queryKey: ['knowledge', creatorId],
    queryFn: () => getKnowledge(creatorId),
  });

  const updateConfigMutation = useMutation({
    mutationFn: (config: any) => updateCreatorConfig(creatorId, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config', creatorId] });
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

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={onBack}>
          <ArrowLeft className="text-gray-400" />
        </button>
        <h1 className="text-xl font-bold text-white">Tu Clon</h1>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        <button
          onClick={() => setActiveTab('personality')}
          className={`px-4 py-2 rounded-lg text-sm transition-colors ${
            activeTab === 'personality'
              ? 'bg-purple-500 text-white'
              : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}
        >
          Personalidad
        </button>
        <button
          onClick={() => setActiveTab('knowledge')}
          className={`px-4 py-2 rounded-lg text-sm transition-colors ${
            activeTab === 'knowledge'
              ? 'bg-purple-500 text-white'
              : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}
        >
          Conocimiento
        </button>
      </div>

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
              className="bg-gray-900 border-gray-800"
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
            <div className="flex items-center justify-between p-3 bg-gray-900 rounded-lg">
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

            <div className="flex items-center justify-between p-3 bg-gray-900 rounded-lg">
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
            className="w-full bg-purple-500 hover:bg-purple-600"
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
            <p className="text-gray-500 text-center py-4">Cargando...</p>
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
                          className="p-2 text-gray-400 hover:text-red-500 transition-colors"
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
                      className="bg-gray-800 border-gray-700"
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
                      className="flex-1 border-gray-700"
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
                      className="flex-1 bg-purple-500 hover:bg-purple-600"
                    >
                      Añadir
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  onClick={() => setIsAddingFaq(true)}
                  className="w-full bg-purple-500 hover:bg-purple-600"
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
