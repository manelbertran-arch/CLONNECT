import { useNavigate } from 'react-router-dom';
import { useCallback, useRef } from 'react';
import { Onboarding as OnboardingSlides } from '../components/Onboarding';

/**
 * Onboarding Page
 * Shows the 12 educational slides about Clonnect
 * After completion, redirects to /crear-clon (Create your clone)
 */
export default function Onboarding() {
  const navigate = useNavigate();
  const completedRef = useRef(false);

  const handleComplete = useCallback(() => {
    // Prevent double-navigation
    if (completedRef.current) {
      console.log('[Onboarding] Already completed, ignoring');
      return;
    }
    completedRef.current = true;
    console.log('[Onboarding] 12 slides completed! Navigating to /crear-clon');
    // After 12 slides, go to the "Create your clone" step
    navigate('/crear-clon');
  }, [navigate]);

  console.log('[Onboarding] Rendering 12 intro slides');

  return <OnboardingSlides onComplete={handleComplete} />;
}
