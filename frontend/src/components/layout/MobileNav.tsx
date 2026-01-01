import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  MessageSquare,
  Users,
  Sparkles,
  ShoppingBag,
  TrendingUp,
  Calendar,
  Settings,
  Zap,
  Menu,
  X
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";

const navItems = [
  { path: "/dashboard", label: "Home", icon: LayoutDashboard },
  { path: "/inbox", label: "Inbox", icon: MessageSquare },
  { path: "/leads", label: "Leads", icon: Users },
  { path: "/nurturing", label: "Nurturing", icon: Sparkles },
  { path: "/products", label: "Products", icon: ShoppingBag },
  { path: "/revenue", label: "Revenue", icon: TrendingUp },
  { path: "/calendar", label: "Calendar", icon: Calendar },
  { path: "/settings", label: "Settings", icon: Settings },
];

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const location = useLocation();

  return (
    <div className="md:hidden fixed top-0 left-0 right-0 h-16 bg-background border-b border-border/50 z-50 flex items-center justify-between px-4">
      {/* Logo */}
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center">
          <Zap className="w-4 h-4 text-white" />
        </div>
        <span className="text-lg font-bold tracking-tight">Clonnect</span>
      </div>

      {/* Menu Button */}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon">
            <Menu className="h-6 w-6" />
            <span className="sr-only">Toggle menu</span>
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-64 p-0">
          {/* Drawer Header */}
          <div className="p-6 flex items-center gap-3 border-b border-border/50">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold tracking-tight">Clonnect</span>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-4 py-4">
            <ul className="space-y-1">
              {navItems.map((item) => {
                const isActive = location.pathname === item.path ||
                  (item.path === "/dashboard" && location.pathname === "/");
                return (
                  <li key={item.path}>
                    <NavLink
                      to={item.path}
                      onClick={() => setOpen(false)}
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
          <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-border/50">
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
        </SheetContent>
      </Sheet>
    </div>
  );
}
