import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { getCreatorId, setCreatorId } from '@/services/api';

export type OnboardingStep = 'welcome' | 'connect' | 'profile' | 'products' | 'activate';

export interface ProfileData {
  businessName: string;
  description: string;
  tone: 'formal' | 'casual' | 'friendly';
}

export interface ProductData {
  id: string;
  name: string;
  description: string;
  price?: string;
}

interface OnboardingState {
  currentStep: OnboardingStep;
  creatorId: string;
  instagramConnected: boolean;
  instagramUsername: string;
  profile: ProfileData;
  products: ProductData[];
  botActive: boolean;
  isLoading: boolean;
  error: string | null;
}

interface OnboardingContextType extends OnboardingState {
  setStep: (step: OnboardingStep) => void;
  nextStep: () => void;
  prevStep: () => void;
  setInstagramConnected: (connected: boolean, username?: string) => void;
  setProfile: (profile: ProfileData) => void;
  addProduct: (product: Omit<ProductData, 'id'>) => void;
  removeProduct: (id: string) => void;
  setBotActive: (active: boolean) => void;
  setError: (error: string | null) => void;
  setLoading: (loading: boolean) => void;
  saveProgress: () => Promise<void>;
  getOrCreateCreatorId: () => string;
}

const STEPS_ORDER: OnboardingStep[] = ['welcome', 'connect', 'profile', 'products', 'activate'];

const STORAGE_KEY = 'clonnect_onboarding';

const defaultState: OnboardingState = {
  currentStep: 'welcome',
  creatorId: '',
  instagramConnected: false,
  instagramUsername: '',
  profile: {
    businessName: '',
    description: '',
    tone: 'friendly',
  },
  products: [],
  botActive: true,
  isLoading: false,
  error: null,
};

const OnboardingContext = createContext<OnboardingContextType | undefined>(undefined);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<OnboardingState>(() => {
    // Try to restore from localStorage
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return { ...defaultState, ...parsed, isLoading: false, error: null };
      }
    } catch (e) {
      console.error('Failed to restore onboarding state:', e);
    }
    return defaultState;
  });

  // Persist state to localStorage
  useEffect(() => {
    const toSave = {
      currentStep: state.currentStep,
      creatorId: state.creatorId,
      instagramConnected: state.instagramConnected,
      instagramUsername: state.instagramUsername,
      profile: state.profile,
      products: state.products,
      botActive: state.botActive,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
  }, [state.currentStep, state.creatorId, state.instagramConnected, state.instagramUsername, state.profile, state.products, state.botActive]);

  const getOrCreateCreatorId = (): string => {
    if (state.creatorId) return state.creatorId;

    const existing = getCreatorId();
    if (existing && existing !== 'demo_creator') {
      setState(s => ({ ...s, creatorId: existing }));
      return existing;
    }

    const newId = `user_${Date.now()}`;
    setState(s => ({ ...s, creatorId: newId }));
    setCreatorId(newId);
    return newId;
  };

  const setStep = (step: OnboardingStep) => {
    setState(s => ({ ...s, currentStep: step }));
  };

  const nextStep = () => {
    const currentIndex = STEPS_ORDER.indexOf(state.currentStep);
    if (currentIndex < STEPS_ORDER.length - 1) {
      setState(s => ({ ...s, currentStep: STEPS_ORDER[currentIndex + 1] }));
    }
  };

  const prevStep = () => {
    const currentIndex = STEPS_ORDER.indexOf(state.currentStep);
    if (currentIndex > 0) {
      setState(s => ({ ...s, currentStep: STEPS_ORDER[currentIndex - 1] }));
    }
  };

  const setInstagramConnected = (connected: boolean, username?: string) => {
    setState(s => ({
      ...s,
      instagramConnected: connected,
      instagramUsername: username || s.instagramUsername,
    }));
  };

  const setProfile = (profile: ProfileData) => {
    setState(s => ({ ...s, profile }));
  };

  const addProduct = (product: Omit<ProductData, 'id'>) => {
    const newProduct: ProductData = {
      ...product,
      id: `prod_${Date.now()}`,
    };
    setState(s => ({ ...s, products: [...s.products, newProduct] }));
  };

  const removeProduct = (id: string) => {
    setState(s => ({ ...s, products: s.products.filter(p => p.id !== id) }));
  };

  const setBotActive = (active: boolean) => {
    setState(s => ({ ...s, botActive: active }));
  };

  const setError = (error: string | null) => {
    setState(s => ({ ...s, error }));
  };

  const setLoading = (loading: boolean) => {
    setState(s => ({ ...s, isLoading: loading }));
  };

  const saveProgress = async () => {
    // This will be called to save to backend
    // For now, localStorage handles it
    console.log('[Onboarding] Progress saved:', state);
  };

  return (
    <OnboardingContext.Provider
      value={{
        ...state,
        setStep,
        nextStep,
        prevStep,
        setInstagramConnected,
        setProfile,
        addProduct,
        removeProduct,
        setBotActive,
        setError,
        setLoading,
        saveProgress,
        getOrCreateCreatorId,
      }}
    >
      {children}
    </OnboardingContext.Provider>
  );
}

export function useOnboarding() {
  const context = useContext(OnboardingContext);
  if (!context) {
    throw new Error('useOnboarding must be used within OnboardingProvider');
  }
  return context;
}

export function clearOnboardingStorage() {
  localStorage.removeItem(STORAGE_KEY);
}
