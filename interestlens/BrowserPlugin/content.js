/**
 * InterestLens Content Script
 *
 * Creates the sidebar UI with shadow DOM isolation.
 * Handles sidebar toggle, resize, and communication.
 */

(() => {
  // Aggressive cleanup of old sidebars
  const cleanup = () => {
    const selectorsToRemove = [
      '#interestlens-sidebar-host',
      '[data-interestlens-sidebar]',
      '[id*="interestlens"]',
      '#interestlens-page-style'
    ];

    selectorsToRemove.forEach(selector => {
      try {
        document.querySelectorAll(selector).forEach(el => el.remove());
      } catch (e) {}
    });

    if (window.__interestLensSidebar) {
      try {
        if (window.__interestLensSidebar.observer) {
          window.__interestLensSidebar.observer.disconnect();
        }
      } catch (e) {}
      window.__interestLensSidebar = null;
    }

    delete window.__interestLensSidebar_v2__;
  };

  cleanup();

  // Version marker to prevent re-initialization
  const VERSION_KEY = '__IL_SIDEBAR_V3__';
  if (window[VERSION_KEY]) {
    return;
  }
  window[VERSION_KEY] = Date.now();

  // SVG Icons
  const ICONS = {
    eye: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
    refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>`,
    chevronLeft: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>`,
    chevronRight: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>`,
    mic: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`,
    check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`,
    alert: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
    warning: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    empty: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
    sparkles: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l1.912 5.813L20 10l-6.088 1.187L12 17l-1.912-5.813L4 10l6.088-1.187L12 3z"/></svg>`
  };

  // State
  let isCollapsed = false;
  let currentWidth = 360;

  // Create main container
  const host = document.createElement("div");
  host.id = "interestlens-sidebar-host";
  host.setAttribute("data-interestlens-sidebar", "v3");

  // Create collapse toggle button
  const toggleBtn = document.createElement("button");
  toggleBtn.id = "il-toggle-btn";
  toggleBtn.innerHTML = ICONS.chevronRight;
  toggleBtn.setAttribute("aria-label", "Toggle sidebar");

  // Toggle button styles
  Object.assign(toggleBtn.style, {
    position: 'fixed',
    top: '50%',
    right: '0',
    transform: 'translateY(-50%)',
    zIndex: '2147483647',
    width: '24px',
    height: '48px',
    border: 'none',
    borderRadius: '8px 0 0 8px',
    background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)',
    color: 'white',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '-2px 0 8px rgba(0,0,0,0.2)',
    transition: 'all 0.2s ease',
    padding: '0'
  });

  // Host styles
  Object.assign(host.style, {
    position: 'fixed',
    top: '0',
    right: '0',
    width: '360px',
    height: '100vh',
    zIndex: '2147483646',
    margin: '0',
    padding: '0',
    border: '0',
    transition: 'transform 0.3s ease'
  });

  const shadowRoot = host.attachShadow({ mode: "open" });

  // Load CSS
  const styleLink = document.createElement("link");
  styleLink.rel = "stylesheet";
  styleLink.href = chrome.runtime.getURL("sidebar.css");

  // Main wrapper
  const wrapper = document.createElement("div");
  wrapper.className = "il-sidebar";

  // Header
  const header = document.createElement("div");
  header.className = "il-header";
  header.innerHTML = `
    <div class="il-logo">${ICONS.eye}</div>
    <div class="il-title">InterestLens</div>
    <div class="il-header-actions">
      <button class="il-btn" id="il-refresh-btn" type="button" aria-label="Refresh">${ICONS.refresh}</button>
    </div>
  `;

  // Stats section
  const stats = document.createElement("div");
  stats.className = "il-stats";
  stats.innerHTML = `
    <div class="il-stat-card">
      <div class="il-stat-value" id="il-stat-avg">--</div>
      <div class="il-stat-label">Avg Score</div>
    </div>
    <div class="il-stat-card">
      <div class="il-stat-value" id="il-stat-count">0</div>
      <div class="il-stat-label">Items</div>
    </div>
    <div class="il-stat-card">
      <div class="il-stat-value il-stat-good" id="il-stat-verified">0</div>
      <div class="il-stat-label">Matches</div>
    </div>
  `;

  // Body
  const body = document.createElement("div");
  body.className = "il-body";

  // Voice Section
  const voiceSection = document.createElement("div");
  voiceSection.className = "il-voice-section";
  voiceSection.innerHTML = `
    <button class="il-voice-btn" id="il-voice-btn" type="button">
      <span class="il-voice-icon">${ICONS.mic}</span>
      <span>Ask InterestLens</span>
    </button>
    <div class="il-voice-status" id="il-voice-status"></div>
  `;

  // Assemble
  wrapper.appendChild(header);
  wrapper.appendChild(stats);
  wrapper.appendChild(body);
  wrapper.appendChild(voiceSection);
  shadowRoot.appendChild(styleLink);
  shadowRoot.appendChild(wrapper);

  // Page margin style
  const pageStyle = document.createElement("style");
  pageStyle.id = "interestlens-page-style";
  pageStyle.textContent = `
    body { margin-right: 360px !important; transition: margin-right 0.3s ease; }
  `;

  // Toggle function
  const toggleSidebar = () => {
    isCollapsed = !isCollapsed;

    if (isCollapsed) {
      host.style.transform = 'translateX(100%)';
      toggleBtn.innerHTML = ICONS.chevronLeft;
      toggleBtn.style.right = '0';
      pageStyle.textContent = `body { margin-right: 0 !important; transition: margin-right 0.3s ease; }`;
    } else {
      host.style.transform = 'translateX(0)';
      toggleBtn.innerHTML = ICONS.chevronRight;
      toggleBtn.style.right = '360px';
      pageStyle.textContent = `body { margin-right: 360px !important; transition: margin-right 0.3s ease; }`;
    }
  };

  // Attach to DOM
  document.documentElement.appendChild(host);
  document.documentElement.appendChild(toggleBtn);
  document.head.appendChild(pageStyle);

  // Position toggle button
  toggleBtn.style.right = '360px';

  // Toggle button click
  toggleBtn.addEventListener("click", toggleSidebar);

  // Get references
  const refreshBtn = shadowRoot.getElementById("il-refresh-btn");
  const voiceBtn = shadowRoot.getElementById("il-voice-btn");
  const voiceStatus = shadowRoot.getElementById("il-voice-status");

  // Update voice status
  const updateVoiceStatus = (message) => {
    if (voiceStatus) {
      voiceStatus.textContent = message;
      voiceStatus.classList.add("il-visible");
      setTimeout(() => voiceStatus.classList.remove("il-visible"), 3000);
    }
  };

  // Update stats
  const updateStats = (avgScore, count, verified) => {
    const avgEl = shadowRoot.getElementById("il-stat-avg");
    const countEl = shadowRoot.getElementById("il-stat-count");
    const verifiedEl = shadowRoot.getElementById("il-stat-verified");

    if (avgEl) {
      avgEl.textContent = avgScore !== null && avgScore !== undefined ? avgScore.toFixed(0) : "--";
      avgEl.className = "il-stat-value";
      if (avgScore !== null && avgScore !== undefined) {
        if (avgScore >= 80) avgEl.classList.add("il-stat-good");
        else if (avgScore >= 50) avgEl.classList.add("il-stat-warning");
        else avgEl.classList.add("il-stat-danger");
      }
    }
    if (countEl) countEl.textContent = count;
    if (verifiedEl) verifiedEl.textContent = verified;
  };

  // Expose API
  window.__interestLensSidebar = {
    host,
    shadowRoot,
    body,
    refreshBtn,
    voiceBtn,
    voiceStatus,
    toggleBtn,
    isCollapsed: () => isCollapsed,
    toggle: toggleSidebar,
    updateVoiceStatus,
    updateStats,
    ICONS
  };

  // Keyboard shortcut
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "s") {
      e.preventDefault();
      toggleSidebar();
    }
  });

  // Scroll handling in sidebar
  host.addEventListener("wheel", (e) => {
    const path = e.composedPath ? e.composedPath() : [];
    if (path.includes(body) || path.includes(wrapper)) {
      e.preventDefault();
      e.stopPropagation();
      body.scrollBy({ top: e.deltaY, behavior: "auto" });
    }
  }, { passive: false, capture: true });

  // Listen for messages
  try {
    chrome.runtime.onMessage.addListener((msg, sender, respond) => {
      if (msg?.type === "interestlens:toggle-sidebar") {
        toggleSidebar();
        respond({ ok: true });
        return true;
      }
    });
  } catch (e) {
    console.warn("Could not add message listener:", e);
  }
})();
