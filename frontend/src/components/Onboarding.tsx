import { useEffect, useState } from 'react';
import { OnboardingDesktop } from './OnboardingDesktop';
import { OnboardingMobile } from './OnboardingMobile';

interface OnboardingProps {
  onComplete: () => void;
}

/**
 * Onboarding Wrapper Component
 * Detects device type and renders the appropriate onboarding experience:
 * - Desktop: Full visual experience with mockups and animations
 * - Mobile: Simplified vertical layout optimized for touch
 */
export function Onboarding({ onComplete }: OnboardingProps) {
  const [isMobile, setIsMobile] = useState<boolean | null>(null);

  useEffect(() => {
    const checkDevice = () => {
      setIsMobile(window.innerWidth < 768);
    };

    // Initial check
    checkDevice();

    // Listen for resize events
    window.addEventListener('resize', checkDevice);
    return () => window.removeEventListener('resize', checkDevice);
  }, []);

  // Don't render until we know the device type
  if (isMobile === null) {
    return (
      <div
        style={{
          position: 'fixed',
          inset: 0,
          background: '#09090b',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
      >
        <div
          style={{
            width: 40,
            height: 40,
            border: '3px solid rgba(168, 85, 247, 0.3)',
            borderTopColor: '#a855f7',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite'
          }}
        />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // Render the appropriate component based on device
  if (isMobile) {
    return <OnboardingMobile onComplete={onComplete} />;
  }

  return <OnboardingDesktop onComplete={onComplete} />;
}

export default Onboarding;
