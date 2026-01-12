import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { DashboardLayout } from "./components/layout/DashboardLayout";
import { DashboardLayoutClean } from "./components/layout/DashboardLayoutClean";
import NotFound from "./pages/NotFound";
import Login from "./pages/Login";

// Debug logging
console.log("[CLONNECT DEBUG] App.tsx module loading");
console.log("[CLONNECT DEBUG] Current URL:", window.location.href);
console.log("[CLONNECT DEBUG] Pathname:", window.location.pathname);

// Normal imports (no lazy loading)
import Dashboard from "./pages/Dashboard";
import Inbox from "./pages/Inbox";
import Leads from "./pages/Leads";
import Nurturing from "./pages/Nurturing";
import Products from "./pages/Products";
import Bookings from "./pages/Bookings";
import Settings from "./pages/Settings";
import Copilot from "./pages/Copilot";
import Docs from "./pages/Docs";
import Terms from "./pages/Terms";
import Privacy from "./pages/Privacy";
import BookService from "./pages/BookService";
import Onboarding from "./pages/Onboarding";
import InboxTest from "./pages/InboxTest";
import HomeWithConversations from "./pages/HomeWithConversations";

// New Dashboard Pages
import { NewLayout } from "./components/layout/NewLayout";
import Inicio from "./pages/new/Inicio";
import Mensajes from "./pages/new/Mensajes";
import Clientes from "./pages/new/Clientes";
import Ajustes from "./pages/new/Ajustes";

// Configure QueryClient with optimized settings
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000, // 30 seconds before refetch
      gcTime: 300000, // 5 minutes cache
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const AppRoutes = () => {
  console.log("[CLONNECT DEBUG] AppRoutes rendering, pathname:", window.location.pathname);
  return (
    <Routes>
      {/* Login route - always show login page */}
      <Route path="/login" element={<Login />} />

      {/* Onboarding route - no protection, let onboarding handle its own state */}
      <Route path="/onboarding" element={<Onboarding />} />

      {/* Minimal test route to isolate Inbox slowness */}
      <Route path="/inbox-test" element={<InboxTest />} />

      {/* Clean layout test - no Sidebar/MobileNav */}
      <Route element={<DashboardLayoutClean />}>
        <Route path="/clean-inbox-test" element={<HomeWithConversations />} />
      </Route>

      {/* Dashboard routes */}
      <Route element={<DashboardLayout />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/home-conv-test" element={<HomeWithConversations />} />
        <Route path="/dashboard/:creatorId" element={<Dashboard />} />
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/copilot" element={<Copilot />} />
        <Route path="/leads" element={<Leads />} />
        <Route path="/nurturing" element={<Nurturing />} />
        <Route path="/products" element={<Products />} />
        <Route path="/bookings" element={<Bookings />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/docs" element={<Docs />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="/privacy" element={<Privacy />} />
      </Route>

      {/* New Dashboard Routes */}
      <Route path="/new" element={<NewLayout />}>
        <Route index element={<Navigate to="/new/inicio" replace />} />
        <Route path="inicio" element={<Inicio />} />
        <Route path="mensajes" element={<Mensajes />} />
        <Route path="mensajes/:conversationId" element={<Mensajes />} />
        <Route path="clientes" element={<Clientes />} />
        <Route path="ajustes" element={<Ajustes />} />
      </Route>

      {/* Root redirects to login */}
      <Route path="/" element={<Navigate to="/login" replace />} />

      {/* Public booking page - no authentication required */}
      <Route path="/book/:creatorId/:serviceId" element={<BookService />} />

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
};

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
