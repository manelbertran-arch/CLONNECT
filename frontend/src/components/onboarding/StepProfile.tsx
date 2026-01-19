import { useState } from 'react';
import { ArrowLeft, ArrowRight, User, MessageSquare } from 'lucide-react';
import { useOnboarding, ProfileData } from './OnboardingContext';

type ToneOption = 'formal' | 'casual' | 'friendly';

const TONE_OPTIONS: { value: ToneOption; label: string; description: string; emoji: string }[] = [
  { value: 'formal', label: 'Formal', description: 'Profesional y serio', emoji: '👔' },
  { value: 'casual', label: 'Casual', description: 'Relajado y natural', emoji: '😎' },
  { value: 'friendly', label: 'Amigable', description: 'Cercano y cálido', emoji: '🤗' },
];

export function StepProfile() {
  const { nextStep, prevStep, profile, setProfile } = useOnboarding();

  const [localProfile, setLocalProfile] = useState<ProfileData>(profile);
  const [errors, setErrors] = useState<{ businessName?: string; description?: string }>({});

  const handleChange = (field: keyof ProfileData, value: string) => {
    setLocalProfile(prev => ({ ...prev, [field]: value }));
    // Clear error when user types
    if (errors[field as keyof typeof errors]) {
      setErrors(prev => ({ ...prev, [field]: undefined }));
    }
  };

  const handleToneSelect = (tone: ToneOption) => {
    setLocalProfile(prev => ({ ...prev, tone }));
  };

  const handleContinue = () => {
    // Validation
    const newErrors: typeof errors = {};

    if (!localProfile.businessName.trim()) {
      newErrors.businessName = 'El nombre es obligatorio';
    }

    if (!localProfile.description.trim()) {
      newErrors.description = 'La descripción es obligatoria';
    } else if (localProfile.description.length < 20) {
      newErrors.description = 'Mínimo 20 caracteres';
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    // Save and continue
    setProfile(localProfile);
    nextStep();
  };

  return (
    <div className="flex flex-col min-h-[80vh] px-6 animate-fade-in">
      {/* Back button */}
      <button
        onClick={prevStep}
        className="flex items-center gap-2 mb-6 text-white/60 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Volver
      </button>

      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="text-center mb-8">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4"
            style={{ background: 'rgba(168, 85, 247, 0.1)' }}
          >
            <User className="w-8 h-8" style={{ color: '#a855f7' }} />
          </div>
          <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">
            Personaliza tu clon
          </h1>
          <p style={{ color: 'rgba(255, 255, 255, 0.6)' }}>
            Cuéntanos sobre tu negocio
          </p>
        </div>

        {/* Form */}
        <div className="flex-1 space-y-6 max-w-sm mx-auto w-full">
          {/* Business Name */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Nombre del negocio o marca
            </label>
            <input
              type="text"
              value={localProfile.businessName}
              onChange={(e) => handleChange('businessName', e.target.value)}
              placeholder="Ej: Fitness con María"
              className={`w-full p-4 rounded-xl text-white outline-none transition-all ${
                errors.businessName ? 'ring-2 ring-red-500' : 'focus:ring-2 focus:ring-purple-500'
              }`}
              style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
            />
            {errors.businessName && (
              <p className="text-red-400 text-sm mt-1">{errors.businessName}</p>
            )}
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              ¿Qué ofreces? ¿A quién?
            </label>
            <textarea
              value={localProfile.description}
              onChange={(e) => handleChange('description', e.target.value)}
              placeholder="Ej: Soy entrenadora personal especializada en fitness femenino. Ofrezco planes de entrenamiento personalizados y coaching nutricional para mujeres que quieren transformar su cuerpo..."
              rows={4}
              className={`w-full p-4 rounded-xl text-white outline-none resize-none transition-all ${
                errors.description ? 'ring-2 ring-red-500' : 'focus:ring-2 focus:ring-purple-500'
              }`}
              style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.08)' }}
            />
            <div className="flex justify-between mt-1">
              {errors.description ? (
                <p className="text-red-400 text-sm">{errors.description}</p>
              ) : (
                <span />
              )}
              <span className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>
                {localProfile.description.length} caracteres
              </span>
            </div>
          </div>

          {/* Tone Selection */}
          <div>
            <label className="block text-sm font-medium text-white mb-3">
              <MessageSquare className="w-4 h-4 inline mr-2" />
              Tono de comunicación
            </label>
            <div className="grid grid-cols-3 gap-3">
              {TONE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => handleToneSelect(option.value)}
                  className={`p-3 rounded-xl text-center transition-all ${
                    localProfile.tone === option.value
                      ? 'ring-2 ring-purple-500'
                      : 'hover:bg-white/5'
                  }`}
                  style={{
                    background: localProfile.tone === option.value
                      ? 'rgba(168, 85, 247, 0.15)'
                      : 'rgba(255, 255, 255, 0.03)',
                    border: '1px solid rgba(255, 255, 255, 0.06)',
                  }}
                >
                  <span className="text-2xl block mb-1">{option.emoji}</span>
                  <span className="text-white text-sm font-medium block">{option.label}</span>
                  <span className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                    {option.description}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Continue Button */}
        <div className="pt-6 max-w-sm mx-auto w-full">
          <button
            onClick={handleContinue}
            className="w-full p-4 text-white font-semibold rounded-xl flex items-center justify-center gap-3 transition-all hover:scale-[1.02]"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              boxShadow: '0 4px 20px rgba(168, 85, 247, 0.3)',
            }}
          >
            Siguiente
            <ArrowRight className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
