/**
 * Sidebar Navigation
 *
 * SPRINT3-T3.3: Updated structure with sections
 */
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  Home,
  MessageSquare,
  Users,
  ShoppingBag,
  Calendar,
  Settings,
  Bot,
  LogOut,
  Lightbulb,
  UserCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/context/AuthContext";

type NavItemType = "link" | "section" | "divider";

interface NavItem {
  type?: NavItemType;
  path?: string;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  disabled?: boolean;
  badge?: string;
}

const navItems: NavItem[] = [
  // Main
  { path: "/dashboard", label: "Hoy", icon: Home },
  { path: "/copilot", label: "Copilot", icon: Bot },

  // Operaciones section
  { type: "section", label: "OPERACIONES" },
  { path: "/inbox", label: "Bandeja", icon: MessageSquare },
  { path: "/leads", label: "Leads", icon: Users },
  { path: "/bookings", label: "Reservas", icon: Calendar },
  { path: "/products", label: "Productos", icon: ShoppingBag },

  // Inteligencia section
  { type: "section", label: "INTELIGENCIA" },
  { path: "/tu-audiencia", label: "Tu Audiencia", icon: Lightbulb },
  { path: "/personas", label: "Personas", icon: UserCircle },

  // Divider before settings
  { type: "divider", label: "" },
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
      <nav className="flex-1 px-4 py-2 overflow-y-auto">
        <ul className="space-y-1">
          {navItems.map((item, index) => {
            // Section header
            if (item.type === "section") {
              return (
                <li key={`section-${index}`} className="pt-4 pb-1">
                  <span className="px-3 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                    {item.label}
                  </span>
                </li>
              );
            }

            // Divider
            if (item.type === "divider") {
              return (
                <li key={`divider-${index}`} className="py-2">
                  <div className="border-t border-border/30" />
                </li>
              );
            }

            // Regular nav item
            const isActive = location.pathname === item.path ||
              (item.path === "/dashboard" && location.pathname === "/");
            const Icon = item.icon;

            return (
              <li key={item.path}>
                <NavLink
                  to={item.disabled ? "#" : item.path!}
                  onClick={item.disabled ? (e) => e.preventDefault() : undefined}
                  className={cn(
                    "sidebar-item flex items-center gap-3",
                    isActive && "sidebar-item-active",
                    item.disabled && "opacity-50 cursor-not-allowed hover:bg-transparent"
                  )}
                >
                  {Icon && <Icon className="w-5 h-5" />}
                  <span className="font-medium flex-1">{item.label}</span>
                  {item.badge && (
                    <span className="text-[10px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded">
                      {item.badge}
                    </span>
                  )}
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
