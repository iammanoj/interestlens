/**
 * InterestLens Background Service Worker
 *
 * Handles:
 * - API requests to backend
 * - Voice session management
 * - Activity tracking coordination
 * - Keyboard shortcuts
 */

// API endpoints
const SCRAPER_API = "http://localhost:8000";
const BACKEND_API = "http://localhost:8001";

// Send message to content script
const sendToTab = async (tabId, message) => {
  try {
    return await chrome.tabs.sendMessage(tabId, message);
  } catch (error) {
    console.warn("Failed to send message to tab:", error);
    return { ok: false, error: error.message };
  }
};

// Toggle sidebar visibility
const toggleSidebar = async (tabId) => {
  try {
    await chrome.tabs.sendMessage(tabId, {
      type: "interestlens:toggle-sidebar"
    });
  } catch (error) {
    console.warn("Failed to toggle sidebar:", error);
  }
};

// Message handler
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const { type } = message || {};

  // Scrape request
  if (type === "interestlens:scrape") {
    const payload = { url: message.url };
    if (message.refreshCache) {
      payload.refresh_cache = true;
    }

    fetch(`${SCRAPER_API}/scrape`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Status ${response.status}`);
        const data = await response.json();
        sendResponse({ ok: true, data });
      })
      .catch((error) => {
        sendResponse({ ok: false, error: error?.message || "Scrape failed" });
      });

    return true;
  }

  // Authenticity check request
  if (type === "interestlens:authenticity") {
    fetch(`${BACKEND_API}/check_authenticity/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message.payload)
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Status ${response.status}`);
        const data = await response.json();
        sendResponse({ ok: true, data });
      })
      .catch((error) => {
        sendResponse({ ok: false, error: error?.message || "Authenticity check failed" });
      });

    return true;
  }

  // Voice session request
  if (type === "interestlens:voice-session") {
    const userId = message.userId || `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    fetch(`${BACKEND_API}/voice/start-session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId })
    })
      .then(async (response) => {
        if (!response.ok) {
          if (response.status === 401 || response.status === 403) {
            throw new Error("Authentication required");
          }
          throw new Error(`Status ${response.status}`);
        }
        const data = await response.json();
        sendResponse({ ok: true, data });
      })
      .catch((error) => {
        sendResponse({
          ok: false,
          error: error?.message || "Voice session failed",
          fallback: "web-speech-api"
        });
      });

    return true;
  }

  // Activity tracking request
  if (type === "interestlens:track-activity") {
    fetch(`${BACKEND_API}/activity/track`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message.payload)
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Status ${response.status}`);
        const data = await response.json();
        sendResponse({ ok: true, data });
      })
      .catch((error) => {
        sendResponse({ ok: false, error: error?.message || "Activity tracking failed" });
      });

    return true;
  }

  // Get user interests
  if (type === "interestlens:get-interests") {
    fetch(`${BACKEND_API}/voice/preferences`, {
      method: "GET",
      headers: { "Content-Type": "application/json" }
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Status ${response.status}`);
        const data = await response.json();
        sendResponse({ ok: true, data });
      })
      .catch((error) => {
        sendResponse({ ok: false, error: error?.message || "Failed to get interests" });
      });

    return true;
  }

  // DOM action request
  if (type === "interestlens:execute-dom-action") {
    const { action, params } = message;

    chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
      if (tabs.length > 0) {
        const result = await sendToTab(tabs[0].id, {
          type: "interestlens:dom-action",
          action,
          params
        });
        sendResponse(result);
      } else {
        sendResponse({ ok: false, error: "No active tab" });
      }
    });

    return true;
  }

  return false;
});

// Handle keyboard shortcuts
chrome.commands?.onCommand?.addListener((command) => {
  if (command === "toggle-sidebar") {
    chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
      if (tabs.length > 0) {
        await toggleSidebar(tabs[0].id);
      }
    });
  }
});

// Listen for install/update events
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    console.log("InterestLens installed");
    // Could open welcome page here
  } else if (details.reason === "update") {
    console.log(`InterestLens updated to ${chrome.runtime.getManifest().version}`);
  }
});

// Handle extension icon click
chrome.action?.onClicked?.addListener(async (tab) => {
  await toggleSidebar(tab.id);
});
