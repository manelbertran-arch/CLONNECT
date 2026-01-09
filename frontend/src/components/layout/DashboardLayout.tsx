import { useEffect } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { MobileNav } from "./MobileNav";
import { useVisualOnboardingStatus } from "@/hooks/useApi";

export function DashboardLayout() {
  const navigate = useNavigate();
  const { data: onboardingStatus, isLoading } = useVisualOnboardingStatus();

  // Redirect to /onboarding if not completed
  useEffect(() => {
    if (isLoading) return;

    // If onboarding not completed, redirect to /onboarding page
    if (onboardingStatus && !onboardingStatus.onboarding_completed) {
      console.log("Onboarding not completed, redirecting to /onboarding");
      navigate("/onboarding", { replace: true });
    }
  }, [isLoading, onboardingStatus, navigate]);

  // Show loading while checking onboarding status
  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Cargando...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">

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
