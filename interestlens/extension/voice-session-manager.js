/**
 * Voice Session Manager for Chrome Extension
 * Handles session validation, cache management, and recovery.
 *
 * USAGE:
 *   const sessionManager = new VoiceSessionManager('http://localhost:8000');
 *
 *   // On page load - validate cached session
 *   const session = await sessionManager.getValidSession();
 *   if (session) {
 *     // Use cached session
 *     connectToVoice(session.room_name, session.token);
 *   } else {
 *     // Need to start new session
 *     const newSession = await sessionManager.startNewSession();
 *     connectToVoice(newSession.room_name, newSession.token);
 *   }
 */

class VoiceSessionManager {
  constructor(apiBaseUrl, options = {}) {
    this.apiBaseUrl = apiBaseUrl;
    this.storagePrefix = options.storagePrefix || 'interestlens_voice_';
    this.sessionTimeoutMs = options.sessionTimeoutMs || 30 * 60 * 1000; // 30 minutes
    this.tokenExpiryBufferMs = options.tokenExpiryBufferMs || 5 * 60 * 1000; // 5 minute buffer
  }

  /**
   * Storage keys
   */
  get KEYS() {
    return {
      ROOM_NAME: `${this.storagePrefix}room_name`,
      TOKEN: `${this.storagePrefix}token`,
      TOKEN_EXPIRY: `${this.storagePrefix}token_expiry`,
      ROOM_URL: `${this.storagePrefix}room_url`,
      SESSION_START: `${this.storagePrefix}session_start`,
      WEBSOCKET_URL: `${this.storagePrefix}websocket_url`,
      USER_ID: `${this.storagePrefix}user_id`
    };
  }

  /**
   * Get cached session data from localStorage
   */
  getCachedSession() {
    const roomName = localStorage.getItem(this.KEYS.ROOM_NAME);
    const token = localStorage.getItem(this.KEYS.TOKEN);
    const tokenExpiry = localStorage.getItem(this.KEYS.TOKEN_EXPIRY);
    const roomUrl = localStorage.getItem(this.KEYS.ROOM_URL);
    const sessionStart = localStorage.getItem(this.KEYS.SESSION_START);
    const websocketUrl = localStorage.getItem(this.KEYS.WEBSOCKET_URL);
    const userId = localStorage.getItem(this.KEYS.USER_ID);

    if (!roomName || !token) {
      return null;
    }

    return {
      room_name: roomName,
      token: token,
      token_expiry: tokenExpiry ? parseInt(tokenExpiry) : null,
      room_url: roomUrl,
      session_start: sessionStart ? parseInt(sessionStart) : null,
      websocket_url: websocketUrl,
      user_id: userId
    };
  }

  /**
   * Save session data to localStorage
   */
  saveSession(sessionData) {
    localStorage.setItem(this.KEYS.ROOM_NAME, sessionData.room_name);
    localStorage.setItem(this.KEYS.TOKEN, sessionData.token);
    localStorage.setItem(this.KEYS.ROOM_URL, sessionData.room_url);
    localStorage.setItem(this.KEYS.WEBSOCKET_URL, sessionData.websocket_url);
    localStorage.setItem(this.KEYS.SESSION_START, Date.now().toString());

    if (sessionData.expires_at) {
      localStorage.setItem(this.KEYS.TOKEN_EXPIRY, (sessionData.expires_at * 1000).toString());
    }

    if (sessionData.user_id) {
      localStorage.setItem(this.KEYS.USER_ID, sessionData.user_id);
    }
  }

  /**
   * Clear all cached session data
   */
  clearSession() {
    Object.values(this.KEYS).forEach(key => {
      localStorage.removeItem(key);
    });
    console.log('[VoiceSessionManager] Cleared cached session');
  }

  /**
   * Check if token is expired or about to expire
   */
  isTokenExpired(session) {
    if (!session || !session.token_expiry) {
      return true; // Assume expired if no expiry info
    }

    const now = Date.now();
    const expiryWithBuffer = session.token_expiry - this.tokenExpiryBufferMs;

    return now >= expiryWithBuffer;
  }

  /**
   * Check if session has been idle too long
   */
  isSessionStale(session) {
    if (!session || !session.session_start) {
      return true;
    }

    const now = Date.now();
    const sessionAge = now - session.session_start;

    return sessionAge >= this.sessionTimeoutMs;
  }

