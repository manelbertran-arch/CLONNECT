// Re-export everything for backward compatibility
// Existing imports like `from '@/services/api'` continue to work

export * from './client';
export * from './auth';
export * from './dashboard';
export * from './dm';
export * from './leads';
export * from './copilot';
export * from './products';
export * from './payments';
export * from './calendar';
export * from './nurturing';
export * from './knowledge';
export * from './creator';
export * from './intelligence';
export * from './audience';
export * from './insights';
export * from './audiencia';
export * from './connections';
export * from './onboarding';
export * from './keys';

// Default export with all functions for backward compatibility
import { getDashboardOverview, toggleBot } from './dashboard';
import { getConversations, getLeads, getMetrics, getFollowerDetail, sendMessage, markConversationRead, updateLeadStatus } from './dm';
import { getCreatorConfig, updateCreatorConfig, getToneProfile, regenerateToneProfile, getContentStats, testClone } from './creator';
import { getProducts, addProduct, updateProduct, deleteProduct } from './products';
import { getRevenueStats, getPurchases } from './payments';
import { getBookings, getCalendarStats, getBookingLinks, getCalendlySyncStatus, createBookingLink, deleteBookingLink } from './calendar';
import { getNurturingSequences, getNurturingFollowups, getNurturingStats, toggleNurturingSequence, updateNurturingSequence, getNurturingEnrolled, cancelNurturing, runNurturing } from './nurturing';
import { addContent, getKnowledge, getFAQs, addFAQ, deleteFAQ, updateFAQ, getAbout, updateAbout, generateKnowledge, deleteKnowledge } from './knowledge';
import { getVisualOnboardingStatus, completeVisualOnboarding, startFullSetup, getSetupProgress } from './onboarding';
import { getCopilotPending, getCopilotStatus, approveCopilotResponse, discardCopilotResponse, toggleCopilotMode, getCopilotNotifications, approveAllCopilot } from './copilot';
import { getEscalations } from './leads';
import { getIntelligenceDashboard, getIntelligencePredictions, getIntelligenceRecommendations, getIntelligencePatterns, getWeeklyReport, generateWeeklyReport } from './intelligence';
import { apiKeys } from './keys';
import { CREATOR_ID, API_URL } from './client';

export default {
  getDashboardOverview, toggleBot,
  getConversations, getLeads, getMetrics, getFollowerDetail, sendMessage, markConversationRead, updateLeadStatus,
  getCreatorConfig, updateCreatorConfig,
  getProducts, addProduct, updateProduct, deleteProduct,
  getRevenueStats, getPurchases,
  getBookings, getCalendarStats, getBookingLinks, getCalendlySyncStatus, createBookingLink, deleteBookingLink,
  getNurturingSequences, getNurturingFollowups, getNurturingStats, toggleNurturingSequence, updateNurturingSequence, getNurturingEnrolled, cancelNurturing, runNurturing,
  addContent, getKnowledge, getFAQs, addFAQ, deleteFAQ, updateFAQ, getAbout, updateAbout, generateKnowledge, deleteKnowledge,
  getVisualOnboardingStatus, completeVisualOnboarding, startFullSetup, getSetupProgress,
  getToneProfile, regenerateToneProfile, getContentStats, testClone,
  getCopilotPending, getCopilotStatus, approveCopilotResponse, discardCopilotResponse, toggleCopilotMode, getCopilotNotifications, approveAllCopilot,
  getEscalations,
  getIntelligenceDashboard, getIntelligencePredictions, getIntelligenceRecommendations, getIntelligencePatterns, getWeeklyReport, generateWeeklyReport,
  apiKeys, CREATOR_ID, API_URL,
};
