// Clean layout WITHOUT Sidebar or MobileNav
// To test if those components cause the slowness

import { Outlet } from "react-router-dom";

export function DashboardLayoutClean() {
  return (
    <div className="min-h-screen bg-background">
      <div className="p-4 bg-yellow-500/20 text-center text-sm">
        CLEAN LAYOUT TEST - No Sidebar/MobileNav
      </div>
      <main className="min-h-screen p-8">
        <Outlet />
      </main>
    </div>
  );
}