  /**
   * Validate session with the backend
   */
  async validateWithBackend(roomName, token = null) {
    try {
      const url = `${this.apiBaseUrl}/voice/validate-session/${roomName}`;
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        console.error('[VoiceSessionManager] Backend validation failed:', response.status);
        return {
          valid: false,
          action: 'start_new',
          error: 'VALIDATION_FAILED'
        };
      }

      return await response.json();
    } catch (error) {
      console.error('[VoiceSessionManager] Error validating session:', error);
      return {
        valid: false,
        action: 'start_new',
        error: 'NETWORK_ERROR'
      };
    }
  }

  /**
   * Get a valid session (from cache or start new)
   * This is the main entry point for getting a session.
   *
   * Returns: Session data if valid, null if needs new session
   */
  async getValidSession() {
    const cached = this.getCachedSession();

    if (!cached) {
      console.log('[VoiceSessionManager] No cached session found');
      return null;
    }

    console.log('[VoiceSessionManager] Found cached session:', cached.room_name);

    // Quick local checks first
    if (this.isTokenExpired(cached)) {
      console.log('[VoiceSessionManager] Token is expired');
      this.clearSession();
      return null;
    }

    if (this.isSessionStale(cached)) {
      console.log('[VoiceSessionManager] Session is stale');
      this.clearSession();
      return null;
    }

    // Validate with backend
    const validation = await this.validateWithBackend(cached.room_name, cached.token);

    if (!validation.valid) {
      console.log('[VoiceSessionManager] Backend validation failed:', validation.error);
      if (validation.should_clear_cache) {
        this.clearSession();
      }
      return null;
    }

    console.log('[VoiceSessionManager] Session is valid');
    return cached;
  }

  /**
   * Start a new voice session
   */
  async startNewSession(authToken = null) {
    console.log('[VoiceSessionManager] Starting new session');

    // Clear any stale session data first
    this.clearSession();

    try {
      const headers = {
        'Content-Type': 'application/json'
      };

      if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
      }

      const response = await fetch(`${this.apiBaseUrl}/voice/start-session`, {
        method: 'POST',
        headers
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`Failed to start session: ${response.status} - ${error}`);
      }

      const session = await response.json();

      // Save to cache
      this.saveSession(session);

      console.log('[VoiceSessionManager] New session started:', session.room_name);
      return session;

    } catch (error) {
      console.error('[VoiceSessionManager] Error starting session:', error);
      throw error;
    }
  }

  /**
   * End the current session
   */
  async endSession() {
    const cached = this.getCachedSession();

    if (cached && cached.room_name) {
      try {
        await fetch(`${this.apiBaseUrl}/voice/session/${cached.room_name}/end`, {
          method: 'POST'
        });
      } catch (error) {
        console.error('[VoiceSessionManager] Error ending session:', error);
      }
    }

    this.clearSession();
  }

  /**
   * Get session status from backend
   */
  async getSessionStatus(roomName = null) {
    const room = roomName || this.getCachedSession()?.room_name;

    if (!room) {
      return { exists: false, status: 'no_session' };
    }

    try {
      const response = await fetch(`${this.apiBaseUrl}/voice/session/${room}/status`);
      return await response.json();
    } catch (error) {
      console.error('[VoiceSessionManager] Error getting status:', error);
      return { exists: false, status: 'error', error: error.message };
    }
  }

  /**
   * Create a WebSocket connection with automatic reconnection
   */
  createWebSocketConnection(options = {}) {
    const cached = this.getCachedSession();

    if (!cached || !cached.websocket_url) {
      throw new Error('No valid session for WebSocket connection');
    }

    const wsUrl = cached.websocket_url.startsWith('/')
      ? `${this.apiBaseUrl.replace('http', 'ws')}${cached.websocket_url}`
      : cached.websocket_url;

    return new ReconnectingWebSocket(wsUrl, {
      maxRetries: options.maxRetries || 5,
      retryDelayMs: options.retryDelayMs || 1000,
      maxRetryDelayMs: options.maxRetryDelayMs || 30000,
      onError: (error, retryCount) => {
        console.warn(`[VoiceSessionManager] WebSocket error (retry ${retryCount}):`, error);

        // If we've exhausted retries, the session might be dead
        if (retryCount >= (options.maxRetries || 5)) {
          console.log('[VoiceSessionManager] Max retries reached, clearing session');
          this.clearSession();
          if (options.onSessionExpired) {
            options.onSessionExpired();
          }
        }
      },
      ...options
    });
  }
}

/**
 * WebSocket with automatic reconnection
 */
class ReconnectingWebSocket {
  constructor(url, options = {}) {
    this.url = url;
    this.maxRetries = options.maxRetries || 5;
    this.retryDelayMs = options.retryDelayMs || 1000;
    this.maxRetryDelayMs = options.maxRetryDelayMs || 30000;
    this.onError = options.onError || (() => {});
    this.onConnect = options.onConnect || (() => {});
    this.onDisconnect = options.onDisconnect || (() => {});
    this.onMessage = options.onMessage || (() => {});
    this.onSessionExpired = options.onSessionExpired || (() => {});

    this.ws = null;
    this.retryCount = 0;
    this.isConnecting = false;
    this.shouldReconnect = true;
  }

  connect() {
    if (this.isConnecting) return;
    this.isConnecting = true;

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log('[ReconnectingWebSocket] Connected');
        this.retryCount = 0;
        this.isConnecting = false;
        this.onConnect();
      };

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        // Handle session errors
        if (data.type === 'error' && data.code) {
          if (['SESSION_NOT_FOUND', 'SESSION_EXPIRED', 'SESSION_ENDED'].includes(data.code)) {
            console.log('[ReconnectingWebSocket] Session error:', data.code);
            this.shouldReconnect = false;
            this.onSessionExpired();
            return;
          }
        }

        this.onMessage(data);
      };

      this.ws.onerror = (error) => {
        console.error('[ReconnectingWebSocket] Error:', error);
        this.isConnecting = false;
        this.onError(error, this.retryCount);
      };

      this.ws.onclose = (event) => {
        console.log('[ReconnectingWebSocket] Closed:', event.code, event.reason);
        this.isConnecting = false;
        this.onDisconnect();

        if (this.shouldReconnect && this.retryCount < this.maxRetries) {
          this.scheduleReconnect();
        }
      };

    } catch (error) {
      console.error('[ReconnectingWebSocket] Connection error:', error);
      this.isConnecting = false;
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    this.retryCount++;
    const delay = Math.min(
      this.retryDelayMs * Math.pow(2, this.retryCount - 1),
      this.maxRetryDelayMs
    );

    console.log(`[ReconnectingWebSocket] Reconnecting in ${delay}ms (attempt ${this.retryCount})`);
    setTimeout(() => this.connect(), delay);
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(typeof data === 'string' ? data : JSON.stringify(data));
    }
  }

  close() {
    this.shouldReconnect = false;
    if (this.ws) {
      this.ws.close();
    }
  }
}

// Export for use
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { VoiceSessionManager, ReconnectingWebSocket };
}
