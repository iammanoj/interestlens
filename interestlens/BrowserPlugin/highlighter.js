/**
 * InterestLens Content Highlighter
 *
 * Detects content items on any webpage and highlights
 * those matching user's interests from voice onboarding
 * and tracked activity.
 */

(() => {
  // Prevent duplicate initialization
  if (window.__IL_HIGHLIGHTER_INIT__) return;
  window.__IL_HIGHLIGHTER_INIT__ = true;

  const BACKEND_URL = 'http://localhost:8001';
  const HIGHLIGHT_CHECK_INTERVAL = 2000; // Check for new content every 2 seconds
  const CACHE_DURATION = 300000; // 5 minutes cache

  // State
  let userInterests = null;
  let highlightedElements = new Set();
  let isHighlightingEnabled = true;
  let lastInterestsFetch = 0;
  let observer = null;
  let highlightStats = { total: 0, matched: 0 };

  /**
   * Inject highlighter CSS
   */
  function injectStyles() {
    if (document.getElementById('il-highlighter-styles')) return;

    const link = document.createElement('link');
    link.id = 'il-highlighter-styles';
    link.rel = 'stylesheet';
    link.href = chrome.runtime.getURL('highlighter.css');
    document.head.appendChild(link);
  }

  /**
   * Fetch user interests from backend
   */
  async function fetchUserInterests(forceRefresh = false) {
    const now = Date.now();

    // Use cached interests if available
    if (!forceRefresh && userInterests && (now - lastInterestsFetch) < CACHE_DURATION) {
      return userInterests;
    }

    try {
      const response = await fetch(`${BACKEND_URL}/voice/preferences`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();

      // Extract categories from the response
      userInterests = {
        likes: [],
        dislikes: [],
        topicAffinities: {}
      };

      // Parse from extracted_categories
      if (data.extracted_categories) {
        if (data.extracted_categories.likes) {
          userInterests.likes = data.extracted_categories.likes.map(l =>
            typeof l === 'string' ? l.toLowerCase() : (l.category || '').toLowerCase()
          ).filter(Boolean);
        }
        if (data.extracted_categories.dislikes) {
          userInterests.dislikes = data.extracted_categories.dislikes.map(d =>
            typeof d === 'string' ? d.toLowerCase() : (d.category || '').toLowerCase()
          ).filter(Boolean);
        }
      }

      // Also parse from preferences.topics
      if (data.preferences?.topics) {
        data.preferences.topics.forEach(topic => {
          const name = topic.topic?.toLowerCase();
          if (!name) return;

          if (topic.sentiment === 'like') {
            if (!userInterests.likes.includes(name)) {
              userInterests.likes.push(name);
            }
            userInterests.topicAffinities[name] = topic.intensity || 0.8;
          } else if (topic.sentiment === 'dislike') {
            if (!userInterests.dislikes.includes(name)) {
              userInterests.dislikes.push(name);
            }
            userInterests.topicAffinities[name] = -(topic.intensity || 0.8);
          }
        });
      }

      lastInterestsFetch = now;
      return userInterests;

    } catch (error) {
      console.warn('InterestLens: Failed to fetch interests', error);
      return userInterests || { likes: [], dislikes: [], topicAffinities: {} };
    }
  }

  /**
   * Find content elements on the page
   */
  function findContentElements() {
    const elements = [];

    // Common selectors for content items
    const selectors = [
      'article',
      '[role="article"]',
      '.post',
      '.card',
      '.item',
      '.story',
      '.entry',
      '.article',
      '.news-item',
      '.feed-item',
      'h1 a',
      'h2 a',
      'h3 a',
      '.title a',
      '.headline a',
      'a[href*="/article"]',
      'a[href*="/post"]',
      'a[href*="/story"]',
      'a[href*="/news"]'
    ];

    // Find elements matching selectors
    selectors.forEach(selector => {
      try {
        document.querySelectorAll(selector).forEach(el => {
          // Skip if already processed or is navigation/header
          if (highlightedElements.has(el)) return;
          if (el.closest('nav, header, footer, aside, .sidebar, .menu')) return;
          if (el.closest('#interestlens-sidebar-host')) return;

          // Must have meaningful text
          const text = extractText(el);
          if (text.length < 20) return;

          elements.push({
            element: el,
            text: text,
            url: el.href || el.querySelector('a')?.href || ''
          });
        });
      } catch (e) {
        // Ignore selector errors
      }
    });

    return elements;
  }

  /**
   * Extract text content from an element
   */
  function extractText(element) {
    // Get text from headings first
    const heading = element.querySelector('h1, h2, h3, h4, .title, .headline');
    if (heading) {
      return heading.textContent?.trim() || '';
    }

    // Fall back to element text
    return element.textContent?.trim().substring(0, 500) || '';
  }

  /**
   * Calculate interest match score for content
   */
  function calculateMatchScore(text, interests) {
    if (!interests || (!interests.likes.length && !interests.dislikes.length)) {
      return { score: 0, matchedCategories: [], isDisliked: false };
    }

    const textLower = text.toLowerCase();
    const matchedCategories = [];
    let score = 0;
    let isDisliked = false;

    // Check for liked categories
    interests.likes.forEach(category => {
      if (textLower.includes(category) ||
          textMatches(textLower, category)) {
        score += (interests.topicAffinities[category] || 0.5) * 50;
        matchedCategories.push(category);
      }
    });

    // Check for disliked categories (negative score)
    interests.dislikes.forEach(category => {
      if (textLower.includes(category) ||
          textMatches(textLower, category)) {
        score -= 30;
        isDisliked = true;
      }
    });

    // Normalize score to 0-100
    score = Math.max(0, Math.min(100, score));

    return { score, matchedCategories, isDisliked };
  }

  /**
   * Check if text matches category with fuzzy matching
   */
  function textMatches(text, category) {
    // Handle multi-word categories
    const words = category.split(/\s+/);
    if (words.length > 1) {
      return words.every(word => text.includes(word));
    }

    // Check for word boundaries
    const regex = new RegExp(`\\b${escapeRegex(category)}\\b`, 'i');
    return regex.test(text);
  }

  /**
   * Escape regex special characters
   */
  function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  /**
   * Apply highlight to an element
   */
  function applyHighlight(element, score, matchedCategories, isDisliked) {
    if (highlightedElements.has(element)) return;

    highlightedElements.add(element);
    highlightStats.total++;

    // Add base highlight class
    element.classList.add('il-highlight');

    if (isDisliked) {
      element.classList.add('il-highlight-low', 'il-disliked');
      return;
    }

    if (score >= 50) {
      highlightStats.matched++;

      if (score >= 80) {
        element.classList.add('il-highlight-high');
      } else {
        element.classList.add('il-highlight-medium');
      }

      // Add category tooltip
      if (matchedCategories.length > 0) {
        const tooltip = document.createElement('span');
        tooltip.className = 'il-category-tooltip';
        tooltip.textContent = matchedCategories.slice(0, 3).join(', ');

        // Position relative to element
        element.style.position = element.style.position || 'relative';
        element.appendChild(tooltip);
      }

      // Add interest badge for high scores
      if (score >= 70 && !element.querySelector('.il-interest-badge')) {
        const badge = document.createElement('span');
        badge.className = `il-interest-badge ${score >= 80 ? '' : 'green'}`;
        badge.textContent = score >= 80 ? 'For You' : 'Match';

        element.style.position = element.style.position || 'relative';
        element.appendChild(badge);
      }

      // Add animation class
      element.classList.add('il-highlight-animated');
      setTimeout(() => {
        element.classList.remove('il-highlight-animated');
      }, 300);
    }
  }

  /**
   * Remove highlight from an element
   */
  function removeHighlight(element) {
    element.classList.remove(
      'il-highlight',
      'il-highlight-high',
      'il-highlight-medium',
      'il-highlight-low',
      'il-disliked',
      'il-highlight-animated'
    );

    // Remove badges and tooltips
    element.querySelectorAll('.il-interest-badge, .il-category-tooltip').forEach(el => el.remove());

    highlightedElements.delete(element);
  }

  /**
   * Process and highlight content on the page
   */
  async function processContent() {
    if (!isHighlightingEnabled) return;

    // Check if user is onboarded
    const result = await new Promise(resolve => {
      chrome.storage.local.get(['interestlens_onboarded'], resolve);
    });

    if (!result.interestlens_onboarded) return;

    // Fetch user interests
    const interests = await fetchUserInterests();

    if (!interests.likes.length && !interests.dislikes.length) {
      // No interests set yet
      return;
    }

    // Find content elements
    const elements = findContentElements();

    // Process each element
    elements.forEach(({ element, text }) => {
      const { score, matchedCategories, isDisliked } = calculateMatchScore(text, interests);

      if (score > 0 || isDisliked) {
        applyHighlight(element, score, matchedCategories, isDisliked);
      }
    });

    // Update stats in sidebar if available
    updateSidebarStats();
  }

  /**
   * Update stats in the sidebar
   */
  function updateSidebarStats() {
    // This will integrate with the sidebar API
    if (window.__interestLensSidebar?.updateStats) {
      // We can add a method to show interest matches
    }
  }

  /**
   * Toggle highlighting on/off
   */
  function toggleHighlighting(enabled) {
    isHighlightingEnabled = enabled;

    if (!enabled) {
      document.body.classList.add('il-highlights-disabled');
    } else {
      document.body.classList.remove('il-highlights-disabled');
      processContent();
    }

    // Save preference
    chrome.storage.local.set({ 'interestlens_highlighting': enabled });
  }

  /**
   * Create highlight controls
   */
  function createControls() {
    const existingControls = document.getElementById('il-highlight-controls');
    if (existingControls) return;

    const controls = document.createElement('div');
    controls.id = 'il-highlight-controls';
    controls.className = 'il-highlight-controls';
    controls.innerHTML = `
      <label class="il-highlight-toggle">
        <input type="checkbox" id="il-highlight-checkbox" ${isHighlightingEnabled ? 'checked' : ''}>
        <span>Highlights</span>
      </label>
      <span class="il-highlight-stats" id="il-highlight-stats">
        ${highlightStats.matched} matches
      </span>
    `;

    document.body.appendChild(controls);

    // Toggle handler
    document.getElementById('il-highlight-checkbox')?.addEventListener('change', (e) => {
      toggleHighlighting(e.target.checked);
    });
  }

  /**
   * Set up mutation observer for dynamic content
   */
  function setupObserver() {
    if (observer) return;

    observer = new MutationObserver((mutations) => {
      let hasNewContent = false;

      mutations.forEach(mutation => {
        mutation.addedNodes.forEach(node => {
          if (node.nodeType === Node.ELEMENT_NODE) {
            hasNewContent = true;
          }
        });
      });

      if (hasNewContent) {
        // Debounce processing
        clearTimeout(window.__ilHighlightDebounce);
        window.__ilHighlightDebounce = setTimeout(processContent, 500);
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  /**
   * Initialize highlighter
   */
  async function init() {
    // Check if user is onboarded
    const result = await new Promise(resolve => {
      chrome.storage.local.get(['interestlens_onboarded', 'interestlens_highlighting'], resolve);
    });

    if (!result.interestlens_onboarded) return;

    // Load highlighting preference
    if (result.interestlens_highlighting !== undefined) {
      isHighlightingEnabled = result.interestlens_highlighting;
    }

    // Inject styles
    injectStyles();

    // Initial content processing
    await processContent();

    // Set up observer for dynamic content
    setupObserver();

    // Create controls (optional - can be disabled)
    // createControls();

    // Periodic check for new content
    setInterval(processContent, HIGHLIGHT_CHECK_INTERVAL);
  }

  // Initialize when ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    // Delay slightly to ensure other scripts are loaded
    setTimeout(init, 1000);
  }

  // Expose API for debugging and integration
  window.__interestLensHighlighter = {
    refresh: processContent,
    toggle: toggleHighlighting,
    getStats: () => highlightStats,
    getInterests: () => userInterests,
    refreshInterests: () => fetchUserInterests(true)
  };
})();
