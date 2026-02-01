/**
 * InterestLens Content Script
 * Extracts page items and renders overlays
 */

import type { PageItem, ScoredItem, DOMOutline } from '../shared/types';

const HIGHLIGHT_CLASS = 'interestlens-highlight';
const BADGE_CLASS = 'interestlens-badge';

let currentItems: Map<string, { element: HTMLElement; item: PageItem }> = new Map();
let scoredItems: ScoredItem[] = [];
let isAnalyzing = false;

// Listen for messages from service worker (for preference updates)
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'REFRESH_ANALYSIS') {
    console.log('InterestLens: Received refresh request - preferences updated');
    // Re-analyze the page with new preferences
    extractAndAnalyze();
    sendResponse({ success: true });
  }
  return true;
});

// Listen for BroadcastChannel messages (cross-tab communication)
try {
  const preferencesChannel = new BroadcastChannel('interestlens_preferences');
  preferencesChannel.onmessage = (event) => {
    if (event.data.type === 'PREFERENCES_UPDATED') {
      console.log('InterestLens: Received preferences update via BroadcastChannel');
      extractAndAnalyze();
    }
  };
} catch (err) {
  // BroadcastChannel not supported
}

// Listen for localStorage changes (fallback for cross-tab communication)
window.addEventListener('storage', (event) => {
  if (event.key === 'interestlens_preferences_updated' && event.newValue) {
    console.log('InterestLens: Received preferences update via localStorage');
    extractAndAnalyze();
  }
});

// Initialize on page load
initialize();

async function initialize() {
  // Wait for page to be ready
  if (document.readyState !== 'complete') {
    window.addEventListener('load', () => extractAndAnalyze());
  } else {
    extractAndAnalyze();
  }
}

async function extractAndAnalyze() {
  // Prevent concurrent analyses
  if (isAnalyzing) {
    console.log('InterestLens: Analysis already in progress, skipping');
    return;
  }

  isAnalyzing = true;

  try {
    // Extract items from the page
    const items = extractPageItems();
    const domOutline = extractDOMOutline();

    if (items.length === 0) {
      console.log('InterestLens: No items found on page');
      return;
    }

    console.log(`InterestLens: Found ${items.length} items, analyzing...`);

  // Store items for later reference
  items.forEach((item) => {
    const element = document.querySelector(`[data-interestlens-id="${item.id}"]`);
    if (element) {
      currentItems.set(item.id, { element: element as HTMLElement, item });
    }
  });

    // Send to background for analysis
    try {
      const response = await chrome.runtime.sendMessage({
        type: 'ANALYZE_PAGE',
        payload: {
          pageUrl: window.location.href,
          domOutline,
          items,
        },
      });

      if (response.success) {
        scoredItems = response.data.items;
        renderHighlights(scoredItems);
        console.log('InterestLens: Analysis complete, highlights rendered');
      } else {
        console.error('InterestLens: Analysis failed', response.error);
      }
    } catch (error) {
      console.error('InterestLens: Error communicating with background', error);
    }
  } finally {
    isAnalyzing = false;
  }
}

function extractPageItems(): PageItem[] {
  const items: PageItem[] = [];
  const seenTexts = new Set<string>();

  // Find all clickable elements with text content
  const selectors = [
    'a[href]',
    'article',
    '[role="article"]',
    '.post',
    '.card',
    '.item',
    '.story',
    '.entry',
  ];

  const elements = document.querySelectorAll(selectors.join(', '));

  elements.forEach((el, index) => {
    const element = el as HTMLElement;

    // Skip if too small or hidden
    const rect = element.getBoundingClientRect();
    if (rect.width < 50 || rect.height < 20) return;
    if (rect.top > window.innerHeight * 3) return; // Skip items too far below

    // Get text content
    const text = element.textContent?.trim().slice(0, 200) || '';
    if (text.length < 10) return;
    if (seenTexts.has(text)) return;
    seenTexts.add(text);

    // Get link href
    const href = element.tagName === 'A'
      ? (element as HTMLAnchorElement).href
      : element.querySelector('a')?.href || null;

    // Generate ID and mark element
    const id = `item_${index}`;
    element.setAttribute('data-interestlens-id', id);

    items.push({
      id,
      href,
      text,
      snippet: text.slice(0, 100),
      bbox: [rect.x, rect.y, rect.width, rect.height],
      thumbnailBase64: null, // TODO: Extract thumbnails
    });
  });

  return items.slice(0, 50); // Limit to 50 items
}

function extractDOMOutline(): DOMOutline {
  const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
    .slice(0, 10)
    .map((el) => el.textContent?.trim() || '')
    .filter(Boolean);

  const mainContent = document.querySelector('main, article, [role="main"]');
  const mainTextExcerpt = mainContent?.textContent?.slice(0, 500) || '';

  return {
    title: document.title,
    headings,
    mainTextExcerpt,
  };
}

function renderHighlights(items: ScoredItem[]) {
  // Clear existing highlights
  document.querySelectorAll(`.${HIGHLIGHT_CLASS}`).forEach((el) => {
    el.classList.remove(HIGHLIGHT_CLASS);
  });
  document.querySelectorAll(`.${BADGE_CLASS}`).forEach((el) => {
    el.remove();
  });

  // Highlight top 5 items
  const topItems = items.slice(0, 5);

  topItems.forEach((scoredItem, rank) => {
    const itemData = currentItems.get(scoredItem.id);
    if (!itemData) return;

    const { element } = itemData;

    // Add highlight class
    element.classList.add(HIGHLIGHT_CLASS);
    element.style.setProperty('--interestlens-rank', String(rank + 1));

    // Create score badge
    const badge = document.createElement('div');
    badge.className = BADGE_CLASS;
    badge.textContent = String(scoredItem.score);
    badge.title = `${scoredItem.topics.join(', ')}\n${scoredItem.why}`;

    // Position badge
    element.style.position = 'relative';
    element.appendChild(badge);

    // Add click listener for learning
    element.addEventListener('click', () => handleItemClick(scoredItem), { once: true });
  });
}

async function handleItemClick(item: ScoredItem) {
  console.log('InterestLens: Item clicked', item.id);

  try {
    await chrome.runtime.sendMessage({
      type: 'LOG_EVENT',
      payload: {
        event: 'click',
        itemId: item.id,
        pageUrl: window.location.href,
        itemData: {
          text: currentItems.get(item.id)?.item.text || '',
          topics: item.topics,
        },
      },
    });
  } catch (error) {
    console.error('InterestLens: Error logging click', error);
  }
}

// Re-analyze when page content changes significantly
const observer = new MutationObserver((mutations) => {
  const hasSignificantChanges = mutations.some(
    (m) => m.addedNodes.length > 5 || m.removedNodes.length > 5
  );
  if (hasSignificantChanges) {
    // Debounce re-analysis
    setTimeout(extractAndAnalyze, 1000);
  }
});

observer.observe(document.body, {
  childList: true,
  subtree: true,
});
