import { useNavigate } from 'react-router-dom';
import { Onboarding } from '../components/Onboarding';

/**
 * OnboardingIntro Page
 * Shows the 12 educational slides about Clonnect
 * After completion, redirects to /onboarding (Create your clone)
 */
export default function OnboardingIntro() {
  const navigate = useNavigate();

  const handleComplete = () => {
    // After 12 slides, go to the "Create your clone" step
    navigate('/onboarding');
  };

  return <Onboarding onComplete={handleComplete} />;
}
