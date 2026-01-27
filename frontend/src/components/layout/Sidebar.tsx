import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  MessageSquare,
  Users,
  Sparkles,
  ShoppingBag,
  Calendar,
  Settings,
  Bot,
  LogOut,
  BarChart3,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/context/AuthContext";

const navItems = [
  { path: "/dashboard", label: "Inicio", icon: LayoutDashboard },
  { path: "/inbox", label: "Bandeja", icon: MessageSquare },
  { path: "/copilot", label: "Copilot", icon: Bot },
  { path: "/leads", label: "Leads", icon: Users },
  { path: "/analytics", label: "Analytics", icon: BarChart3 },
  { path: "/nurturing", label: "Nurturing", icon: Sparkles },
  { path: "/products", label: "Productos", icon: ShoppingBag },
  { path: "/bookings", label: "Reservas", icon: Calendar },
  { path: "/settings", label: "Ajustes", icon: Settings },
];

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, creatorId, logout } = useAuth();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  // Get display name from user or creatorId
  const displayName = user?.name || creatorId?.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()) || "User";
  const initials = displayName.split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase();
  const userEmail = user?.email || "";

  return (
    <aside className="fixed left-0 top-0 h-screen w-64 bg-background border-r border-border/50 flex flex-col z-50">
      {/* Logo */}
      <div className="p-6 flex items-center gap-3">
        <img
          src="/clonnect-logo.png"
          alt="Clonnect"
          className="w-9 h-9 object-contain"
        />
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
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{displayName}</p>
            <p className="text-xs text-muted-foreground truncate">
              {userEmail || "Plan Pro"}
            </p>
          </div>
          <button
            onClick={handleLogout}
            className="p-2 hover:bg-secondary rounded-lg transition-colors text-muted-foreground hover:text-foreground"
            title="Cerrar sesión"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
