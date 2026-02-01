/**
 * Voice Client for Chrome Extension
 * Connects to InterestLens backend via WebSocket for real-time voice interaction.
 *
 * Usage:
 *   const voiceClient = new VoiceClient('ws://localhost:8000/voice/audio-stream/my-session');
 *   await voiceClient.connect();
 *   voiceClient.startListening();
 *   // ... user speaks ...
 *   voiceClient.stopListening(); // Triggers transcription and response
 */

class VoiceClient {
  constructor(websocketUrl, options = {}) {
    this.websocketUrl = websocketUrl;
    this.ws = null;
    this.isConnected = false;
    this.isListening = false;

    // Audio settings
    this.sampleRate = options.sampleRate || 16000;
    this.bufferSize = options.bufferSize || 4096;

    // Audio context and nodes
    this.audioContext = null;
    this.mediaStream = null;
    this.processor = null;
    this.source = null;

    // Callbacks
    this.onConnected = options.onConnected || (() => {});
    this.onDisconnected = options.onDisconnected || (() => {});
    this.onTranscription = options.onTranscription || (() => {});
    this.onAgentResponse = options.onAgentResponse || (() => {});
    this.onError = options.onError || ((err) => console.error('VoiceClient error:', err));
    this.onListeningStateChange = options.onListeningStateChange || (() => {});
  }

  /**
   * Connect to the WebSocket server
   */
  async connect() {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.websocketUrl);

        this.ws.onopen = () => {
          console.log('[VoiceClient] Connected to server');
          this.isConnected = true;
        };

        this.ws.onmessage = (event) => {
          const data = JSON.parse(event.data);
          this.handleMessage(data);

          if (data.type === 'connected') {
            this.onConnected(data);
            resolve();
          }
        };

        this.ws.onerror = (error) => {
          console.error('[VoiceClient] WebSocket error:', error);
          this.onError(error);
          reject(error);
        };

