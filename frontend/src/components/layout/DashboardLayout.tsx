import { useState, useEffect } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { MobileNav } from "./MobileNav";
import { Onboarding } from "@/components/Onboarding";
import { useVisualOnboardingStatus, useCompleteVisualOnboarding } from "@/hooks/useApi";

export function DashboardLayout() {
  const [showOnboarding, setShowOnboarding] = useState(false);
  const { data: onboardingStatus, isLoading } = useVisualOnboardingStatus();
  const completeOnboarding = useCompleteVisualOnboarding();

  // Show onboarding if not completed
  useEffect(() => {
    if (!isLoading && onboardingStatus && !onboardingStatus.onboarding_completed) {
      setShowOnboarding(true);
    }
  }, [isLoading, onboardingStatus]);

  const handleOnboardingComplete = () => {
    completeOnboarding.mutate(undefined, {
      onSuccess: () => {
        setShowOnboarding(false);
      },
    });
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Visual Onboarding Modal */}
      {showOnboarding && <Onboarding onComplete={handleOnboardingComplete} />}

      {/* Desktop Sidebar - hidden on mobile */}
      <div className="hidden md:block">
        <Sidebar />
      </div>

      {/* Mobile Navigation - visible on mobile only */}
      <MobileNav />

      {/* Main Content - no padding-left on mobile, pl-64 on desktop */}
      <main className="pl-0 md:pl-64 min-h-screen pt-16 md:pt-0">
        <div className="p-4 md:p-8 animate-fade-in">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
