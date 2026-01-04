import { useState, useEffect } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { MobileNav } from "./MobileNav";
import { Onboarding } from "@/components/Onboarding";
import { useVisualOnboardingStatus, useCompleteVisualOnboarding } from "@/hooks/useApi";

export function DashboardLayout() {
  const [showOnboarding, setShowOnboarding] = useState(false);
  const { data: onboardingStatus, isLoading, error: statusError } = useVisualOnboardingStatus();
  const completeOnboarding = useCompleteVisualOnboarding();

  // Determine if we should show onboarding based on API response
  useEffect(() => {
    if (isLoading) return;

    // If API error, skip onboarding (don't block user)
    if (statusError) {
      console.error("Failed to fetch onboarding status:", statusError);
      setShowOnboarding(false);
      return;
    }

    // Show onboarding only if status says not completed
    if (onboardingStatus && !onboardingStatus.onboarding_completed) {
      setShowOnboarding(true);
    } else {
      setShowOnboarding(false);
    }
  }, [isLoading, onboardingStatus, statusError]);

  const handleOnboardingComplete = async () => {
    try {
      // 1. Call API to mark as completed
      await completeOnboarding.mutateAsync(undefined);

      // 2. Close the onboarding modal
      setShowOnboarding(false);

      console.log("Onboarding completed successfully");
    } catch (error) {
      // Even if API fails, close the modal so user isn't stuck
      console.error("Error completing onboarding:", error);
      setShowOnboarding(false);
    }
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
