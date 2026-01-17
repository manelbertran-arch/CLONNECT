# Clonnect Frontend Testing Guide

## Overview

This guide covers the testing infrastructure for the Clonnect frontend application.

## Test Structure

```
src/
├── test/
│   ├── utils.tsx          # Test utilities and providers
│   ├── mocks/
│   │   └── index.ts       # Centralized mocks
│   └── README.md          # This file
├── pages/
│   ├── Dashboard.test.tsx        # Unit tests
│   ├── Dashboard.snapshot.test.tsx  # Snapshot tests
│   └── Dashboard.a11y.test.tsx   # Accessibility tests
```

## Running Tests

```bash
# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage

# Run specific test file
npm test -- Dashboard.test.tsx

# Run tests matching pattern
npm test -- --grep "should render"
```

## Test Types

### 1. Unit Tests (`*.test.tsx`)

Test component logic, state management, and user interactions.

```typescript
import { render, screen, fireEvent } from "@/test/utils";
import Dashboard from "./Dashboard";

describe("Dashboard", () => {
  it("should render stats correctly", () => {
    render(<Dashboard />);
    expect(screen.getByText("Revenue")).toBeInTheDocument();
  });
});
```

### 2. Snapshot Tests (`*.snapshot.test.tsx`)

Capture UI structure to detect unintended changes.

```typescript
import { render } from "@/test/utils";
import Dashboard from "./Dashboard";

describe("Dashboard Snapshots", () => {
  it("matches snapshot with data", () => {
    const { container } = render(<Dashboard />);
    expect(container).toMatchSnapshot();
  });
});
```

### 3. Accessibility Tests (`*.a11y.test.tsx`)

Verify WCAG compliance and keyboard navigation.

```typescript
import { render } from "@/test/utils";
import Dashboard from "./Dashboard";

describe("Dashboard Accessibility", () => {
  it("should have proper heading hierarchy", () => {
    const { container } = render(<Dashboard />);
    const headings = container.querySelectorAll("h1, h2, h3");
    // Verify no skipped levels
  });
});
```

## Using Centralized Mocks

### Import Mocks

```typescript
import {
  mockConversation,
  createMockQuery,
  createMockMutation,
  mockUseApiDefaults,
} from "@/test/mocks";
```

### Mock API Hooks

```typescript
vi.mock("@/hooks/useApi", () => ({
  useConversations: vi.fn(() =>
    createMockQuery({
      conversations: [mockConversation],
    })
  ),
}));
```

### Create Custom Mock Data

```typescript
import { createMockConversations, createMockLeads } from "@/test/mocks";

const conversations = createMockConversations(10);
const leads = createMockLeads(5);
```

### Loading and Error States

```typescript
import { createLoadingQuery, createErrorQuery } from "@/test/mocks";

// Loading state
vi.mock("@/hooks/useApi", () => ({
  useConversations: vi.fn(() => createLoadingQuery()),
}));

// Error state
vi.mock("@/hooks/useApi", () => ({
  useConversations: vi.fn(() => createErrorQuery("Network error")),
}));
```

## Test Utilities

### Custom Render

The custom `render` function wraps components with all required providers:

```typescript
import { render } from "@/test/utils";

// Automatically includes:
// - QueryClientProvider
// - BrowserRouter
// - TooltipProvider
// - Toaster
```

### Available Mock Data

| Export | Description |
|--------|-------------|
| `mockDashboardStats` | Dashboard statistics |
| `mockConversation` | Single conversation |
| `mockLead` | Single lead |
| `mockNurturingSequence` | Nurturing sequence |
| `mockProduct` | Product data |
| `mockCreatorConfig` | Creator configuration |

### Factory Functions

| Function | Description |
|----------|-------------|
| `createMockQuery<T>()` | Create query with data |
| `createMockMutation()` | Create mutation mock |
| `createLoadingQuery<T>()` | Create loading state |
| `createErrorQuery<T>()` | Create error state |
| `createMockConversations(n)` | Generate n conversations |
| `createMockLeads(n)` | Generate n leads |
| `createMockMessages(n, id)` | Generate n messages |

## Accessibility Testing Checklist

- [ ] Heading hierarchy (no skipped levels)
- [ ] Form labels (all inputs have labels)
- [ ] Button accessibility (text or aria-label)
- [ ] Keyboard navigation (tab order)
- [ ] Focus indicators
- [ ] Color contrast
- [ ] Screen reader announcements
- [ ] No duplicate IDs
- [ ] Proper ARIA attributes

## Best Practices

### 1. Use Data-Testid Sparingly

Prefer querying by role, text, or label:

```typescript
// Preferred
screen.getByRole("button", { name: "Submit" });
screen.getByLabelText("Email");

// Only when necessary
screen.getByTestId("complex-widget");
```

### 2. Test User Behavior, Not Implementation

```typescript
// Good - tests what user sees
expect(screen.getByText("Welcome, John")).toBeInTheDocument();

// Avoid - tests implementation details
expect(component.state.userName).toBe("John");
```

### 3. Clean Up After Tests

```typescript
beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});
```

### 4. Group Related Tests

```typescript
describe("Dashboard", () => {
  describe("when loading", () => {
    it("shows skeleton");
  });

  describe("with data", () => {
    it("shows stats");
    it("shows charts");
  });

  describe("on error", () => {
    it("shows error message");
  });
});
```

## CI/CD Integration

Tests run automatically on:
- Every push to `main`
- Every pull request
- Nightly scheduled runs

See `.github/workflows/test.yml` for configuration.

## Troubleshooting

### Tests Timing Out

Increase timeout or check for unresolved promises:

```typescript
it("slow test", async () => {
  // ...
}, 10000); // 10s timeout
```

### Mock Not Working

Ensure mock is defined before imports:

```typescript
// Must be before component import
vi.mock("@/hooks/useApi", () => ({...}));

import Component from "./Component";
```

### Snapshot Outdated

Update snapshots when intentional UI changes occur:

```bash
npm test -- -u
```
