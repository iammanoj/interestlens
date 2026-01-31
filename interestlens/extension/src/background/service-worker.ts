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
chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  if (message.type === 'AUTH_SUCCESS') {
    handleAuthSuccess(message.payload);
    sendResponse({ success: true });
  }
});

async function handleMessage(
  message: Message,
  sender: chrome.runtime.MessageSender,
  sendResponse: (response: any) => void
) {
  switch (message.type) {
    case 'ANALYZE_PAGE':
      try {
        const result = await analyzePageAPI(
          message.payload as AnalyzeRequest,
          authState.token
        );
        sendResponse({ success: true, data: result });
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

    default:
      sendResponse({ success: false, error: 'Unknown message type' });
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
