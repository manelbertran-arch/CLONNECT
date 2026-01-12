import { Suspense, lazy } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { DashboardLayout } from "./components/layout/DashboardLayout";
import NotFound from "./pages/NotFound";
import Login from "./pages/Login";

// Lazy load pages for better performance
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Inbox = lazy(() => import("./pages/Inbox"));
const Leads = lazy(() => import("./pages/Leads"));
const Nurturing = lazy(() => import("./pages/Nurturing"));
const Products = lazy(() => import("./pages/Products"));
const Bookings = lazy(() => import("./pages/Bookings"));
const Settings = lazy(() => import("./pages/Settings"));
const Copilot = lazy(() => import("./pages/Copilot"));
const Docs = lazy(() => import("./pages/Docs"));
const Terms = lazy(() => import("./pages/Terms"));
const Privacy = lazy(() => import("./pages/Privacy"));
const BookService = lazy(() => import("./pages/BookService"));
const Onboarding = lazy(() => import("./pages/Onboarding"));

// New Dashboard Pages - lazy loaded
const NewLayout = lazy(() => import("./components/layout/NewLayout").then(m => ({ default: m.NewLayout })));
const Inicio = lazy(() => import("./pages/new/Inicio"));
const Mensajes = lazy(() => import("./pages/new/Mensajes"));
const Clientes = lazy(() => import("./pages/new/Clientes"));
const Ajustes = lazy(() => import("./pages/new/Ajustes"));

// Loading spinner for Suspense fallback
const PageLoader = () => (
  <div className="flex items-center justify-center min-h-screen bg-gray-950">
    <div className="flex flex-col items-center gap-4">
      <div className="w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full animate-spin" />
      <p className="text-gray-400 text-sm">Cargando...</p>
    </div>
  </div>
);

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
    <Suspense fallback={<PageLoader />}>
      <Routes>
        {/* Login route - always show login page */}
        <Route path="/login" element={<Login />} />

        {/* Onboarding route - no protection, let onboarding handle its own state */}
        <Route path="/onboarding" element={<Onboarding />} />

        {/* Dashboard routes */}
        <Route element={<DashboardLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
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
    </Suspense>
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
