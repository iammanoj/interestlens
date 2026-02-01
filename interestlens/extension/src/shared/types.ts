/**
 * Shared types for InterestLens extension
 */

export interface PageItem {
  id: string;
  href: string | null;
  text: string;
  snippet: string;
  bbox: [number, number, number, number]; // [x, y, width, height]
  thumbnailBase64: string | null;
}

export interface ScoredItem {
  id: string;
  score: number;
  topics: string[];
  why: string;
}

export interface DOMOutline {
  title: string;
  headings: string[];
  mainTextExcerpt: string;
}

export interface AnalyzeRequest {
  pageUrl: string;
  domOutline: DOMOutline;
  items: PageItem[];
  screenshotBase64?: string;
}

export interface AnalyzeResponse {
  items: ScoredItem[];
  pageTopics: string[];
  profileSummary?: {
    topTopics: [string, number][];
  };
  weaveTraceUrl?: string;
}

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  picture?: string;
}

export interface AuthState {
  isAuthenticated: boolean;
  user: UserProfile | null;
  token: string | null;
}

export type MessageType =
  | 'ANALYZE_PAGE'
  | 'ANALYSIS_RESULT'
  | 'LOG_EVENT'
  | 'GET_AUTH_STATE'
  | 'AUTH_STATE'
  | 'LOGIN'
  | 'LOGOUT'
  | 'PREFERENCES_UPDATED'
  | 'REFRESH_ANALYSIS'
  | 'VOICE_SESSION_COMPLETE';

export interface Message {
  type: MessageType;
  payload?: any;
}