        this.ws.onclose = () => {
          console.log('[VoiceClient] Disconnected');
          this.isConnected = false;
          this.isListening = false;
          this.onDisconnected();
        };

      } catch (error) {
        reject(error);
      }
    });
  }

  /**
   * Handle incoming WebSocket messages
   */
  handleMessage(data) {
    switch (data.type) {
      case 'connected':
        console.log('[VoiceClient] Session:', data.session_id);
        break;

      case 'listening_started':
        console.log('[VoiceClient] Listening started');
        this.onListeningStateChange(true);
        break;

      case 'processing':
        console.log('[VoiceClient] Processing:', data.message);
        break;

      case 'transcription':
        console.log('[VoiceClient] Transcription:', data.text);
        this.onTranscription(data.text, data.speaker);
        break;

      case 'agent_response':
        console.log('[VoiceClient] Agent response:', data.text);
        this.onAgentResponse({
          text: data.text,
          isComplete: data.is_complete,
          preferences: data.preferences
        });

        // If session is complete, notify the extension to refresh all pages
        if (data.is_complete && data.preferences) {
          this.notifyExtensionPreferencesUpdated(data.preferences);
        }
        break;

      case 'session_complete':
        console.log('[VoiceClient] Session complete with preferences');
        this.notifyExtensionPreferencesUpdated(data.preferences);
        break;

      case 'error':
        console.error('[VoiceClient] Server error:', data.error);
        this.onError(new Error(data.error));
        break;

      case 'heartbeat':
      case 'pong':
        // Keepalive messages, ignore
        break;

      default:
        console.log('[VoiceClient] Unknown message type:', data.type);
    }
  }

  /**
   * Start capturing audio from microphone
   */
  async startListening() {
    if (!this.isConnected) {
      throw new Error('Not connected to server');
    }

    if (this.isListening) {
      return;
    }

    try {
      // Request microphone access
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: this.sampleRate,
          echoCancellation: true,
          noiseSuppression: true
        }
      });

      // Create audio context
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: this.sampleRate
      });

      // Create source from microphone
      this.source = this.audioContext.createMediaStreamSource(this.mediaStream);

      // Create script processor for capturing audio
      this.processor = this.audioContext.createScriptProcessor(this.bufferSize, 1, 1);

      this.processor.onaudioprocess = (event) => {
        if (!this.isListening) return;

        const inputData = event.inputBuffer.getChannelData(0);

        // Convert Float32 to Int16 PCM
        const pcmData = this.float32ToInt16(inputData);

        // Encode as base64 and send
        const base64Audio = this.arrayBufferToBase64(pcmData.buffer);

        this.send({
          type: 'audio_chunk',
          data: base64Audio
        });
      };

      // Connect nodes
      this.source.connect(this.processor);
      this.processor.connect(this.audioContext.destination);

      // Tell server we're starting
      this.send({ type: 'start_listening' });
      this.send({ type: 'set_sample_rate', sample_rate: this.sampleRate });

      this.isListening = true;
      console.log('[VoiceClient] Started listening');

    } catch (error) {
      console.error('[VoiceClient] Error starting audio:', error);
      this.onError(error);
      throw error;
    }
  }

  /**
   * Stop capturing audio and process
   */
  stopListening() {
    if (!this.isListening) return;

    this.isListening = false;
    this.onListeningStateChange(false);

    // Stop audio processing
    if (this.processor) {
      this.processor.disconnect();
      this.processor = null;
    }

    if (this.source) {
      this.source.disconnect();
      this.source = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }

    // Tell server to process accumulated audio
    this.send({ type: 'stop_listening' });

    console.log('[VoiceClient] Stopped listening, processing...');
  }

  /**
   * Send a message to the server
   */
  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  /**
   * Disconnect from server
   */
  disconnect() {
    if (this.isListening) {
      this.stopListening();
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.isConnected = false;
  }

  /**
   * Notify the Chrome extension that preferences have been updated
   * This triggers all open tabs to refresh their analysis
   */
  notifyExtensionPreferencesUpdated(preferences) {
    console.log('[VoiceClient] Notifying extension of preference update');

    // Method 1: Send via Chrome extension API (if running in extension context)
    if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
      try {
        chrome.runtime.sendMessage({
          type: 'VOICE_SESSION_COMPLETE',
          payload: { preferences }
        }, (response) => {
          if (chrome.runtime.lastError) {
            console.log('[VoiceClient] Extension notification error:', chrome.runtime.lastError);
          } else {
            console.log('[VoiceClient] Extension notified successfully');
          }
        });
      } catch (err) {
        console.log('[VoiceClient] Could not send to extension:', err);
      }
    }

    // Method 2: Broadcast via BroadcastChannel (for same-origin pages)
    try {
      const channel = new BroadcastChannel('interestlens_preferences');
      channel.postMessage({
        type: 'PREFERENCES_UPDATED',
        preferences,
        timestamp: Date.now()
      });
      channel.close();
      console.log('[VoiceClient] Broadcast channel message sent');
    } catch (err) {
      console.log('[VoiceClient] BroadcastChannel not supported');
    }

    // Method 3: Store in localStorage and trigger storage event
    try {
      localStorage.setItem('interestlens_preferences_updated', JSON.stringify({
        timestamp: Date.now(),
        preferences
      }));
      console.log('[VoiceClient] Preferences stored in localStorage');
    } catch (err) {
      console.log('[VoiceClient] Could not store in localStorage');
    }
  }

  /**
   * Convert Float32Array to Int16Array (PCM)
   */
  float32ToInt16(float32Array) {
    const int16Array = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return int16Array;
  }

  /**
   * Convert ArrayBuffer to base64 string
   */
  arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }
}

// Export for use in Chrome extension
if (typeof module !== 'undefined' && module.exports) {
  module.exports = VoiceClient;
}
