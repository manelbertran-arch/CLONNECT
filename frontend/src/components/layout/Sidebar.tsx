import { NavLink, useLocation } from "react-router-dom";
import { 
  LayoutDashboard, 
  MessageSquare, 
  Users, 
  Sparkles, 
  TrendingUp, 
  Calendar, 
  Settings,
  Zap
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { path: "/dashboard", label: "Home", icon: LayoutDashboard },
  { path: "/inbox", label: "Inbox", icon: MessageSquare },
  { path: "/leads", label: "Leads", icon: Users },
  { path: "/nurturing", label: "Nurturing", icon: Sparkles },
  { path: "/revenue", label: "Revenue", icon: TrendingUp },
  { path: "/bookings", label: "Bookings", icon: Calendar },
  { path: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const location = useLocation();

  return (
    <aside className="fixed left-0 top-0 h-screen w-64 bg-background border-r border-border/50 flex flex-col z-50">
      {/* Logo */}
      <div className="p-6 flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center">
          <Zap className="w-5 h-5 text-white" />
        </div>
        <span className="text-xl font-bold tracking-tight">Clonnect</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 py-2">
        <ul className="space-y-1">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path || 
              (item.path === "/dashboard" && location.pathname === "/");
            return (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  className={cn(
                    "sidebar-item",
                    isActive && "sidebar-item-active"
                  )}
                >
                  <item.icon className="w-5 h-5" />
                  <span className="font-medium">{item.label}</span>
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* User */}
      <div className="p-4 border-t border-border/50">
        <div className="flex items-center gap-3 px-3 py-2">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary/60 to-accent/60 flex items-center justify-center text-sm font-semibold">
            M
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">Manel</p>
            <p className="text-xs text-muted-foreground truncate">Pro Plan</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
