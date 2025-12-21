import React, { ReactElement } from "react";
import { render, RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/toaster";

// Create a new QueryClient for each test
const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
    },
  });

interface AllProvidersProps {
  children: React.ReactNode;
}

const AllProviders = ({ children }: AllProvidersProps) => {
  const queryClient = createTestQueryClient();
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <TooltipProvider>
          {children}
          <Toaster />
        </TooltipProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

const customRender = (
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">
) => render(ui, { wrapper: AllProviders, ...options });

export * from "@testing-library/react";
export { customRender as render };

// Mock data for tests
export const mockDashboardData = {
  revenue: {
    total: 15000,
    trend: 12.5,
    last_30_days: 5000,
    growth_rate: 15,
  },
  followers: {
    total: 1250,
    new_today: 23,
    trend: 8.3,
  },
  conversations: {
    total: 450,
    pending: 12,
    resolved: 438,
  },
  conversion_rate: {
    rate: 4.5,
    trend: 0.8,
  },
};

export const mockLeadsData = [
  {
    id: "1",
    name: "John Doe",
    instagram_id: "@johndoe",
    stage: "hot",
    score: 85,
    last_message: "I want to buy!",
    last_activity: new Date().toISOString(),
    created_at: new Date().toISOString(),
  },
  {
    id: "2",
    name: "Jane Smith",
    instagram_id: "@janesmith",
    stage: "warm",
    score: 65,
    last_message: "Tell me more",
    last_activity: new Date().toISOString(),
    created_at: new Date().toISOString(),
  },
];

export const mockConversationsData = [
  {
    id: "conv1",
    follower_id: "f1",
    follower_name: "John Doe",
    last_message: "Thanks for the info!",
    unread_count: 0,
    updated_at: new Date().toISOString(),
  },
  {
    id: "conv2",
    follower_id: "f2",
    follower_name: "Jane Smith",
    last_message: "How much does it cost?",
    unread_count: 2,
    updated_at: new Date().toISOString(),
  },
];

export const mockNurturingSequences = [
  {
    id: "1",
    type: "interest_cold",
    name: "Cold Interest Follow-up",
    is_active: true,
    enrolled_count: 15,
    sent_count: 45,
    steps: [
      { delay_hours: 24, message: "Hey! Still interested?" },
      { delay_hours: 72, message: "Just checking in..." },
    ],
  },
  {
    id: "2",
    type: "abandoned",
    name: "Abandoned Cart",
    is_active: false,
    enrolled_count: 5,
    sent_count: 12,
    steps: [{ delay_hours: 1, message: "Need help completing?" }],
  },
];

export const mockRevenueData = {
  metrics: {
    total_revenue: 15000,
    pending_revenue: 2500,
    monthly_growth: 12.5,
    total_customers: 150,
  },
  transactions: [
    {
      id: "t1",
      amount: 99,
      status: "completed",
      customer_name: "John Doe",
      product_name: "Course A",
      created_at: new Date().toISOString(),
    },
  ],
};

export const mockCalendarEvents = [
  {
    id: "e1",
    title: "Follow-up: John Doe",
    start: new Date().toISOString(),
    end: new Date().toISOString(),
    type: "followup",
  },
];
