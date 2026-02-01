/**
 * InterestLens Activity Tracker
 *
 * Tracks user browsing activity including:
 * - URL visits and time spent
 * - Click interactions on links/articles
 * - Content categories detected on pages
 *
 * Data is synced to the backend for personalization.
 */

(() => {
  // Prevent duplicate initialization
  if (window.__IL_TRACKER_INIT__) return;
  window.__IL_TRACKER_INIT__ = true;

  const BACKEND_URL = 'http://localhost:8001';
  const SYNC_INTERVAL = 30000; // Sync every 30 seconds
  const STORAGE_KEY = 'interestlens_activity_buffer';
  const SESSION_KEY = 'interestlens_current_session';

  // Activity buffer for batching
  let activityBuffer = [];
  let currentPageSession = null;
  let syncTimer = null;
  let isPageVisible = true;

  /**
   * Initialize tracking for current page
   */
  function initPageSession() {
    const now = Date.now();

    currentPageSession = {
      url: window.location.href,
      domain: window.location.hostname,
      title: document.title,
      startTime: now,
      lastActiveTime: now,
      totalActiveTime: 0,
      scrollDepth: 0,
      clicks: [],
      detectedCategories: [],
      isArticle: detectIfArticlePage()
    };

    // Save to session storage for recovery
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(currentPageSession));
    } catch (e) {
      // Session storage might be blocked
    }
  }

  /**
   * Detect if current page is an article/content page
   */
  function detectIfArticlePage() {
    // Check for common article indicators
    const articleIndicators = [
      document.querySelector('article'),
      document.querySelector('[role="article"]'),
      document.querySelector('.post-content'),
      document.querySelector('.article-content'),
      document.querySelector('.entry-content'),
      document.querySelector('main p')
    ];

    return articleIndicators.some(el => el !== null);
  }

  /**
   * Extract potential content categories from page
   */
  function extractPageCategories() {
    const categories = new Set();

    // Get meta keywords
    const metaKeywords = document.querySelector('meta[name="keywords"]');
    if (metaKeywords) {
      metaKeywords.content.split(',').forEach(kw => {
        const trimmed = kw.trim().toLowerCase();
        if (trimmed && trimmed.length < 30) {
          categories.add(trimmed);
        }
      });
    }

    // Get Open Graph tags
    const ogType = document.querySelector('meta[property="og:type"]');
    if (ogType) {
      categories.add(ogType.content.toLowerCase());
    }

    // Get article tags/categories from common selectors
    const categorySelectors = [
      '[rel="tag"]',
      '.category',
      '.tag',
      '.topic',
      '[data-category]',
      '.post-category',
      '.article-category'
    ];

    categorySelectors.forEach(selector => {
      document.querySelectorAll(selector).forEach(el => {
        const text = el.textContent?.trim().toLowerCase();
        if (text && text.length < 30 && text.length > 2) {
          categories.add(text);
        }
      });
    });

    // Extract from URL path
    const pathParts = window.location.pathname.split('/').filter(p => p.length > 2);
    const commonCategories = [
      'news', 'tech', 'technology', 'science', 'sports', 'business',
      'entertainment', 'politics', 'health', 'finance', 'travel',
      'food', 'lifestyle', 'culture', 'ai', 'machine-learning', 'startup'
    ];

    pathParts.forEach(part => {
      const normalized = part.toLowerCase().replace(/-/g, ' ');
      if (commonCategories.some(c => normalized.includes(c))) {
        categories.add(normalized);
      }
    });

    return Array.from(categories).slice(0, 10); // Limit to 10 categories
  }

  /**
   * Track a click on a link or article
   */
  function trackClick(event) {
    // Find the closest link
    const link = event.target.closest('a');
    if (!link) return;

    const href = link.href;
    if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;

    // Get link text/title
    const text = link.textContent?.trim()?.substring(0, 200) || '';
    const title = link.title || link.getAttribute('aria-label') || '';

    // Check if it's likely an article link
    const isArticleLink = link.closest('article, .post, .card, .item, [role="article"]') !== null;

    const clickData = {
      timestamp: Date.now(),
      url: href,
      text: text,
      title: title,
      isArticleLink: isArticleLink,
      position: {
        x: event.clientX,
        y: event.clientY
      }
    };

    if (currentPageSession) {
      currentPageSession.clicks.push(clickData);
    }

    // Add to activity buffer
    addToBuffer({
      type: 'click',
      data: clickData,
      sourceUrl: window.location.href,
      sourceDomain: window.location.hostname
    });
  }

  /**
   * Track scroll depth
   */
  function trackScroll() {
    if (!currentPageSession) return;

    const scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
    if (scrollHeight <= 0) return;

    const currentDepth = Math.round((window.scrollY / scrollHeight) * 100);

    if (currentDepth > currentPageSession.scrollDepth) {
      currentPageSession.scrollDepth = currentDepth;
    }
  }

  /**
   * Update active time tracking
   */
  function updateActiveTime() {
    if (!currentPageSession || !isPageVisible) return;

    const now = Date.now();
    const elapsed = now - currentPageSession.lastActiveTime;

    // Only count if under 5 minutes (avoid counting idle time)
    if (elapsed < 300000) {
      currentPageSession.totalActiveTime += elapsed;
    }

    currentPageSession.lastActiveTime = now;
  }

  /**
   * Handle page visibility changes
   */
  function handleVisibilityChange() {
    isPageVisible = !document.hidden;

    if (isPageVisible) {
      // Page became visible - update last active time
      if (currentPageSession) {
        currentPageSession.lastActiveTime = Date.now();
      }
    } else {
      // Page hidden - save current session state
      updateActiveTime();
      saveSessionState();
    }
  }

  /**
   * Save current session state to storage
   */
  function saveSessionState() {
    if (!currentPageSession) return;

    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(currentPageSession));
    } catch (e) {
      // Ignore storage errors
    }
  }

  /**
   * Add activity to buffer
   */
  function addToBuffer(activity) {
    activityBuffer.push({
      ...activity,
      timestamp: Date.now()
    });

    // Save buffer to local storage
    try {
      chrome.storage.local.set({ [STORAGE_KEY]: activityBuffer });
    } catch (e) {
      // Fallback to localStorage
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(activityBuffer));
      } catch (e2) {
        // Ignore storage errors
      }
    }
  }

  /**
   * Sync activity buffer to backend
   */
  async function syncToBackend() {
    // Update time before sync
    updateActiveTime();

    // Prepare page visit data
    if (currentPageSession) {
      currentPageSession.detectedCategories = extractPageCategories();

      addToBuffer({
        type: 'page_visit',
        data: {
          url: currentPageSession.url,
          domain: currentPageSession.domain,
          title: currentPageSession.title,
          timeSpent: currentPageSession.totalActiveTime,
          scrollDepth: currentPageSession.scrollDepth,
          isArticle: currentPageSession.isArticle,
          categories: currentPageSession.detectedCategories,
          clickCount: currentPageSession.clicks.length
        },
        sourceUrl: currentPageSession.url,
        sourceDomain: currentPageSession.domain
      });
    }

    if (activityBuffer.length === 0) return;

    const bufferToSync = [...activityBuffer];
    activityBuffer = [];

    try {
      const response = await fetch(`${BACKEND_URL}/activity/track`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          activities: bufferToSync,
          client_timestamp: Date.now()
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      // Clear synced buffer from storage
      try {
        chrome.storage.local.remove([STORAGE_KEY]);
      } catch (e) {
        localStorage.removeItem(STORAGE_KEY);
      }

    } catch (error) {
      // Only log if it's not a common network error
      if (error.message && !error.message.includes('Failed to fetch') &&
          !error.message.includes('Extension context invalidated')) {
        console.debug('InterestLens: Activity sync deferred', error.message);
      }
      // Put items back in buffer for retry
      activityBuffer = [...bufferToSync, ...activityBuffer];
    }
  }

  /**
   * Load any buffered activity from storage
   */
  async function loadBufferedActivity() {
    try {
      const result = await new Promise(resolve => {
        chrome.storage.local.get([STORAGE_KEY], resolve);
      });

      if (result[STORAGE_KEY]) {
        activityBuffer = result[STORAGE_KEY];
      }
    } catch (e) {
      // Try localStorage fallback
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          activityBuffer = JSON.parse(stored);
        }
      } catch (e2) {
        // Ignore errors
      }
    }
  }

  /**
   * Handle page unload - sync remaining data
   */
  function handleUnload() {
    updateActiveTime();

    if (currentPageSession) {
      currentPageSession.detectedCategories = extractPageCategories();

      // Use sendBeacon for reliable delivery on unload
      const payload = JSON.stringify({
        activities: [{
          type: 'page_visit',
          timestamp: Date.now(),
          data: {
            url: currentPageSession.url,
            domain: currentPageSession.domain,
            title: currentPageSession.title,
            timeSpent: currentPageSession.totalActiveTime,
            scrollDepth: currentPageSession.scrollDepth,
            isArticle: currentPageSession.isArticle,
            categories: currentPageSession.detectedCategories,
            clickCount: currentPageSession.clicks.length
          },
          sourceUrl: currentPageSession.url,
          sourceDomain: currentPageSession.domain
        }, ...activityBuffer],
        client_timestamp: Date.now()
      });

      navigator.sendBeacon(`${BACKEND_URL}/activity/track`, payload);
    }
  }

  /**
   * Initialize tracker
   */
  async function init() {
    // Check if user has completed onboarding before tracking
    const result = await new Promise(resolve => {
      chrome.storage.local.get(['interestlens_onboarded'], resolve);
    });

    if (!result.interestlens_onboarded) {
      // Don't track until onboarded
      return;
    }

    // Load any buffered activity
    await loadBufferedActivity();

    // Initialize page session
    initPageSession();

    // Set up event listeners
    document.addEventListener('click', trackClick, { capture: true, passive: true });
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('scroll', throttle(trackScroll, 1000), { passive: true });
    window.addEventListener('beforeunload', handleUnload);

    // Set up periodic sync
    syncTimer = setInterval(syncToBackend, SYNC_INTERVAL);

    // Initial sync of any buffered data
    if (activityBuffer.length > 0) {
      setTimeout(syncToBackend, 5000);
    }
  }

  /**
   * Throttle helper
   */
  function throttle(fn, wait) {
    let lastTime = 0;
    return function(...args) {
      const now = Date.now();
      if (now - lastTime >= wait) {
        lastTime = now;
        fn.apply(this, args);
      }
    };
  }

  // Initialize
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose for debugging
  window.__interestLensTracker = {
    getSession: () => currentPageSession,
    getBuffer: () => activityBuffer,
    sync: syncToBackend,
    extractCategories: extractPageCategories
  };
})();
