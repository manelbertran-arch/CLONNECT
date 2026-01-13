import { useNavigate } from 'react-router-dom';
import { useCallback, useRef } from 'react';
import { Onboarding } from '../components/Onboarding';

/**
 * OnboardingIntro Page
 * Shows the 12 educational slides about Clonnect
 * After completion, redirects to /onboarding (Create your clone)
 */
export default function OnboardingIntro() {
  const navigate = useNavigate();
  const completedRef = useRef(false);

  const handleComplete = useCallback(() => {
    // Prevent double-navigation
    if (completedRef.current) {
      console.log('[OnboardingIntro] Already completed, ignoring');
      return;
    }
    completedRef.current = true;
    console.log('[OnboardingIntro] Completed! Navigating to /onboarding');
    // After 12 slides, go to the "Create your clone" step
    navigate('/onboarding');
  }, [navigate]);

  console.log('[OnboardingIntro] Rendering');

  return <Onboarding onComplete={handleComplete} />;
}
