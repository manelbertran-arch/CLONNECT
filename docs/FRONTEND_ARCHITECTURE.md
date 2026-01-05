# Frontend Architecture - CLONNECT

## Overview

React + TypeScript + Vite application with TailwindCSS and shadcn/ui components.

## Directory Structure

```
frontend/src/
├── App.tsx              # Main app with routing
├── main.tsx             # Entry point
├── index.css            # Global styles + Tailwind
├── App.css              # App-specific styles
│
├── components/
│   ├── layout/
│   │   ├── DashboardLayout.tsx   # Main layout wrapper
│   │   ├── Sidebar.tsx           # Desktop navigation
│   │   └── MobileNav.tsx         # Mobile hamburger nav
│   │
│   ├── Onboarding.tsx            # Visual onboarding modal
│   ├── OnboardingChecklist.tsx   # Step-by-step checklist
│   ├── OnboardingDesktop.tsx     # Desktop onboarding variant
│   ├── OnboardingMobile.tsx      # Mobile onboarding variant
│   ├── NavLink.tsx               # Navigation link component
│   │
│   └── ui/                       # shadcn/ui components (50+ files)
│       ├── button.tsx
│       ├── card.tsx
│       ├── dialog.tsx
│       ├── input.tsx
│       ├── toast.tsx
│       └── ... (accordion, alert, avatar, badge, etc.)
│
├── pages/
│   ├── Dashboard.tsx     # Main dashboard (Home)
│   ├── Inbox.tsx         # Conversations view
│   ├── Leads.tsx         # Lead management
│   ├── Nurturing.tsx     # Nurturing sequences
│   ├── Products.tsx      # Product management
│   ├── Bookings.tsx      # Calendar/bookings
│   ├── Settings.tsx      # Creator settings
│   ├── Docs.tsx          # Documentation
│   ├── Terms.tsx         # Terms of service
│   ├── Privacy.tsx       # Privacy policy
│   ├── BookService.tsx   # Public booking page
│   └── NotFound.tsx      # 404 page
│
├── hooks/
│   ├── useApi.ts         # React Query hooks for API
│   ├── use-toast.ts      # Toast notifications
│   └── use-mobile.tsx    # Mobile detection
│
├── services/
│   └── api.ts            # API service layer (all endpoints)
│
├── types/
│   └── api.ts            # TypeScript interfaces
│
├── lib/
│   └── utils.ts          # Utility functions (cn for classnames)
│
└── test/
    ├── setup.ts          # Test configuration
    ├── utils.tsx         # Test utilities
    └── mocks/useApi.ts   # API mocks for tests
```

## Routing

| Path | Component | Description |
|------|-----------|-------------|
| `/` | Redirect | → `/dashboard` |
| `/dashboard` | Dashboard.tsx | Main metrics view |
| `/inbox` | Inbox.tsx | All conversations |
| `/leads` | Leads.tsx | Lead management |
| `/nurturing` | Nurturing.tsx | Automation sequences |
| `/products` | Products.tsx | Product catalog |
| `/bookings` | Bookings.tsx | Calendar & bookings |
| `/settings` | Settings.tsx | Bot settings |
| `/docs` | Docs.tsx | Documentation |
| `/book/:creatorId/:serviceId` | BookService.tsx | Public booking (no layout) |

## Navigation (Sidebar)

```typescript
const navItems = [
  { path: "/dashboard", label: "Home", icon: LayoutDashboard },
  { path: "/inbox", label: "Inbox", icon: MessageSquare },
  { path: "/leads", label: "Leads", icon: Users },
  { path: "/nurturing", label: "Nurturing", icon: Sparkles },
  { path: "/products", label: "Products", icon: ShoppingBag },
  { path: "/bookings", label: "Bookings", icon: Calendar },
  { path: "/settings", label: "Settings", icon: Settings },
];
```

## State Management

- **React Query** (`@tanstack/react-query`) for server state
- **Local state** (`useState`) for UI state
- **No Redux/Zustand** - simple prop drilling where needed

### API Hooks Pattern

