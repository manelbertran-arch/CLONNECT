import { OnboardingProvider, useOnboarding } from '@/components/onboarding/OnboardingContext';
import { OnboardingProgress } from '@/components/onboarding/OnboardingProgress';
import { StepWelcome } from '@/components/onboarding/StepWelcome';
import { StepConnectIG } from '@/components/onboarding/StepConnectIG';
import { StepProfile } from '@/components/onboarding/StepProfile';
import { StepProducts } from '@/components/onboarding/StepProducts';
import { StepActivate } from '@/components/onboarding/StepActivate';

function OnboardingWizard() {
  const { currentStep } = useOnboarding();

  const renderStep = () => {
    switch (currentStep) {
      case 'welcome':
        return <StepWelcome />;
      case 'connect':
        return <StepConnectIG />;
      case 'profile':
        return <StepProfile />;
      case 'products':
        return <StepProducts />;
      case 'activate':
        return <StepActivate />;
      default:
        return <StepWelcome />;
    }
  };

  return (
    <div className="min-h-screen" style={{ background: '#09090b' }}>
      {/* Background gradient effects */}
      <div
        style={{
          position: 'fixed',
          top: '5%',
          left: '5%',
          width: '500px',
          height: '500px',
          background: 'radial-gradient(circle, rgba(168, 85, 247, 0.08) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(80px)',
          pointerEvents: 'none',
        }}
      />
      <div
        style={{
          position: 'fixed',
          bottom: '10%',
          right: '10%',
          width: '400px',
          height: '400px',
          background: 'radial-gradient(circle, rgba(99, 102, 241, 0.08) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(80px)',
          pointerEvents: 'none',
        }}
      />

      {/* Content */}
      <div className="relative z-10 max-w-lg mx-auto">
        {/* Progress indicator - hide on welcome and activate/complete */}
        {currentStep !== 'welcome' && currentStep !== 'activate' && (
          <div className="pt-6">
            <OnboardingProgress />
          </div>
        )}

        {/* Current step */}
        <div className="py-6">
          {renderStep()}
        </div>
      </div>

      {/* CSS for animations */}
      <style>{`
        @keyframes fade-in {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .animate-fade-in {
          animation: fade-in 0.4s ease-out forwards;
        }
      `}</style>
    </div>
  );
}

export default function Onboarding() {
  return (
    <OnboardingProvider>
      <OnboardingWizard />
    </OnboardingProvider>
  );
}
