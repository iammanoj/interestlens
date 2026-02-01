/**
 * InterestLens Service Worker
 * Handles API calls, auth state, and message passing
 */

import { analyzePageAPI, logEventAPI } from '../shared/api';
import type { Message, AuthState, AnalyzeRequest } from '../shared/types';

// Auth state
let authState: AuthState = {
  isAuthenticated: false,
  user: null,
  token: null,
};

// Initialize auth state from storage
chrome.storage.local.get(['authToken', 'user'], (result) => {
  if (result.authToken && result.user) {
    authState = {
      isAuthenticated: true,
      user: result.user,
      token: result.authToken,
    };
  }
});

// Listen for messages from content script and side panel
chrome.runtime.onMessage.addListener((message: Message, sender, sendResponse) => {
  handleMessage(message, sender, sendResponse);
  return true; // Keep channel open for async response
});

// Listen for messages from web app (login callback)
chrome.runtime.onMessageExternal.addListener((message, _sender, sendResponse) => {
  if (message.type === 'AUTH_SUCCESS') {
    handleAuthSuccess(message.payload);
    sendResponse({ success: true });
  }
});

async function handleMessage(
  message: Message,
  _sender: chrome.runtime.MessageSender,
  sendResponse: (response: any) => void
) {
  console.log('[ServiceWorker] Received message:', message.type);

  switch (message.type) {
    case 'ANALYZE_PAGE':
      console.log('[ServiceWorker] ANALYZE_PAGE received, items:', (message.payload as any)?.items?.length);
      try {
        const result = await analyzePageAPI(
          message.payload as AnalyzeRequest,
          authState.token
        );
        console.log('[ServiceWorker] API call successful');
        sendResponse({ success: true, data: result });

        // Also broadcast to sidepanel and other listeners
        chrome.runtime.sendMessage({
          type: 'ANALYSIS_RESULT',
          payload: result,
        }).catch(() => {
          // Ignore errors if no listeners
        });
      } catch (error) {
        sendResponse({ success: false, error: String(error) });
      }
      break;

    case 'LOG_EVENT':
      if (authState.token) {
        try {
          await logEventAPI(
            message.payload.event,
            message.payload.itemId,
            message.payload.pageUrl,
            message.payload.itemData,
            authState.token
          );
          sendResponse({ success: true });
        } catch (error) {
          sendResponse({ success: false, error: String(error) });
        }
      } else {
        sendResponse({ success: false, error: 'Not authenticated' });
      }
      break;

    case 'GET_AUTH_STATE':
      sendResponse(authState);
      break;

    case 'LOGIN':
      // Open login page
      chrome.tabs.create({
        url: 'https://interestlens.vercel.app/login',
      });
      sendResponse({ success: true });
      break;

    case 'LOGOUT':
      handleLogout();
      sendResponse({ success: true });
      break;

    case 'VOICE_SESSION_COMPLETE':
      // Voice onboarding completed - notify all tabs to refresh
      handleVoiceSessionComplete(message.payload);
      sendResponse({ success: true });
      break;

    case 'PREFERENCES_UPDATED':
      // Preferences were updated - broadcast to all content scripts
      broadcastPreferencesUpdated(message.payload);
      sendResponse({ success: true });
      break;

    default:
      sendResponse({ success: false, error: 'Unknown message type' });
  }
}

/**
 * Handle voice session completion - broadcast refresh to all tabs
 */
async function handleVoiceSessionComplete(payload: any) {
  console.log('[ServiceWorker] Voice session complete, refreshing all tabs');

  // Broadcast to all tabs to refresh their analysis
  broadcastPreferencesUpdated(payload);
}

/**
 * Broadcast preferences update to all tabs
 */
async function broadcastPreferencesUpdated(payload: any) {
  try {
    // Get all tabs
    const tabs = await chrome.tabs.query({});

    // Send refresh message to each tab's content script
    for (const tab of tabs) {
      if (tab.id && tab.url && !tab.url.startsWith('chrome://')) {
        try {
          await chrome.tabs.sendMessage(tab.id, {
            type: 'REFRESH_ANALYSIS',
            payload: {
              reason: 'preferences_updated',
              preferences: payload?.preferences,
              timestamp: Date.now()
            }
          });
          console.log(`[ServiceWorker] Sent refresh to tab ${tab.id}: ${tab.url}`);
        } catch (err) {
          // Tab might not have content script loaded, ignore
        }
      }
    }
  } catch (error) {
    console.error('[ServiceWorker] Error broadcasting preferences update:', error);
  }
}

async function handleAuthSuccess(payload: { token: string; user: any }) {
  authState = {
    isAuthenticated: true,
    user: payload.user,
    token: payload.token,
  };

  // Store in chrome.storage
  await chrome.storage.local.set({
    authToken: payload.token,
    user: payload.user,
  });

  // Notify all tabs
  chrome.runtime.sendMessage({
    type: 'AUTH_STATE',
    payload: authState,
  });
}

async function handleLogout() {
  authState = {
    isAuthenticated: false,
    user: null,
    token: null,
  };

  await chrome.storage.local.remove(['authToken', 'user']);

  chrome.runtime.sendMessage({
    type: 'AUTH_STATE',
    payload: authState,
  });
}

// Open side panel when extension icon is clicked
chrome.action.onClicked.addListener((tab) => {
  if (tab.id) {
    chrome.sidePanel.open({ tabId: tab.id });
  }
});

// Set side panel options
chrome.sidePanel.setOptions({
  enabled: true,
});
