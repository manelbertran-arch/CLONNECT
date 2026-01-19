import { useOnboarding, OnboardingStep } from './OnboardingContext';

const STEPS: { key: OnboardingStep; label: string }[] = [
  { key: 'welcome', label: 'Inicio' },
  { key: 'connect', label: 'Instagram' },
  { key: 'profile', label: 'Perfil' },
  { key: 'products', label: 'Productos' },
  { key: 'activate', label: 'Activar' },
];

export function OnboardingProgress() {
  const { currentStep } = useOnboarding();
  const currentIndex = STEPS.findIndex(s => s.key === currentStep);

  return (
    <div className="flex items-center justify-center gap-2 py-4">
      {STEPS.map((step, index) => {
        const isActive = index === currentIndex;
        const isCompleted = index < currentIndex;

        return (
          <div key={step.key} className="flex items-center">
            {/* Dot */}
            <div
              className={`
                w-2.5 h-2.5 rounded-full transition-all duration-300
                ${isActive ? 'w-8 bg-gradient-to-r from-purple-500 to-indigo-500' : ''}
                ${isCompleted ? 'bg-purple-500' : ''}
                ${!isActive && !isCompleted ? 'bg-white/20' : ''}
              `}
            />
          </div>
        );
      })}
    </div>
  );
}

export function OnboardingProgressLabeled() {
  const { currentStep } = useOnboarding();
  const currentIndex = STEPS.findIndex(s => s.key === currentStep);

  return (
    <div className="flex items-center justify-between w-full max-w-md mx-auto py-4 px-2">
      {STEPS.map((step, index) => {
        const isActive = index === currentIndex;
        const isCompleted = index < currentIndex;

        return (
          <div key={step.key} className="flex flex-col items-center gap-1">
            {/* Dot */}
            <div
              className={`
                w-3 h-3 rounded-full transition-all duration-300
                ${isActive ? 'bg-gradient-to-r from-purple-500 to-indigo-500 ring-4 ring-purple-500/20' : ''}
                ${isCompleted ? 'bg-green-500' : ''}
                ${!isActive && !isCompleted ? 'bg-white/20' : ''}
              `}
            />
            {/* Label */}
            <span
              className={`
                text-xs transition-all duration-300
                ${isActive ? 'text-white font-medium' : ''}
                ${isCompleted ? 'text-green-400' : ''}
                ${!isActive && !isCompleted ? 'text-white/40' : ''}
              `}
            >
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