```typescript
// In hooks/useApi.ts
export function useDashboard() {
  return useQuery({
    queryKey: apiKeys.dashboard(CREATOR_ID),
    queryFn: () => getDashboardOverview(CREATOR_ID),
  });
}

export function useUpdateConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: Partial<CreatorConfig>) =>
      updateCreatorConfig(CREATOR_ID, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.config(CREATOR_ID) });
    },
  });
}
```

## Styling

### Theme (Dark mode default)

```css
:root {
  --background: 240 6% 4%;        /* Near black */
  --foreground: 0 0% 98%;         /* White text */
  --primary: 262 83% 58%;         /* Purple */
  --accent: 187 92% 55%;          /* Cyan */
  --card: 240 5% 8%;              /* Dark card bg */
  --border: 240 4% 24%;           /* Subtle borders */
}
```

### Component Classes

```css
.metric-card    /* Card with hover effect */
.sidebar-item   /* Nav item styling */
.status-badge   /* Status indicators */
.gradient-text  /* Purple-cyan gradient */
.glass          /* Frosted glass effect */
.glow           /* Purple glow shadow */
```

## API Layer

All API calls go through `services/api.ts`:

```typescript
// Base configuration
export const API_URL = import.meta.env.VITE_API_URL || "https://web-production-9f69.up.railway.app";
export const CREATOR_ID = import.meta.env.VITE_CREATOR_ID || "manel";

// Generic fetch wrapper
async function apiFetch<T>(endpoint: string, options?: RequestInit): Promise<T>

// Endpoint groups:
// - Dashboard: getDashboardOverview, toggleBot
// - DM/Conversations: getConversations, getFollowerDetail, sendMessage
// - Leads: getLeads, updateLeadStatus, createManualLead
// - Config: getCreatorConfig, updateCreatorConfig
// - Products: getProducts, addProduct, updateProduct, deleteProduct
// - Payments: getRevenueStats, getPurchases, recordPurchase
// - Calendar: getBookings, getBookingLinks, createBookingLink
// - Nurturing: getNurturingSequences, toggleNurturingSequence, runNurturing
// - Knowledge: getKnowledge, addFAQ, updateAbout
// - Connections: getConnections, updateConnection, disconnectPlatform
```

## Key Patterns

### 1. Page Structure

```tsx
export default function PageName() {
  const { data, isLoading, error } = useApiHook();

  if (isLoading) return <Skeleton />;
  if (error) return <ErrorMessage />;

  return (
    <div className="space-y-6">
      <header className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Page Title</h1>
        <Button>Action</Button>
      </header>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Content cards */}
      </div>
    </div>
  );
}
```

### 2. Responsive Design

- Mobile-first with Tailwind breakpoints
- `md:` prefix for tablet/desktop
- Sidebar hidden on mobile, MobileNav shown instead
- Grid columns adjust: `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`

### 3. Component Composition

```tsx
// Using shadcn/ui components
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Dialog, DialogTrigger, DialogContent } from "@/components/ui/dialog";
```

## Extension Points

### Adding a New Page

1. Create `pages/NewPage.tsx`
2. Add route in `App.tsx`:
   ```tsx
   <Route path="/new-page" element={<NewPage />} />
   ```
3. Add to sidebar in `components/layout/Sidebar.tsx`:
   ```tsx
   { path: "/new-page", label: "New Page", icon: SomeIcon }
   ```

### Adding API Endpoints

1. Add types in `types/api.ts`
2. Add fetch function in `services/api.ts`
3. Add query key in `apiKeys` object
4. Create hook in `hooks/useApi.ts`

### Adding UI Components

Use shadcn/ui CLI:
```bash
npx shadcn@latest add [component-name]
```

## Testing

```bash
# Run tests
npm test

# Test files
pages/*.test.tsx     # Page component tests
test/mocks/useApi.ts # Mock API responses
test/setup.ts        # Jest/Vitest config
test/utils.tsx       # Test utilities
```

## Environment Variables

```env
VITE_API_URL=https://web-production-9f69.up.railway.app
VITE_CREATOR_ID=manel
```

## Dependencies

- **React 18** - UI framework
- **React Router 6** - Routing
- **TanStack Query** - Server state management
- **Tailwind CSS** - Utility-first CSS
- **shadcn/ui** - Component library
- **Lucide React** - Icon library
- **Recharts** - Charts (used in Dashboard)
- **date-fns** - Date formatting
