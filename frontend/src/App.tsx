// App Version: 2026-01-26-analytics
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
import Register from "./pages/Register";
import Welcome from "./pages/Welcome";

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
import CrearClon from "./pages/CrearClon";
import CreandoClon from "./pages/CreandoClon";
import Felicidades from "./pages/Felicidades";
import SwitchUser from "./pages/SwitchUser";
import InboxTest from "./pages/InboxTest";
import HomeWithConversations from "./pages/HomeWithConversations";
import { AnalyticsDashboard } from "./pages/Analytics";

// New Dashboard Pages
import { NewLayout } from "./components/layout/NewLayout";
import Inicio from "./pages/new/Inicio";
import Mensajes from "./pages/new/Mensajes";
import Clientes from "./pages/new/Clientes";
import Ajustes from "./pages/new/Ajustes";
import NewOnboarding from "./pages/new/Onboarding";

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
  return (
    <Routes>
      {/* Auth routes */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      {/* Onboarding routes */}
      <Route path="/onboarding" element={<Onboarding />} />
      <Route path="/crear-clon" element={<CrearClon />} />
      <Route path="/creando-clon" element={<CreandoClon />} />
      <Route path="/new/onboarding" element={<NewOnboarding />} />
      <Route path="/felicidades" element={<Felicidades />} />
      <Route path="/switch-user/:creatorId" element={<SwitchUser />} />

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
        <Route path="/analytics" element={<AnalyticsDashboard />} />
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

      {/* Root shows welcome page */}
      <Route path="/" element={<Welcome />} />

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
