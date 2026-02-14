import { lazy, Suspense } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { DashboardLayoutClean } from "./components/layout/DashboardLayoutClean";
import NotFound from "./pages/NotFound";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Welcome from "./pages/Welcome";

// Critical pages - loaded immediately
import Copilot from "./pages/Copilot";
import Onboarding from "./pages/Onboarding";
import CrearClon from "./pages/CrearClon";
import CreandoClon from "./pages/CreandoClon";
import Felicidades from "./pages/Felicidades";
import SwitchUser from "./pages/SwitchUser";
import InboxTest from "./pages/InboxTest";
import HomeWithConversations from "./pages/HomeWithConversations";

// Lazy-loaded pages - loaded on demand
const Nurturing = lazy(() => import("./pages/Nurturing"));
const Products = lazy(() => import("./pages/Products"));
const Bookings = lazy(() => import("./pages/Bookings"));
const Settings = lazy(() => import("./pages/Settings"));
const Docs = lazy(() => import("./pages/Docs"));
const Terms = lazy(() => import("./pages/Terms"));
const Privacy = lazy(() => import("./pages/Privacy"));
const BookService = lazy(() => import("./pages/BookService"));
const AnalyticsDashboard = lazy(() => import("./pages/Analytics").then(m => ({ default: m.AnalyticsDashboard })));
const TuAudiencia = lazy(() => import("./pages/TuAudiencia"));
const Personas = lazy(() => import("./pages/Personas"));

// Loading fallback for lazy-loaded pages
function PageLoader() {
  return (
    <div className="flex items-center justify-center h-[60vh]">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
    </div>
  );
}

// Coming Soon placeholder component
function ComingSoon({ title }: { title: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
      <div className="text-6xl">🚧</div>
      <h1 className="text-2xl font-bold">{title}</h1>
      <p className="text-muted-foreground">Próximamente disponible</p>
    </div>
  );
}

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
      {/* Public auth routes */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      {/* Public onboarding routes */}
      <Route path="/onboarding" element={<Onboarding />} />
      <Route path="/crear-clon" element={<CrearClon />} />
      <Route path="/creando-clon" element={<CreandoClon />} />
      <Route path="/new/onboarding" element={<NewOnboarding />} />
      <Route path="/felicidades" element={<Felicidades />} />

      {/* Public legal pages */}
      <Route path="/terms" element={<Suspense fallback={<PageLoader />}><Terms /></Suspense>} />
      <Route path="/privacy" element={<Suspense fallback={<PageLoader />}><Privacy /></Suspense>} />

      {/* Public booking page */}
      <Route path="/book/:creatorId/:serviceId" element={<Suspense fallback={<PageLoader />}><BookService /></Suspense>} />

      {/* Debug/test routes (no auth) */}
      <Route path="/inbox-test" element={<InboxTest />} />
      <Route element={<DashboardLayoutClean />}>
        <Route path="/clean-inbox-test" element={<HomeWithConversations />} />
      </Route>
      <Route path="/home-conv-test" element={<HomeWithConversations />} />

      {/* Protected: switch user */}
      <Route path="/switch-user/:creatorId" element={<ProtectedRoute><SwitchUser /></ProtectedRoute>} />

      {/* Protected: unified dashboard (NewLayout) */}
      <Route path="/new" element={<ProtectedRoute><NewLayout /></ProtectedRoute>}>
        <Route index element={<Navigate to="/new/inicio" replace />} />
        <Route path="inicio" element={<Inicio />} />
        <Route path="mensajes" element={<Mensajes />} />
        <Route path="mensajes/:conversationId" element={<Mensajes />} />
        <Route path="clientes" element={<Clientes />} />
        <Route path="ajustes" element={<Ajustes />} />
        {/* Features migrated from old dashboard */}
        <Route path="copilot" element={<Copilot />} />
        <Route path="products" element={<Suspense fallback={<PageLoader />}><Products /></Suspense>} />
        <Route path="nurturing" element={<Suspense fallback={<PageLoader />}><Nurturing /></Suspense>} />
        <Route path="bookings" element={<Suspense fallback={<PageLoader />}><Bookings /></Suspense>} />
        <Route path="analytics" element={<Suspense fallback={<PageLoader />}><AnalyticsDashboard /></Suspense>} />
        <Route path="audiencia" element={<Suspense fallback={<PageLoader />}><TuAudiencia /></Suspense>} />
        <Route path="personas" element={<Suspense fallback={<PageLoader />}><Personas /></Suspense>} />
        <Route path="docs" element={<Suspense fallback={<PageLoader />}><Docs /></Suspense>} />
      </Route>

      {/* Redirects: old dashboard routes → new layout */}
      <Route path="/dashboard" element={<Navigate to="/new/inicio" replace />} />
      <Route path="/dashboard/:creatorId" element={<Navigate to="/new/inicio" replace />} />
      <Route path="/inbox" element={<Navigate to="/new/mensajes" replace />} />
      <Route path="/copilot" element={<Navigate to="/new/copilot" replace />} />
      <Route path="/leads" element={<Navigate to="/new/clientes" replace />} />
      <Route path="/products" element={<Navigate to="/new/products" replace />} />
      <Route path="/nurturing" element={<Navigate to="/new/nurturing" replace />} />
      <Route path="/settings" element={<Navigate to="/new/ajustes" replace />} />
      <Route path="/analytics" element={<Navigate to="/new/analytics" replace />} />
      <Route path="/bookings" element={<Navigate to="/new/bookings" replace />} />
      <Route path="/tu-audiencia" element={<Navigate to="/new/audiencia" replace />} />
      <Route path="/personas" element={<Navigate to="/new/personas" replace />} />
      <Route path="/docs" element={<Navigate to="/new/docs" replace />} />

      {/* Root shows welcome page */}
      <Route path="/" element={<Welcome />} />

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
