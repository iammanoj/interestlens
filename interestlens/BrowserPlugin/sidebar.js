(() => {
  // Wait for sidebar to be initialized
  const sidebar = window.__interestLensSidebar;
  if (!sidebar) {
    console.log("InterestLens: Waiting for sidebar...");
    return;
  }

  // Prevent duplicate initialization
  if (sidebar._initialized) {
    return;
  }
  sidebar._initialized = true;

  const MAX_CARDS = 12;
  const ICONS = sidebar.ICONS || {};
  const STORAGE_KEY = 'interestlens_onboarded';

  // Voice state
  let voiceState = 'idle';
  let recognition = null;

  const clearBody = () => {
    if (sidebar.body) {
      sidebar.body.innerHTML = "";
    }
  };

  const renderLoading = (message = "Loading...") => {
    clearBody();
    if (!sidebar.body) return;
    sidebar.body.innerHTML = `
      <div class="il-loading">
        <div class="il-spinner"></div>
        <div class="il-loading-text">${message}</div>
      </div>
    `;
  };

  const renderEmpty = (title, desc) => {
    clearBody();
    if (!sidebar.body) return;
    sidebar.body.innerHTML = `
      <div class="il-empty">
        <div class="il-empty-icon">${ICONS.empty || ''}</div>
        <div class="il-empty-title">${title || 'No content found'}</div>
        <div class="il-empty-desc">${desc || 'Try a different page.'}</div>
      </div>
    `;
  };

  const renderError = (message, showRetry = false) => {
    clearBody();
    if (!sidebar.body) return;
    sidebar.body.innerHTML = `
      <div class="il-error">
        <div class="il-error-icon">${ICONS.alert || ''}</div>
        <div class="il-error-text">${message || 'Something went wrong'}</div>
        ${showRetry ? '<button class="il-retry-btn" id="il-retry-btn" type="button">Try Again</button>' : ''}
      </div>
    `;
    if (showRetry) {
      const retryBtn = sidebar.body.querySelector('#il-retry-btn');
      if (retryBtn) {
        retryBtn.onclick = () => loadCards(true);
      }
    }
  };

  const renderWelcome = () => {
    clearBody();
    if (!sidebar.body) return;
    sidebar.body.innerHTML = `
      <div class="il-welcome-state">
        <div class="il-welcome-icon">${ICONS.sparkles || ''}</div>
        <div class="il-welcome-title">Welcome to InterestLens!</div>
        <div class="il-welcome-desc">Complete the setup to get personalized content recommendations.</div>
        <button class="il-setup-btn" id="il-setup-btn" type="button">Start Setup</button>
      </div>
    `;
    const setupBtn = sidebar.body.querySelector('#il-setup-btn');
    if (setupBtn) {
      setupBtn.onclick = () => {
        // Reset onboarding status and show welcome modal
        if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
          chrome.storage.local.remove([STORAGE_KEY], () => {
            if (window.__interestLensWelcome && window.__interestLensWelcome.show) {
              window.__interestLensWelcome.show();
            }
          });
        } else {
          localStorage.removeItem(STORAGE_KEY);
          if (window.__interestLensWelcome && window.__interestLensWelcome.show) {
            window.__interestLensWelcome.show();
          }
        }
      };
    }
  };

  // Listen for onboarding completion to reload content
  const listenForOnboardingComplete = () => {
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.onChanged) {
      chrome.storage.onChanged.addListener((changes, areaName) => {
        if (areaName === 'local' && changes[STORAGE_KEY] && changes[STORAGE_KEY].newValue) {
          // User just completed onboarding, load content
          loadCards();
        }
      });
    }
  };
  listenForOnboardingComplete();

  const checkOnboardingStatus = () => {
    return new Promise((resolve) => {
      if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get([STORAGE_KEY], (result) => {
          resolve(!!result[STORAGE_KEY]);
        });
      } else {
        resolve(!!localStorage.getItem(STORAGE_KEY));
      }
    });
  };

  const getScoreClass = (score) => {
    if (score == null) return 'il-badge-loading';
    if (score >= 80) return 'il-badge-good';
    if (score >= 50) return 'il-badge-warning';
    return 'il-badge-danger';
  };

  const getScoreIcon = (score) => {
    if (score == null) return '';
    if (score >= 80) return ICONS.check || '';
    if (score >= 50) return ICONS.warning || '';
    return ICONS.alert || '';
  };

  const buildCard = (data) => {
    const card = document.createElement("a");
    card.className = "il-card";
    card.href = data.url;
    card.target = "_blank";
    card.rel = "noopener";

    const hasImage = data.imageUrl && data.imageUrl.length > 0;
    
    let domain = data.url;
    try {
      domain = new URL(data.url).hostname.replace('www.', '');
    } catch (e) {}

    card.innerHTML = `
      <div class="il-card-image">
        ${hasImage ? `<img src="${data.imageUrl}" alt="" loading="lazy" onerror="this.parentElement.innerHTML='<div class=il-card-placeholder>No image</div>'">` : '<div class="il-card-placeholder">No image</div>'}
      </div>
      <div class="il-card-content">
        <div class="il-card-title">${data.title || 'Untitled'}</div>
        <div class="il-card-desc">${domain}</div>
        <div class="il-badge il-badge-loading"><span>Checking...</span></div>
      </div>
    `;

    return card;
  };

  const updateCardBadge = (card, score) => {
    const badge = card.querySelector('.il-badge');
    if (!badge) return;
    
    const scoreClass = getScoreClass(score);
    const icon = getScoreIcon(score);
    badge.className = `il-badge ${scoreClass}`;
    
    if (score == null) {
      badge.innerHTML = `<span>N/A</span>`;
    } else {
      badge.innerHTML = `<span class="il-badge-icon">${icon}</span><span>${score}% authentic</span>`;
    }
  };

  const requestScrape = (url, refreshCache = false) => {
    return new Promise((resolve, reject) => {
      try {
        chrome.runtime.sendMessage(
          { type: "interestlens:scrape", url, refreshCache },
          (response) => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
              return;
            }
            if (!response || !response.ok) {
              reject(new Error(response?.error || "Scrape failed"));
              return;
            }
            resolve(response.data);
          }
        );
      } catch (e) {
        reject(e);
      }
    });
  };

  const requestAuthenticity = (payload) => {
    return new Promise((resolve, reject) => {
      try {
        chrome.runtime.sendMessage(
          { type: "interestlens:authenticity", payload },
          (response) => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
              return;
            }
            if (!response || !response.ok) {
              reject(new Error(response?.error || "Authenticity failed"));
              return;
            }
            resolve(response.data);
          }
        );
      } catch (e) {
        reject(e);
      }
    });
  };

  const loadCards = async (refreshCache = false) => {
    // Show a ready state - the scrape functionality is not available
    // Instead, show the user their interests and activity
    renderLoading("Loading your interests...");
    if (sidebar.updateStats) sidebar.updateStats(null, 0, 0);

    try {
      // Try to get user preferences instead of scraping
      const response = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(
          { type: "interestlens:get-interests" },
          (response) => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
              return;
            }
            resolve(response);
          }
        );
      });

      if (response && response.ok && response.data) {
        const prefs = response.data;
        const topics = prefs.topics || [];

        if (topics.length === 0) {
          renderEmpty("No interests set", "Use the voice setup or browse more to build your interest profile.");
          return;
        }

        // Show user's interests
        clearBody();
        const container = document.createElement('div');
        container.className = 'il-interests-display';
        container.innerHTML = `
          <div class="il-interests-header">Your Interests</div>
          <div class="il-interests-list">
            ${topics.map(t => {
              const sentiment = t.sentiment || 'like';
              const badgeClass = sentiment === 'like' ? 'il-badge-good' : 'il-badge-danger';
              return `<span class="il-badge ${badgeClass}">${t.topic || t}</span>`;
            }).join('')}
          </div>
          <div class="il-interests-hint">Content matching these interests will be highlighted as you browse.</div>
        `;
        if (sidebar.body) sidebar.body.appendChild(container);

        const likes = topics.filter(t => (t.sentiment || 'like') === 'like').length;
        if (sidebar.updateStats) sidebar.updateStats(null, topics.length, likes);
      } else {
        renderEmpty("No interests found", "Complete the voice setup to set your content preferences.");
      }
    } catch (e) {
      console.warn("Load failed:", e);
      renderEmpty("Ready to personalize", "Browse the web and your interests will be learned automatically.");
    }
  };

  // Voice handlers
  const setVoiceState = (state) => {
    voiceState = state;
    const btn = sidebar.voiceBtn;
    if (!btn) return;

    btn.classList.remove('il-voice-listening', 'il-voice-processing');
    const mic = ICONS.mic || '';

    if (state === 'listening') {
      btn.classList.add('il-voice-listening');
      btn.innerHTML = `<span class="il-voice-icon">${mic}</span><span>Listening...</span>`;
      if (sidebar.updateVoiceStatus) sidebar.updateVoiceStatus("Speak now...");
    } else if (state === 'processing') {
      btn.classList.add('il-voice-processing');
      btn.innerHTML = `<span class="il-voice-icon">${mic}</span><span>Processing...</span>`;
    } else {
      btn.innerHTML = `<span class="il-voice-icon">${mic}</span><span>Ask InterestLens</span>`;
    }
  };

  const handleVoiceCommand = (cmd) => {
    const c = cmd.toLowerCase();
    if (sidebar.updateVoiceStatus) {
      sidebar.updateVoiceStatus(`Heard: "${cmd}"`);
    }
  };

  const startVoice = () => {
    if (voiceState !== 'idle') {
      if (recognition) {
        try { recognition.stop(); } catch (e) {}
      }
      setVoiceState('idle');
      return;
    }

    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      if (sidebar.updateVoiceStatus) sidebar.updateVoiceStatus("Voice not supported in this browser");
      return;
    }

    setVoiceState('listening');

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SR();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onresult = (e) => {
      const cmd = e.results[0][0].transcript;
      setVoiceState('processing');
      setTimeout(() => {
        handleVoiceCommand(cmd);
        setVoiceState('idle');
      }, 500);
    };

    recognition.onerror = (e) => {
      if (sidebar.updateVoiceStatus) sidebar.updateVoiceStatus(`Error: ${e.error}`);
      setVoiceState('idle');
    };

    recognition.onend = () => {
      if (voiceState === 'listening') setVoiceState('idle');
    };

    try {
      recognition.start();
    } catch (e) {
      if (sidebar.updateVoiceStatus) sidebar.updateVoiceStatus("Could not start voice");
      setVoiceState('idle');
    }
  };

  // Attach event listeners safely
  if (sidebar.refreshBtn) {
    sidebar.refreshBtn.onclick = () => loadCards(true);
  }

  if (sidebar.voiceBtn) {
    sidebar.voiceBtn.onclick = startVoice;
  }

  // Listen for messages
  try {
    chrome.runtime.onMessage.addListener((msg, sender, respond) => {
      if (msg?.type === "interestlens:toggle-sidebar") {
        if (sidebar.toggle) sidebar.toggle();
        respond({ ok: true });
        return true;
      }
    });
  } catch (e) {
    console.warn("Could not add message listener:", e);
  }

  // Check if welcome modal is currently visible
  const isWelcomeModalVisible = () => {
    return !!document.getElementById('il-welcome-overlay');
  };

  // Initial load - check onboarding first, and wait a bit for welcome modal
  setTimeout(() => {
    // Don't load if welcome modal is visible
    if (isWelcomeModalVisible()) {
      console.log('[InterestLens Sidebar] Welcome modal visible, waiting...');
      renderEmpty('Setup in Progress', 'Complete the welcome setup to get started.');
      return;
    }

    checkOnboardingStatus().then(isOnboarded => {
      if (isOnboarded) {
        loadCards();
      } else {
        renderWelcome();
      }
    });
  }, 500);
})();
