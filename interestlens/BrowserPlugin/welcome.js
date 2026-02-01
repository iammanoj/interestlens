/**
 * InterestLens Welcome & Voice Onboarding Module
 *
 * Shows a welcome modal for first-time users and integrates
 * Daily.co voice agent for preference onboarding.
 */

(function() {
  'use strict';

  // Prevent duplicate initialization
  if (window.__IL_WELCOME_INIT__) return;
  window.__IL_WELCOME_INIT__ = true;

  console.log('[InterestLens] Welcome module initializing...');

  const STORAGE_KEY = 'interestlens_onboarded';
  const BACKEND_URL = 'http://localhost:8001';

  // SVG Icons
  const ICONS = {
    eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
    mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>',
    chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
    sparkles: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l1.912 5.813L20 10l-6.088 1.187L12 17l-1.912-5.813L4 10l6.088-1.187L12 3z"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>'
  };

  // State
  let currentScreen = 'welcome';
  let voiceSession = null;
  let extractedCategories = { likes: [], dislikes: [] };
  let websocket = null;
  let overlayElement = null;
  let recognition = null;
  let isListening = false;

  /**
   * Check if user has completed onboarding
   */
  function checkOnboardingStatus() {
    return new Promise(function(resolve) {
      if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get([STORAGE_KEY], function(result) {
          resolve(!!result[STORAGE_KEY]);
        });
      } else {
        // Fallback to localStorage
        resolve(!!localStorage.getItem(STORAGE_KEY));
      }
    });
  }

  /**
   * Mark onboarding as complete
   */
  function markOnboardingComplete() {
    return new Promise(function(resolve) {
      if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        var data = {};
        data[STORAGE_KEY] = Date.now();
        chrome.storage.local.set(data, resolve);
      } else {
        localStorage.setItem(STORAGE_KEY, Date.now().toString());
        resolve();
      }
    });
  }

  /**
   * Inject welcome CSS styles
   */
  function injectWelcomeStyles() {
    if (document.getElementById('il-welcome-styles')) return;

    var link = document.createElement('link');
    link.id = 'il-welcome-styles';
    link.rel = 'stylesheet';
    if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.getURL) {
      link.href = chrome.runtime.getURL('welcome.css');
    }
    document.head.appendChild(link);
  }

  /**
   * Remove the overlay
   */
  function removeOverlay() {
    console.log('[InterestLens] Removing overlay...');
    if (overlayElement && overlayElement.parentNode) {
      overlayElement.parentNode.removeChild(overlayElement);
      overlayElement = null;
    }
    // Also remove by ID in case of orphaned elements
    var existing = document.getElementById('il-welcome-overlay');
    if (existing && existing.parentNode) {
      existing.parentNode.removeChild(existing);
    }
  }

  /**
   * Handle Start Voice button click
   */
  function handleStartVoice(e) {
    console.log('[InterestLens] Start Voice clicked');
    e.preventDefault();
    e.stopPropagation();
    startVoiceOnboarding();
  }

  /**
   * Handle Skip button click
   */
  function handleSkip(e) {
    console.log('[InterestLens] Skip clicked');
    e.preventDefault();
    e.stopPropagation();
    skipOnboarding();
  }

  /**
   * Create and show the welcome overlay
   */
  function showWelcomeModal() {
    console.log('[InterestLens] Showing welcome modal...');

    // Remove any existing overlay
    removeOverlay();

    // Inject CSS first
    injectWelcomeStyles();

    // Create overlay container
    overlayElement = document.createElement('div');
    overlayElement.id = 'il-welcome-overlay';
    overlayElement.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:2147483647;display:flex;align-items:center;justify-content:center;';

    // Create modal
    var modal = document.createElement('div');
    modal.className = 'il-welcome-modal';
    modal.style.cssText = 'background:#fff;border-radius:16px;width:90%;max-width:480px;max-height:90vh;overflow-y:auto;box-shadow:0 25px 50px rgba(0,0,0,0.25);';

    // Header
    var header = document.createElement('div');
    header.style.cssText = 'padding:32px 32px 24px;text-align:center;';
    header.innerHTML =
      '<div style="width:72px;height:72px;background:linear-gradient(135deg,#6366f1 0%,#a855f7 100%);border-radius:18px;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;box-shadow:0 8px 24px rgba(99,102,241,0.3);">' +
        '<span style="width:36px;height:36px;color:white;display:flex;align-items:center;justify-content:center;">' + ICONS.eye + '</span>' +
      '</div>' +
      '<h1 style="font-size:28px;font-weight:700;color:#0f172a;margin:0 0 8px;font-family:-apple-system,BlinkMacSystemFont,sans-serif;">Welcome to InterestLens</h1>' +
      '<p style="font-size:16px;color:#64748b;margin:0;font-family:-apple-system,BlinkMacSystemFont,sans-serif;">Your personal web content companion</p>';

    // Body with steps
    var body = document.createElement('div');
    body.style.cssText = 'padding:0 32px 24px;';

    var steps = [
      { icon: ICONS.mic, color: '#10b981', title: 'Tell us your interests', desc: 'Have a quick chat with our AI to share what topics you love (and what you\'d rather skip).' },
      { icon: ICONS.chart, color: '#3b82f6', title: 'We learn as you browse', desc: 'The extension tracks which articles and topics catch your attention.' },
      { icon: ICONS.sparkles, color: '#f59e0b', title: 'Content highlighted for you', desc: 'Articles matching your interests get subtly highlighted.' }
    ];

    var stepsHtml = '<div style="display:flex;flex-direction:column;gap:16px;">';
    steps.forEach(function(step) {
      stepsHtml +=
        '<div style="display:flex;align-items:flex-start;gap:16px;padding:16px;background:#f8fafc;border-radius:12px;">' +
          '<div style="width:44px;height:44px;border-radius:12px;background:' + step.color + ';display:flex;align-items:center;justify-content:center;flex-shrink:0;">' +
            '<span style="width:22px;height:22px;color:white;">' + step.icon + '</span>' +
          '</div>' +
          '<div style="flex:1;">' +
            '<h3 style="font-size:15px;font-weight:600;color:#0f172a;margin:0 0 4px;font-family:-apple-system,BlinkMacSystemFont,sans-serif;">' + step.title + '</h3>' +
            '<p style="font-size:13px;color:#64748b;margin:0;line-height:1.5;font-family:-apple-system,BlinkMacSystemFont,sans-serif;">' + step.desc + '</p>' +
          '</div>' +
        '</div>';
    });
    stepsHtml += '</div>';
    body.innerHTML = stepsHtml;

    // Footer with buttons
    var footer = document.createElement('div');
    footer.style.cssText = 'padding:20px 32px;background:#f8fafc;border-top:1px solid #e2e8f0;border-radius:0 0 16px 16px;';

    // Start Voice button
    var startBtn = document.createElement('button');
    startBtn.id = 'il-start-voice-btn';
    startBtn.type = 'button';
    startBtn.style.cssText = 'width:100%;padding:14px 24px;border:none;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;background:linear-gradient(135deg,#6366f1 0%,#a855f7 100%);color:white;box-shadow:0 4px 14px rgba(99,102,241,0.4);font-family:-apple-system,BlinkMacSystemFont,sans-serif;display:flex;align-items:center;justify-content:center;gap:8px;';
    startBtn.innerHTML = '<span style="width:20px;height:20px;">' + ICONS.mic + '</span> Start Voice Setup';
    startBtn.onclick = handleStartVoice;

    // Skip button
    var skipBtn = document.createElement('button');
    skipBtn.id = 'il-skip-btn';
    skipBtn.type = 'button';
    skipBtn.style.cssText = 'width:100%;margin-top:12px;padding:8px;border:none;background:none;color:#64748b;font-size:14px;cursor:pointer;font-family:-apple-system,BlinkMacSystemFont,sans-serif;';
    skipBtn.textContent = 'Skip for now (I\'ll set up later)';
    skipBtn.onclick = handleSkip;

    footer.appendChild(startBtn);
    footer.appendChild(skipBtn);

    // Assemble modal
    modal.appendChild(header);
    modal.appendChild(body);
    modal.appendChild(footer);
    overlayElement.appendChild(modal);

    // Prevent clicks on overlay from closing (click on modal content is fine)
    overlayElement.onclick = function(e) {
      if (e.target === overlayElement) {
        e.stopPropagation();
      }
    };

    // Add to DOM
    document.body.appendChild(overlayElement);
    console.log('[InterestLens] Welcome modal displayed');
  }

  /**
   * Skip onboarding
   */
  function skipOnboarding() {
    console.log('[InterestLens] Skipping onboarding...');
    markOnboardingComplete().then(function() {
      removeOverlay();
      console.log('[InterestLens] Onboarding skipped successfully');
    });
  }

  /**
   * Start voice onboarding session
   */
  function startVoiceOnboarding() {
    console.log('[InterestLens] Starting voice onboarding...');
    currentScreen = 'voice';
    renderVoiceScreen('connecting');

    // Generate a user ID for this session
    var sessionUserId = 'user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    console.log('[InterestLens] Session user ID:', sessionUserId);

    // Try to start voice session
    if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
      chrome.runtime.sendMessage(
        { type: 'interestlens:voice-session', userId: sessionUserId },
        function(response) {
          if (chrome.runtime.lastError) {
            console.error('[InterestLens] Voice session error:', chrome.runtime.lastError);
            renderVoiceScreen('error');
            setTimeout(startTextFallback, 1000);
            return;
          }

          if (!response || !response.ok) {
            console.error('[InterestLens] Voice session failed:', response?.error);
            renderVoiceScreen('error');
            setTimeout(startTextFallback, 1000);
            return;
          }

          console.log('[InterestLens] Voice session started:', response.data);
          voiceSession = {
            roomUrl: response.data.room_url,
            roomName: response.data.room_name,
            token: response.data.token,
            transcript: ''
          };

          // Render the Daily.co voice call screen
          renderDailyVoiceScreen();
        }
      );
    } else {
      // No chrome API, go directly to text fallback
      console.log('[InterestLens] Chrome API not available, using text fallback');
      renderVoiceScreen('error');
      setTimeout(startTextFallback, 1000);
    }
  }

  /**
   * Render the voice/chat screen
   */
  function renderVoiceScreen(status) {
    console.log('[InterestLens] Rendering voice screen, status:', status);
    if (!overlayElement) return;

    var statusText = {
      connecting: 'Connecting to assistant...',
      connected: 'Connected! Type your interests below.',
      listening: 'Listening...',
      processing: 'Processing...',
      error: 'Using text chat instead.'
    };

    var statusColor = status === 'error' ? '#ef4444' : (status === 'connected' ? '#22c55e' : '#eab308');

    overlayElement.innerHTML = '';

    var modal = document.createElement('div');
    modal.style.cssText = 'background:#fff;border-radius:16px;width:90%;max-width:480px;max-height:90vh;overflow-y:auto;box-shadow:0 25px 50px rgba(0,0,0,0.25);padding:32px;';

    // Avatar
    var avatar = document.createElement('div');
    avatar.style.cssText = 'width:80px;height:80px;border-radius:50%;background:linear-gradient(135deg,#10b981 0%,#059669 100%);margin:0 auto 20px;display:flex;align-items:center;justify-content:center;';
    avatar.innerHTML = '<span style="width:40px;height:40px;color:white;">' + ICONS.mic + '</span>';

    // Status
    var statusEl = document.createElement('div');
    statusEl.id = 'il-status-indicator';
    statusEl.style.cssText = 'text-align:center;margin-bottom:8px;';
    statusEl.innerHTML = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';margin-right:8px;"></span>' +
      '<span style="font-size:14px;color:#64748b;">' + (statusText[status] || 'Ready') + '</span>';

    // Title
    var title = document.createElement('h2');
    title.style.cssText = 'font-size:20px;font-weight:600;color:#0f172a;margin:0 0 8px;text-align:center;font-family:-apple-system,BlinkMacSystemFont,sans-serif;';
    title.textContent = 'Tell me your interests';

    // Hint
    var hint = document.createElement('p');
    hint.style.cssText = 'font-size:14px;color:#64748b;margin:0 0 20px;text-align:center;font-family:-apple-system,BlinkMacSystemFont,sans-serif;';
    hint.textContent = 'Click the mic button and speak, or type below.';

    // Mic button
    var micBtn = document.createElement('button');
    micBtn.type = 'button';
    micBtn.id = 'il-mic-btn';
    micBtn.style.cssText = 'width:64px;height:64px;border-radius:50%;border:none;background:linear-gradient(135deg,#22c55e 0%,#16a34a 100%);color:white;cursor:pointer;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;box-shadow:0 4px 14px rgba(34,197,94,0.4);transition:all 0.2s ease;';
    micBtn.innerHTML = '<span style="width:28px;height:28px;color:white;">' + ICONS.mic + '</span>';
    micBtn.onclick = function(e) {
      e.preventDefault();
      e.stopPropagation();
      console.log('[InterestLens] Mic button clicked');
      startVoiceRecognition();
    };

    // Transcript area
    var transcript = document.createElement('div');
    transcript.id = 'il-transcript-area';
    transcript.style.cssText = 'background:#f1f5f9;border-radius:12px;padding:16px;margin-bottom:16px;min-height:100px;max-height:200px;overflow-y:auto;';
    transcript.innerHTML = '<div style="font-size:11px;text-transform:uppercase;color:#94a3b8;margin-bottom:8px;">Conversation</div>' +
      '<div id="il-transcript-text" style="font-size:14px;color:#0f172a;line-height:1.5;">Click the mic button to speak or type below...</div>' +
      '<div id="il-interim-transcript" style="font-size:14px;color:#94a3b8;font-style:italic;display:none;margin-top:8px;"></div>';

    // Categories display
    var categoriesEl = document.createElement('div');
    categoriesEl.id = 'il-categories-display';
    categoriesEl.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px;justify-content:center;min-height:24px;';

    // Input area
    var inputArea = document.createElement('div');
    inputArea.style.cssText = 'display:flex;gap:8px;margin-bottom:16px;';

    var input = document.createElement('input');
    input.type = 'text';
    input.id = 'il-text-input';
    input.placeholder = 'e.g., I love technology and AI, but dislike sports news...';
    input.style.cssText = 'flex:1;padding:12px;border:1px solid #e2e8f0;border-radius:8px;font-size:14px;font-family:-apple-system,BlinkMacSystemFont,sans-serif;';

    var sendBtn = document.createElement('button');
    sendBtn.type = 'button';
    sendBtn.id = 'il-send-btn';
    sendBtn.textContent = 'Send';
    sendBtn.style.cssText = 'padding:12px 20px;background:linear-gradient(135deg,#6366f1 0%,#a855f7 100%);color:white;border:none;border-radius:8px;font-weight:600;cursor:pointer;font-family:-apple-system,BlinkMacSystemFont,sans-serif;';
    sendBtn.onclick = handleSendMessage;

    inputArea.appendChild(input);
    inputArea.appendChild(sendBtn);

    // Enter key handler for input
    input.onkeypress = function(e) {
      if (e.key === 'Enter') {
        handleSendMessage(e);
      }
    };

    // Action buttons
    var actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:12px;';

    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'flex:1;padding:12px;background:#e2e8f0;color:#475569;border:none;border-radius:8px;font-weight:600;cursor:pointer;font-family:-apple-system,BlinkMacSystemFont,sans-serif;';
    cancelBtn.onclick = function(e) {
      e.preventDefault();
      e.stopPropagation();
      console.log('[InterestLens] Cancel clicked');
      stopVoiceRecognition();
      currentScreen = 'welcome';
      showWelcomeModal();
    };

    var doneBtn = document.createElement('button');
    doneBtn.type = 'button';
    doneBtn.textContent = 'Done';
    doneBtn.style.cssText = 'flex:1;padding:12px;background:linear-gradient(135deg,#22c55e 0%,#16a34a 100%);color:white;border:none;border-radius:8px;font-weight:600;cursor:pointer;font-family:-apple-system,BlinkMacSystemFont,sans-serif;';
    doneBtn.onclick = function(e) {
      e.preventDefault();
      e.stopPropagation();
      console.log('[InterestLens] Done clicked');
      stopVoiceRecognition();
      completeVoiceOnboarding();
    };

    actions.appendChild(cancelBtn);
    actions.appendChild(doneBtn);

    // Assemble
    modal.appendChild(avatar);
    modal.appendChild(statusEl);
    modal.appendChild(title);
    modal.appendChild(hint);
    modal.appendChild(micBtn);
    modal.appendChild(transcript);
    modal.appendChild(categoriesEl);
    modal.appendChild(inputArea);
    modal.appendChild(actions);

    overlayElement.appendChild(modal);

    // Focus input
    setTimeout(function() {
      var inp = document.getElementById('il-text-input');
      if (inp) inp.focus();
    }, 100);
  }

  // Session ID for text chat
  var textSessionId = 'text_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

  /**
   * Start voice recognition
   */
  function startVoiceRecognition() {
    console.log('[InterestLens] Starting voice recognition...');

    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      console.error('[InterestLens] Speech recognition not supported');
      addToTranscript('System: Voice input not supported in this browser. Please type instead.');
      return;
    }

    if (isListening) {
      stopVoiceRecognition();
      return;
    }

    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = function() {
      console.log('[InterestLens] Voice recognition started');
      isListening = true;
      updateMicButton(true);
      updateStatusIndicator('listening');
    };

    recognition.onresult = function(event) {
      var finalTranscript = '';
      var interimTranscript = '';

      for (var i = event.resultIndex; i < event.results.length; i++) {
        var transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      // Show interim results
      if (interimTranscript) {
        updateInterimTranscript(interimTranscript);
      }

      // Process final results
      if (finalTranscript) {
        console.log('[InterestLens] Final transcript:', finalTranscript);
        clearInterimTranscript();

        // Add to transcript and send to backend
        addToTranscript('You: ' + finalTranscript);
        sendMessageToBackend(finalTranscript);
      }
    };

    recognition.onerror = function(event) {
      console.error('[InterestLens] Voice recognition error:', event.error);
      isListening = false;
      updateMicButton(false);
      updateStatusIndicator('connected');

      if (event.error === 'not-allowed') {
        addToTranscript('System: Microphone access denied. Please allow microphone access and try again.');
      } else if (event.error === 'no-speech') {
        addToTranscript('System: No speech detected. Click the mic and try again.');
      }
    };

    recognition.onend = function() {
      console.log('[InterestLens] Voice recognition ended');
      if (isListening) {
        // Restart if we're still supposed to be listening
        try {
          recognition.start();
        } catch (e) {
          isListening = false;
          updateMicButton(false);
          updateStatusIndicator('connected');
        }
      }
    };

    try {
      recognition.start();
    } catch (e) {
      console.error('[InterestLens] Failed to start recognition:', e);
      addToTranscript('System: Could not start voice input. Please type instead.');
    }
  }

  /**
   * Stop voice recognition
   */
  function stopVoiceRecognition() {
    console.log('[InterestLens] Stopping voice recognition...');
    isListening = false;
    if (recognition) {
      try {
        recognition.stop();
      } catch (e) {}
      recognition = null;
    }
    updateMicButton(false);
    updateStatusIndicator('connected');
  }

  /**
   * Update mic button state
   */
  function updateMicButton(listening) {
    var micBtn = document.getElementById('il-mic-btn');
    if (micBtn) {
      if (listening) {
        micBtn.style.background = 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)';
        micBtn.style.animation = 'il-pulse 1.5s ease-in-out infinite';
        micBtn.innerHTML = '<span style="width:24px;height:24px;color:white;">' + ICONS.mic + '</span>';
      } else {
        micBtn.style.background = 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)';
        micBtn.style.animation = 'none';
        micBtn.innerHTML = '<span style="width:24px;height:24px;color:white;">' + ICONS.mic + '</span>';
      }
    }
  }

  /**
   * Update status indicator
   */
  function updateStatusIndicator(status) {
    var statusEl = document.getElementById('il-status-indicator');
    if (statusEl) {
      var statusText = {
        connecting: 'Connecting...',
        connected: 'Ready - Click mic or type below',
        listening: 'Listening... Speak now!',
        processing: 'Processing...'
      };
      var statusColor = status === 'listening' ? '#22c55e' : (status === 'connected' ? '#3b82f6' : '#eab308');
      statusEl.innerHTML = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + statusColor + ';margin-right:8px;' + (status === 'listening' ? 'animation:il-blink 1s infinite;' : '') + '"></span>' +
        '<span style="font-size:14px;color:#64748b;">' + (statusText[status] || 'Ready') + '</span>';
    }
  }

  /**
   * Update interim transcript display
   */
  function updateInterimTranscript(text) {
    var interimEl = document.getElementById('il-interim-transcript');
    if (interimEl) {
      interimEl.textContent = text;
      interimEl.style.display = 'block';
    }
  }

  /**
   * Clear interim transcript
   */
  function clearInterimTranscript() {
    var interimEl = document.getElementById('il-interim-transcript');
    if (interimEl) {
      interimEl.textContent = '';
      interimEl.style.display = 'none';
    }
  }

  /**
   * Send message to backend
   */
  function sendMessageToBackend(message) {
    fetch(BACKEND_URL + '/voice/text-message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: textSessionId,
        message: message
      })
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
      console.log('[InterestLens] Backend response:', data);

      if (data.response) {
        addToTranscript('AI: ' + data.response);
        // Speak the response if available
        speakResponse(data.response);
      }

      if (data.extracted_categories || data.preferences_detected) {
        var cats = data.extracted_categories || data.preferences_detected;
        if (cats.topics && cats.topics.length > 0) {
          updateCategories({ likes: cats.topics.filter(function(t) { return t.sentiment === 'like'; }).map(function(t) { return t.topic; }),
                            dislikes: cats.topics.filter(function(t) { return t.sentiment === 'dislike'; }).map(function(t) { return t.topic; }) });
        }
      }
    })
    .catch(function(error) {
      console.error('[InterestLens] Backend error:', error);
      addToTranscript('AI: Got it! I\'ve noted your interests.');
      extractCategoriesLocally(message);
    });
  }

  /**
   * Speak response using Text-to-Speech
   */
  function speakResponse(text) {
    if ('speechSynthesis' in window) {
      var utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      utterance.volume = 0.8;
      window.speechSynthesis.speak(utterance);
    }
  }

  /**
   * Handle send message (from text input)
   */
  function handleSendMessage(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }

    var input = document.getElementById('il-text-input');
    var message = input ? input.value.trim() : '';
    if (!message) return;

    console.log('[InterestLens] Sending typed message:', message);

    // Clear input
    input.value = '';

    // Add to transcript and send to backend
    addToTranscript('You: ' + message);
    sendMessageToBackend(message);
  }

  /**
   * Add text to transcript
   */
  function addToTranscript(text) {
    var transcriptEl = document.getElementById('il-transcript-text');
    if (transcriptEl) {
      if (transcriptEl.textContent === 'Type your interests below to get started...') {
        transcriptEl.textContent = '';
      }
      transcriptEl.innerHTML += (transcriptEl.innerHTML ? '<br>' : '') + text;
      transcriptEl.parentNode.scrollTop = transcriptEl.parentNode.scrollHeight;
    }
  }

  /**
   * Update displayed categories
   */
  function updateCategories(categories) {
    if (categories.likes) {
      categories.likes.forEach(function(item) {
        var cat = typeof item === 'string' ? item : item.category;
        if (cat && extractedCategories.likes.indexOf(cat) === -1) {
          extractedCategories.likes.push(cat);
        }
      });
    }
    if (categories.dislikes) {
      categories.dislikes.forEach(function(item) {
        var cat = typeof item === 'string' ? item : item.category;
        if (cat && extractedCategories.dislikes.indexOf(cat) === -1) {
          extractedCategories.dislikes.push(cat);
        }
      });
    }

    renderCategories();
  }

  /**
   * Extract categories locally as fallback
   */
  function extractCategoriesLocally(message) {
    var lower = message.toLowerCase();

    // Simple keyword extraction
    var likeKeywords = ['love', 'like', 'enjoy', 'interested in', 'fan of', 'into'];
    var dislikeKeywords = ['hate', 'dislike', 'avoid', 'don\'t like', 'not interested'];

    var categories = ['technology', 'ai', 'sports', 'politics', 'science', 'health',
                      'business', 'entertainment', 'gaming', 'music', 'travel', 'food',
                      'finance', 'crypto', 'programming', 'news'];

    categories.forEach(function(cat) {
      if (lower.indexOf(cat) !== -1) {
        var isDislike = dislikeKeywords.some(function(kw) { return lower.indexOf(kw) !== -1; });

        if (isDislike && extractedCategories.dislikes.indexOf(cat) === -1) {
          extractedCategories.dislikes.push(cat);
        } else if (!isDislike && extractedCategories.likes.indexOf(cat) === -1) {
          extractedCategories.likes.push(cat);
        }
      }
    });

    renderCategories();
  }

  /**
   * Render category badges
   */
  function renderCategories() {
    var container = document.getElementById('il-categories-display');
    if (!container) return;

    var html = '';
    extractedCategories.likes.forEach(function(cat) {
      html += '<span style="padding:4px 10px;border-radius:20px;font-size:12px;font-weight:500;background:#dcfce7;color:#16a34a;">' + cat + '</span>';
    });
    extractedCategories.dislikes.forEach(function(cat) {
      html += '<span style="padding:4px 10px;border-radius:20px;font-size:12px;font-weight:500;background:#fee2e2;color:#dc2626;">' + cat + '</span>';
    });

    container.innerHTML = html;
  }

  /**
   * Render Daily.co voice call screen
   */
  function renderDailyVoiceScreen() {
    console.log('[InterestLens] Rendering Daily.co voice screen');
    if (!overlayElement || !voiceSession) return;

    overlayElement.innerHTML = '';

    var modal = document.createElement('div');
    modal.style.cssText = 'background:#fff;border-radius:16px;width:90%;max-width:600px;max-height:90vh;overflow:hidden;box-shadow:0 25px 50px rgba(0,0,0,0.25);display:flex;flex-direction:column;';

    // Header
    var header = document.createElement('div');
    header.style.cssText = 'padding:20px 24px;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;justify-content:space-between;';
    header.innerHTML = '<div style="display:flex;align-items:center;gap:12px;">' +
      '<div style="width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#10b981 0%,#059669 100%);display:flex;align-items:center;justify-content:center;">' +
      '<span style="width:20px;height:20px;color:white;">' + ICONS.mic + '</span></div>' +
      '<div><div style="font-size:16px;font-weight:600;color:#0f172a;">Voice Setup</div>' +
      '<div style="font-size:13px;color:#64748b;">Talk to our AI assistant about your interests</div></div></div>';

    // Daily.co iframe container
    var iframeContainer = document.createElement('div');
    iframeContainer.style.cssText = 'flex:1;min-height:400px;background:#0f172a;position:relative;';

    // Create iframe with Daily.co room
    var iframe = document.createElement('iframe');
    var roomUrlWithToken = voiceSession.roomUrl + '?t=' + voiceSession.token;
    iframe.src = roomUrlWithToken;
    iframe.style.cssText = 'width:100%;height:100%;border:none;min-height:400px;';
    iframe.allow = 'microphone; camera; autoplay; display-capture';
    iframe.id = 'il-daily-iframe';

    iframeContainer.appendChild(iframe);

    // Instructions
    var instructions = document.createElement('div');
    instructions.style.cssText = 'padding:16px 24px;background:#f8fafc;border-top:1px solid #e2e8f0;';
    instructions.innerHTML = '<div style="font-size:13px;color:#64748b;text-align:center;">' +
      '<strong>Instructions:</strong> Allow microphone access when prompted. ' +
      'The AI will ask you about your content interests. Just speak naturally!</div>';

    // Categories display area - always visible
    var categoriesArea = document.createElement('div');
    categoriesArea.id = 'il-daily-categories';
    categoriesArea.style.cssText = 'padding:20px 24px;background:linear-gradient(135deg,#f0fdf4 0%,#ecfeff 100%);border-top:1px solid #e2e8f0;';
    categoriesArea.innerHTML =
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">' +
        '<span style="width:24px;height:24px;color:#10b981;">' + ICONS.sparkles + '</span>' +
        '<span style="font-size:14px;font-weight:600;color:#0f172a;">Your Content Preferences</span>' +
      '</div>' +
      '<div style="font-size:13px;color:#64748b;margin-bottom:12px;">As you speak, we\'ll identify your interests:</div>' +
      '<div id="il-likes-section" style="margin-bottom:12px;">' +
        '<div style="font-size:11px;text-transform:uppercase;color:#16a34a;margin-bottom:6px;font-weight:600;">✓ Topics You Like</div>' +
        '<div id="il-daily-likes" style="display:flex;flex-wrap:wrap;gap:6px;min-height:28px;">' +
          '<span style="font-size:12px;color:#94a3b8;font-style:italic;">Listening...</span>' +
        '</div>' +
      '</div>' +
      '<div id="il-dislikes-section">' +
        '<div style="font-size:11px;text-transform:uppercase;color:#dc2626;margin-bottom:6px;font-weight:600;">✗ Topics to Avoid</div>' +
        '<div id="il-daily-dislikes" style="display:flex;flex-wrap:wrap;gap:6px;min-height:28px;">' +
          '<span style="font-size:12px;color:#94a3b8;font-style:italic;">Listening...</span>' +
        '</div>' +
      '</div>';

    // Text input fallback (if voice doesn't work)
    var textFallbackArea = document.createElement('div');
    textFallbackArea.style.cssText = 'padding:16px 24px;background:#fff;border-top:1px solid #e2e8f0;';
    textFallbackArea.innerHTML =
      '<div style="font-size:12px;color:#64748b;margin-bottom:8px;">Voice not working? Type your interests here:</div>';

    var inputRow = document.createElement('div');
    inputRow.style.cssText = 'display:flex;gap:8px;';

    var textInput = document.createElement('input');
    textInput.type = 'text';
    textInput.id = 'il-daily-text-input';
    textInput.placeholder = 'e.g., I like technology, AI. I dislike sports, politics...';
    textInput.style.cssText = 'flex:1;padding:10px 12px;border:1px solid #e2e8f0;border-radius:8px;font-size:14px;font-family:-apple-system,BlinkMacSystemFont,sans-serif;';

    var sendTextBtn = document.createElement('button');
    sendTextBtn.type = 'button';
    sendTextBtn.textContent = 'Add';
    sendTextBtn.style.cssText = 'padding:10px 16px;background:linear-gradient(135deg,#6366f1 0%,#a855f7 100%);color:white;border:none;border-radius:8px;font-weight:600;cursor:pointer;font-family:-apple-system,BlinkMacSystemFont,sans-serif;';
    sendTextBtn.onclick = function(e) {
      e.preventDefault();
      e.stopPropagation();
      var input = document.getElementById('il-daily-text-input');
      var message = input ? input.value.trim() : '';
      if (!message) return;

      console.log('[InterestLens] Sending text message:', message);
      input.value = '';

      // Send to backend text endpoint
      fetch(BACKEND_URL + '/voice/text-message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: voiceSession ? voiceSession.roomName : textSessionId,
          message: message
        })
      })
      .then(function(response) { return response.json(); })
      .then(function(data) {
        console.log('[InterestLens] Text response:', data);
        // Categories will be picked up by polling
      })
      .catch(function(e) {
        console.error('[InterestLens] Text send error:', e);
        // Extract locally as fallback
        extractCategoriesLocally(message);
        renderCategories();
      });
    };

    textInput.onkeypress = function(e) {
      if (e.key === 'Enter') {
        sendTextBtn.click();
      }
    };

    inputRow.appendChild(textInput);
    inputRow.appendChild(sendTextBtn);
    textFallbackArea.appendChild(inputRow);

    // Footer with actions
    var footer = document.createElement('div');
    footer.style.cssText = 'padding:16px 24px;border-top:1px solid #e2e8f0;display:flex;gap:12px;';

    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'flex:1;padding:12px;background:#e2e8f0;color:#475569;border:none;border-radius:8px;font-weight:600;cursor:pointer;font-family:-apple-system,BlinkMacSystemFont,sans-serif;';
    cancelBtn.onclick = function(e) {
      e.preventDefault();
      e.stopPropagation();
      console.log('[InterestLens] Cancel Daily call');
      endDailySession();
      currentScreen = 'welcome';
      showWelcomeModal();
    };

    var doneBtn = document.createElement('button');
    doneBtn.type = 'button';
    doneBtn.textContent = 'Done - Save My Interests';
    doneBtn.style.cssText = 'flex:2;padding:12px;background:linear-gradient(135deg,#22c55e 0%,#16a34a 100%);color:white;border:none;border-radius:8px;font-weight:600;cursor:pointer;font-family:-apple-system,BlinkMacSystemFont,sans-serif;';
    doneBtn.onclick = function(e) {
      e.preventDefault();
      e.stopPropagation();
      console.log('[InterestLens] Done with Daily call');
      endDailySession();
      fetchAndSavePreferences();
    };

    footer.appendChild(cancelBtn);
    footer.appendChild(doneBtn);

    // Assemble modal
    modal.appendChild(header);
    modal.appendChild(iframeContainer);
    modal.appendChild(instructions);
    modal.appendChild(categoriesArea);
    modal.appendChild(textFallbackArea);
    modal.appendChild(footer);
    overlayElement.appendChild(modal);

    // Start polling for transcriptions and preferences
    startPollingForPreferences();
  }

  /**
   * End Daily.co session
   */
  function endDailySession() {
    console.log('[InterestLens] Ending Daily session');
    stopPollingForPreferences();

    // Remove iframe to disconnect
    var iframe = document.getElementById('il-daily-iframe');
    if (iframe) {
      iframe.src = 'about:blank';
    }

    // End session on backend
    if (voiceSession && voiceSession.roomName) {
      fetch(BACKEND_URL + '/voice/session/' + voiceSession.roomName + '/end', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      }).catch(function(e) {
        console.warn('[InterestLens] Failed to end session:', e);
      });
    }
  }

  var preferencesPollingInterval = null;

  /**
   * Start polling for preferences from the voice session
   */
  function startPollingForPreferences() {
    console.log('[InterestLens] Starting preferences polling for room:', voiceSession ? voiceSession.roomName : 'none');

    // Track if we've found categories
    var foundCategories = false;

    preferencesPollingInterval = setInterval(function() {
      if (!voiceSession || !voiceSession.roomName) return;

      var roomName = voiceSession.roomName;
      console.log('[InterestLens] Polling for room:', roomName);

      // Try multiple endpoints in sequence

      // 1. Try transcriptions with session: prefix
      fetch(BACKEND_URL + '/voice/transcriptions/session:' + roomName)
        .then(function(response) {
          if (!response.ok) throw new Error('Not found with session prefix');
          return response.json();
        })
        .then(function(data) {
          console.log('[InterestLens] Found transcription data:', data);
          processExtractedCategories(data);
          foundCategories = true;
        })
        .catch(function() {
          // 2. Try transcriptions without prefix
          return fetch(BACKEND_URL + '/voice/transcriptions/' + roomName)
            .then(function(response) {
              if (!response.ok) throw new Error('Not found without prefix');
              return response.json();
            })
            .then(function(data) {
              console.log('[InterestLens] Found transcription data (no prefix):', data);
              processExtractedCategories(data);
              foundCategories = true;
            })
            .catch(function() {
              // 3. Try session status endpoint
              return fetch(BACKEND_URL + '/voice/session/' + roomName + '/status')
                .then(function(response) { return response.json(); })
                .then(function(data) {
                  console.log('[InterestLens] Session status:', data);
                  if (data.preferences && data.preferences.topics) {
                    var allTopics = data.preferences.topics.map(function(t) {
                      return { topic: t.topic, sentiment: t.sentiment || 'like' };
                    });
                    if (allTopics.length > 0) {
                      updateDailyInterestsDisplay(allTopics);
                      foundCategories = true;
                    }
                  }
                })
                .catch(function() {
                  // 4. Try general preferences endpoint as last resort
                  return fetch(BACKEND_URL + '/voice/preferences')
                    .then(function(response) { return response.json(); })
                    .then(function(data) {
                      console.log('[InterestLens] General preferences:', data);
                      if (data.topics && data.topics.length > 0) {
                        updateDailyInterestsDisplay(data.topics);
                        foundCategories = true;
                      }
                    })
                    .catch(function(e) {
                      if (!foundCategories) {
                        console.log('[InterestLens] No categories found yet, will keep polling...');
                      }
                    });
                });
            });
        });
    }, 2000);
  }

  /**
   * Process extracted categories from transcription data
   */
  function processExtractedCategories(data) {
    if (data.extracted_categories) {
      var cats = data.extracted_categories;
      var allTopics = [];

      // Process likes
      if (cats.likes && Array.isArray(cats.likes)) {
        cats.likes.forEach(function(item) {
          allTopics.push({
            topic: item.category || item.topic || item,
            sentiment: 'like'
          });
        });
      }

      // Process dislikes
      if (cats.dislikes && Array.isArray(cats.dislikes)) {
        cats.dislikes.forEach(function(item) {
          allTopics.push({
            topic: item.category || item.topic || item,
            sentiment: 'dislike'
          });
        });
      }

      if (allTopics.length > 0) {
        console.log('[InterestLens] Extracted topics:', allTopics);
        updateDailyInterestsDisplay(allTopics);
      }
    }

    // Also handle preferences.topics format
    if (data.preferences && data.preferences.topics && data.preferences.topics.length > 0) {
      updateDailyInterestsDisplay(data.preferences.topics);
    }
  }

  /**
   * Stop polling for preferences
   */
  function stopPollingForPreferences() {
    if (preferencesPollingInterval) {
      clearInterval(preferencesPollingInterval);
      preferencesPollingInterval = null;
    }
  }

  /**
   * Update the interests display during Daily call
   */
  function updateDailyInterestsDisplay(topics) {
    var likesContainer = document.getElementById('il-daily-likes');
    var dislikesContainer = document.getElementById('il-daily-dislikes');

    if (!likesContainer || !dislikesContainer) return;

    var likesHtml = '';
    var dislikesHtml = '';

    topics.forEach(function(topic) {
      var sentiment = topic.sentiment || 'like';
      var topicName = topic.topic || topic;

      // Update extracted categories
      if (sentiment === 'like' || sentiment === 'positive') {
        if (extractedCategories.likes.indexOf(topicName) === -1) {
          extractedCategories.likes.push(topicName);
        }
      } else if (sentiment === 'dislike' || sentiment === 'negative' || sentiment === 'avoid') {
        if (extractedCategories.dislikes.indexOf(topicName) === -1) {
          extractedCategories.dislikes.push(topicName);
        }
      }
    });

    // Build HTML for likes
    if (extractedCategories.likes.length > 0) {
      extractedCategories.likes.forEach(function(topic) {
        likesHtml += '<span style="padding:6px 12px;border-radius:20px;font-size:13px;font-weight:500;background:#dcfce7;color:#16a34a;display:inline-flex;align-items:center;gap:4px;animation:il-pop-in 0.3s ease;">' +
          '<span style="font-size:14px;">👍</span> ' + topic + '</span>';
      });
    } else {
      likesHtml = '<span style="font-size:12px;color:#94a3b8;font-style:italic;">Listening...</span>';
    }

    // Build HTML for dislikes
    if (extractedCategories.dislikes.length > 0) {
      extractedCategories.dislikes.forEach(function(topic) {
        dislikesHtml += '<span style="padding:6px 12px;border-radius:20px;font-size:13px;font-weight:500;background:#fee2e2;color:#dc2626;display:inline-flex;align-items:center;gap:4px;animation:il-pop-in 0.3s ease;">' +
          '<span style="font-size:14px;">👎</span> ' + topic + '</span>';
      });
    } else {
      dislikesHtml = '<span style="font-size:12px;color:#94a3b8;font-style:italic;">Listening...</span>';
    }

    likesContainer.innerHTML = likesHtml;
    dislikesContainer.innerHTML = dislikesHtml;

    console.log('[InterestLens] Updated categories display - Likes:', extractedCategories.likes, 'Dislikes:', extractedCategories.dislikes);
  }

  /**
   * Fetch preferences from backend and save
   */
  function fetchAndSavePreferences() {
    console.log('[InterestLens] Fetching final preferences');

    // First try to get preferences from the voice session
    if (voiceSession && voiceSession.roomName) {
      fetch(BACKEND_URL + '/voice/transcriptions/session:' + voiceSession.roomName)
        .then(function(response) {
          if (!response.ok) {
            return fetch(BACKEND_URL + '/voice/transcriptions/' + voiceSession.roomName);
          }
          return response;
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
          console.log('[InterestLens] Final transcription data:', data);

          // Handle extracted_categories format
          if (data.extracted_categories) {
            var cats = data.extracted_categories;

            if (cats.likes && Array.isArray(cats.likes)) {
              cats.likes.forEach(function(item) {
                var topicName = item.category || item.topic || item;
                if (extractedCategories.likes.indexOf(topicName) === -1) {
                  extractedCategories.likes.push(topicName);
                }
              });
            }

            if (cats.dislikes && Array.isArray(cats.dislikes)) {
              cats.dislikes.forEach(function(item) {
                var topicName = item.category || item.topic || item;
                if (extractedCategories.dislikes.indexOf(topicName) === -1) {
                  extractedCategories.dislikes.push(topicName);
                }
              });
            }
          }

          // Also handle preferences.topics format as fallback
          if (data.preferences && data.preferences.topics) {
            data.preferences.topics.forEach(function(topic) {
              var topicName = topic.topic || topic;
              var sentiment = topic.sentiment || 'like';
              if (sentiment === 'like' && extractedCategories.likes.indexOf(topicName) === -1) {
                extractedCategories.likes.push(topicName);
              } else if (sentiment === 'dislike' && extractedCategories.dislikes.indexOf(topicName) === -1) {
                extractedCategories.dislikes.push(topicName);
              }
            });
          }

          console.log('[InterestLens] Final categories:', extractedCategories);
          completeVoiceOnboarding();
        })
        .catch(function(e) {
          console.warn('[InterestLens] Failed to fetch preferences:', e);
          completeVoiceOnboarding();
        });
    } else {
      completeVoiceOnboarding();
    }
  }

  /**
   * Start text-based fallback
   */
  function startTextFallback() {
    console.log('[InterestLens] Starting text fallback...');

    // Get opening message
    fetch(BACKEND_URL + '/voice/text-session/opening')
      .then(function(response) { return response.json(); })
      .then(function(data) {
        if (data.message) {
          addToTranscript('AI: ' + data.message);
        }
      })
      .catch(function() {
        addToTranscript('AI: Hi! Tell me about your interests. What topics do you enjoy reading about?');
      });
  }

  /**
   * Complete voice onboarding
   */
  function completeVoiceOnboarding() {
    console.log('[InterestLens] Completing onboarding...');

    // Save preferences
    savePreferences().then(function() {
      renderCompleteScreen();
    });
  }

  /**
   * Save preferences to backend
   */
  function savePreferences() {
    return new Promise(function(resolve) {
      if (extractedCategories.likes.length === 0 && extractedCategories.dislikes.length === 0) {
        resolve();
        return;
      }

      var topics = [];
      extractedCategories.likes.forEach(function(c) {
        topics.push({
          topic: c,
          sentiment: 'like',
          intensity: 0.8,
          subtopics: [],
          avoid_subtopics: []
        });
      });
      extractedCategories.dislikes.forEach(function(c) {
        topics.push({
          topic: c,
          sentiment: 'dislike',
          intensity: 0.8,
          subtopics: [],
          avoid_subtopics: []
        });
      });

      fetch(BACKEND_URL + '/voice/save-preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topics: topics })
      })
      .then(function() { resolve(); })
      .catch(function() { resolve(); });
    });
  }

  /**
   * Render completion screen
   */
  function renderCompleteScreen() {
    console.log('[InterestLens] Rendering complete screen');
    if (!overlayElement) return;

    overlayElement.innerHTML = '';

    var modal = document.createElement('div');
    modal.style.cssText = 'background:#fff;border-radius:16px;width:90%;max-width:480px;padding:0;text-align:center;box-shadow:0 25px 50px rgba(0,0,0,0.25);overflow:hidden;';

    // Header with success icon
    var header = document.createElement('div');
    header.style.cssText = 'padding:32px 32px 24px;background:linear-gradient(135deg,#f0fdf4 0%,#dcfce7 100%);';
    header.innerHTML =
      '<div style="width:72px;height:72px;border-radius:50%;background:linear-gradient(135deg,#22c55e 0%,#16a34a 100%);margin:0 auto 20px;display:flex;align-items:center;justify-content:center;box-shadow:0 8px 24px rgba(34,197,94,0.3);">' +
        '<span style="width:36px;height:36px;color:white;">' + ICONS.check + '</span>' +
      '</div>' +
      '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 8px;font-family:-apple-system,BlinkMacSystemFont,sans-serif;">You\'re All Set!</h2>' +
      '<p style="font-size:14px;color:#64748b;margin:0;font-family:-apple-system,BlinkMacSystemFont,sans-serif;">Your personalized browsing experience is ready</p>';

    // Categories summary
    var hasLikes = extractedCategories.likes.length > 0;
    var hasDislikes = extractedCategories.dislikes.length > 0;

    var body = document.createElement('div');
    body.style.cssText = 'padding:24px 32px;';

    if (hasLikes || hasDislikes) {
      var summaryHtml = '<div style="text-align:left;">';

      if (hasLikes) {
        summaryHtml += '<div style="margin-bottom:16px;">' +
          '<div style="font-size:12px;text-transform:uppercase;color:#16a34a;margin-bottom:8px;font-weight:600;display:flex;align-items:center;gap:6px;">' +
            '<span style="font-size:16px;">✓</span> Content You\'ll See More Of' +
          '</div>' +
          '<div style="display:flex;flex-wrap:wrap;gap:6px;">';
        extractedCategories.likes.forEach(function(cat) {
          summaryHtml += '<span style="padding:6px 12px;border-radius:20px;font-size:13px;font-weight:500;background:#dcfce7;color:#16a34a;">👍 ' + cat + '</span>';
        });
        summaryHtml += '</div></div>';
      }

      if (hasDislikes) {
        summaryHtml += '<div style="margin-bottom:16px;">' +
          '<div style="font-size:12px;text-transform:uppercase;color:#dc2626;margin-bottom:8px;font-weight:600;display:flex;align-items:center;gap:6px;">' +
            '<span style="font-size:16px;">✗</span> Content You\'ll See Less Of' +
          '</div>' +
          '<div style="display:flex;flex-wrap:wrap;gap:6px;">';
        extractedCategories.dislikes.forEach(function(cat) {
          summaryHtml += '<span style="padding:6px 12px;border-radius:20px;font-size:13px;font-weight:500;background:#fee2e2;color:#dc2626;">👎 ' + cat + '</span>';
        });
        summaryHtml += '</div></div>';
      }

      summaryHtml += '</div>';
      body.innerHTML = summaryHtml;
    }

    // What happens next section
    var nextSection = document.createElement('div');
    nextSection.style.cssText = 'padding:20px 32px;background:#f8fafc;border-top:1px solid #e2e8f0;text-align:left;';
    nextSection.innerHTML =
      '<div style="font-size:13px;font-weight:600;color:#0f172a;margin-bottom:12px;">What InterestLens will do for you:</div>' +
      '<div style="display:flex;flex-direction:column;gap:8px;">' +
        '<div style="display:flex;align-items:center;gap:8px;font-size:13px;color:#64748b;">' +
          '<span style="color:#6366f1;">✦</span> Highlight articles matching your interests' +
        '</div>' +
        '<div style="display:flex;align-items:center;gap:8px;font-size:13px;color:#64748b;">' +
          '<span style="color:#6366f1;">✦</span> Dim content you want to avoid' +
        '</div>' +
        '<div style="display:flex;align-items:center;gap:8px;font-size:13px;color:#64748b;">' +
          '<span style="color:#6366f1;">✦</span> Learn from your browsing to improve recommendations' +
        '</div>' +
      '</div>';

    // Footer with button
    var footer = document.createElement('div');
    footer.style.cssText = 'padding:20px 32px;border-top:1px solid #e2e8f0;';

    var startBtn = document.createElement('button');
    startBtn.type = 'button';
    startBtn.textContent = 'Start Browsing';
    startBtn.style.cssText = 'width:100%;padding:14px 24px;border:none;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;background:linear-gradient(135deg,#6366f1 0%,#a855f7 100%);color:white;font-family:-apple-system,BlinkMacSystemFont,sans-serif;box-shadow:0 4px 14px rgba(99,102,241,0.4);';
    startBtn.onclick = function(e) {
      e.preventDefault();
      e.stopPropagation();
      console.log('[InterestLens] Start Browsing clicked');
      markOnboardingComplete().then(function() {
        removeOverlay();
      });
    };

    footer.appendChild(startBtn);

    modal.appendChild(header);
    if (hasLikes || hasDislikes) {
      modal.appendChild(body);
    }
    modal.appendChild(nextSection);
    modal.appendChild(footer);
    overlayElement.appendChild(modal);
  }

  /**
   * Initialize
   */
  function init() {
    console.log('[InterestLens] Checking onboarding status...');

    checkOnboardingStatus().then(function(isOnboarded) {
      console.log('[InterestLens] Is onboarded:', isOnboarded);

      if (!isOnboarded) {
        setTimeout(function() {
          showWelcomeModal();
        }, 300);
      }
    });
  }

  // Start initialization when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose API for debugging
  window.__interestLensWelcome = {
    show: showWelcomeModal,
    hide: removeOverlay,
    reset: function() {
      return new Promise(function(resolve) {
        if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
          chrome.storage.local.remove([STORAGE_KEY], function() {
            showWelcomeModal();
            resolve();
          });
        } else {
          localStorage.removeItem(STORAGE_KEY);
          showWelcomeModal();
          resolve();
        }
      });
    }
  };

  console.log('[InterestLens] Welcome module loaded');
})();
