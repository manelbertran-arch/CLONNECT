import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { MobileNav } from "./MobileNav";

export function DashboardLayout() {
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
