import { useEffect, useState, useCallback } from 'react';
import type { AuthState, ScoredItem } from '../shared/types';

interface ProfileSummary {
  topTopics: [string, number][];
}

interface VoiceSession {
  isActive: boolean;
  roomUrl?: string;
  token?: string;
  status: 'idle' | 'connecting' | 'listening' | 'processing' | 'complete' | 'error';
  transcripts: { speaker: string; text: string }[];
  preferences?: any;
  error?: string;
}

const API_BASE = 'http://localhost:8001';

export default function App() {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    user: null,
    token: null,
  });
  const [items, setItems] = useState<ScoredItem[]>([]);
  const [profileSummary, setProfileSummary] = useState<ProfileSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [voiceSession, setVoiceSession] = useState<VoiceSession>({
    isActive: false,
    status: 'idle',
    transcripts: [],
  });
  const [showVoicePanel, setShowVoicePanel] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<number>(Date.now());

  // Function to request page analysis
  const requestAnalysis = useCallback(async () => {
    setAnalyzing(true);
    try {
      // Get the current tab
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id) {
        // Ask content script to re-analyze
        chrome.tabs.sendMessage(tab.id, { type: 'REFRESH_ANALYSIS' });
      }
    } catch (error) {
      console.error('Error requesting analysis:', error);
    }
    // Analyzing state will be cleared when we receive results
    setTimeout(() => setAnalyzing(false), 5000); // Timeout fallback
  }, []);

  useEffect(() => {
    // Get initial auth state
    chrome.runtime.sendMessage({ type: 'GET_AUTH_STATE' }, (response) => {
      setAuthState(response);
      setLoading(false);
    });

    // Listen for messages
    const messageListener = (message: any) => {
      console.log('[Sidepanel] Received message:', message.type);

      if (message.type === 'AUTH_STATE') {
        setAuthState(message.payload);
      }
      if (message.type === 'ANALYSIS_RESULT') {
        setItems(message.payload.items || []);
        setProfileSummary(message.payload.profileSummary || null);
        setAnalyzing(false);
        setLastRefresh(Date.now());
      }
      if (message.type === 'REFRESH_ANALYSIS' || message.type === 'PREFERENCES_UPDATED') {
        console.log('[Sidepanel] Preferences updated, requesting re-analysis');
        setLastRefresh(Date.now());
        requestAnalysis();
      }
    };

    chrome.runtime.onMessage.addListener(messageListener);

    // Listen for BroadcastChannel (cross-tab communication)
    let preferencesChannel: BroadcastChannel | null = null;
    try {
      preferencesChannel = new BroadcastChannel('interestlens_preferences');
      preferencesChannel.onmessage = (event) => {
        if (event.data.type === 'PREFERENCES_UPDATED') {
          console.log('[Sidepanel] Received preferences update via BroadcastChannel');
          setLastRefresh(Date.now());
          requestAnalysis();
          // Update voice session if complete
          if (event.data.preferences) {
            setVoiceSession(prev => ({
              ...prev,
              status: 'complete',
              preferences: event.data.preferences,
            }));
          }
        }
      };
    } catch (err) {
      // BroadcastChannel not supported
    }

    // Initial analysis request
    requestAnalysis();

    return () => {
      chrome.runtime.onMessage.removeListener(messageListener);
      preferencesChannel?.close();
    };
  }, [requestAnalysis]);

  const handleLogin = () => {
    chrome.runtime.sendMessage({ type: 'LOGIN' });
  };

  const handleLogout = () => {
    chrome.runtime.sendMessage({ type: 'LOGOUT' });
  };

  const handleThumbsUp = (item: ScoredItem) => {
    chrome.runtime.sendMessage({
      type: 'LOG_EVENT',
      payload: {
        event: 'thumbs_up',
        itemId: item.id,
        pageUrl: window.location.href,
        itemData: { text: '', topics: item.topics },
      },
    });
  };

  const handleThumbsDown = (item: ScoredItem) => {
    chrome.runtime.sendMessage({
      type: 'LOG_EVENT',
      payload: {
        event: 'thumbs_down',
        itemId: item.id,
        pageUrl: window.location.href,
        itemData: { text: '', topics: item.topics },
      },
    });
  };

  // Start voice onboarding session
  const startVoiceSession = async () => {
    setVoiceSession(prev => ({ ...prev, status: 'connecting', transcripts: [], error: undefined }));
    setShowVoicePanel(true);

    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (authState.token) {
        headers['Authorization'] = `Bearer ${authState.token}`;
      }

      const response = await fetch(`${API_BASE}/voice/start-session`, {
        method: 'POST',
        headers,
      });

      if (!response.ok) {
        throw new Error(`Failed to start session: ${response.status}`);
      }

      const session = await response.json();
      console.log('[Sidepanel] Voice session started:', session);

      setVoiceSession(prev => ({
        ...prev,
        isActive: true,
        roomUrl: session.room_url,
        token: session.token,
        status: 'listening',
      }));

      // Connect to WebSocket for real-time updates
      connectToVoiceWebSocket(session.websocket_url || `/voice/session/${session.room_name}/updates`);

    } catch (error: any) {
      console.error('[Sidepanel] Error starting voice session:', error);
      setVoiceSession(prev => ({
        ...prev,
        status: 'error',
        error: error.message,
      }));
    }
  };

  // Connect to voice session WebSocket for real-time transcripts
  const connectToVoiceWebSocket = (wsPath: string) => {
    const wsUrl = `${API_BASE.replace('http', 'ws')}${wsPath}`;
    console.log('[Sidepanel] Connecting to WebSocket:', wsUrl);

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[Sidepanel] WebSocket connected');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('[Sidepanel] WebSocket message:', data.type);

      switch (data.type) {
        case 'transcription':
          setVoiceSession(prev => ({
            ...prev,
            transcripts: [...prev.transcripts, { speaker: data.speaker, text: data.text }],
          }));
          break;

        case 'preference_update':
          setVoiceSession(prev => ({
            ...prev,
            preferences: data.preferences,
          }));
          break;

        case 'session_complete':
          console.log('[Sidepanel] Voice session complete');
          setVoiceSession(prev => ({
            ...prev,
            status: 'complete',
            isActive: false,
            preferences: data.preferences,
          }));
          // Trigger page re-analysis with new preferences
          setTimeout(() => {
            requestAnalysis();
          }, 500);
          break;

        case 'error':
          setVoiceSession(prev => ({
            ...prev,
            status: 'error',
            error: data.error,
          }));
          break;
      }
    };

    ws.onerror = (error) => {
      console.error('[Sidepanel] WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('[Sidepanel] WebSocket closed');
    };
  };

  const handleRefresh = () => {
    requestAnalysis();
  };

  if (loading) {
    return <div className="loading">Loading...</div>;
  }

  return (
    <div className="sidepanel">
      <header className="header">
        <h1>🔍 InterestLens</h1>
        {!authState.isAuthenticated && (
          <span className="mode-badge">Limited Mode</span>
        )}
        <button
          onClick={handleRefresh}
          className="refresh-btn"
          disabled={analyzing}
          title="Refresh analysis"
        >
          {analyzing ? '⏳' : '🔄'}
        </button>
      </header>

      {!authState.isAuthenticated ? (
        <div className="login-prompt">
          <p>Login to personalize your experience</p>
          <button onClick={handleLogin} className="login-btn">
            🔵 Login with Google
          </button>
        </div>
      ) : (
        <div className="user-info">
          <span>👤 {authState.user?.name}</span>
          <button onClick={handleLogout} className="logout-btn">
            Logout
          </button>
        </div>
      )}

      {/* Voice Onboarding Section */}
      <section className="voice-section">
        {!showVoicePanel ? (
          <button onClick={startVoiceSession} className="voice-start-btn">
            🎤 Tell me your interests
          </button>
        ) : (
          <div className="voice-panel">
            <div className="voice-status">
              {voiceSession.status === 'connecting' && '🔄 Connecting...'}
              {voiceSession.status === 'listening' && '🎤 Listening... Speak your interests!'}
              {voiceSession.status === 'processing' && '⏳ Processing...'}
              {voiceSession.status === 'complete' && '✅ Preferences saved!'}
              {voiceSession.status === 'error' && `❌ Error: ${voiceSession.error}`}
            </div>

            {voiceSession.transcripts.length > 0 && (
              <div className="transcripts">
                {voiceSession.transcripts.slice(-5).map((t, i) => (
                  <div key={i} className={`transcript ${t.speaker}`}>
                    <span className="speaker">{t.speaker === 'user' ? '🗣️' : '🤖'}</span>
                    <span className="text">{t.text}</span>
                  </div>
                ))}
              </div>
            )}

            {voiceSession.status === 'complete' && (
              <div className="voice-complete">
                <p>Your preferences have been saved!</p>
                <p>The page will refresh with personalized content.</p>
                <button onClick={() => setShowVoicePanel(false)} className="close-btn">
                  Close
                </button>
              </div>
            )}

            {voiceSession.status === 'listening' && voiceSession.roomUrl && (
              <div className="voice-join">
                <p>Join the voice room to speak with the assistant:</p>
                <a href={voiceSession.roomUrl} target="_blank" rel="noopener" className="join-btn">
                  🎤 Open Voice Room
                </a>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="ranked-list">
        <h2>
          Ranked for You ({items.length})
          {analyzing && <span className="analyzing-indicator"> ⏳</span>}
        </h2>

        {items.length === 0 ? (
          <p className="empty">
            {analyzing
              ? 'Analyzing page content...'
              : 'No items analyzed yet. Browse a content-heavy page!'}
          </p>
        ) : (
          items.map((item, index) => (
            <div key={item.id} className={`item-card ${item.score > 60 ? 'high-match' : item.score < 40 ? 'low-match' : ''}`}>
              <div className="item-header">
                <span className="rank">#{index + 1}</span>
                <span className={`score ${item.score > 60 ? 'high' : item.score < 40 ? 'low' : ''}`}>
                  {item.score}
                </span>
              </div>
              <div className="item-topics">
                {item.topics.map((topic) => (
                  <span key={topic} className="topic-tag">
                    {topic}
                  </span>
                ))}
              </div>
              <p className="item-why">{item.why}</p>
              {authState.isAuthenticated && (
                <div className="feedback">
                  <button onClick={() => handleThumbsUp(item)} title="I like this">👍</button>
                  <button onClick={() => handleThumbsDown(item)} title="Not interested">👎</button>
                </div>
              )}
            </div>
          ))
        )}
      </section>

      {authState.isAuthenticated && profileSummary && (
        <section className="profile-section">
          <h2>Your Interests</h2>
          <div className="topic-bars">
            {profileSummary.topTopics.map(([topic, score]) => (
              <div key={topic} className="topic-bar">
                <span className="topic-name">{topic}</span>
                <div className="bar">
                  <div
                    className="bar-fill"
                    style={{ width: `${Math.min(100, score * 30)}%` }}
                  />
                </div>
                <span className="topic-score">{score.toFixed(1)}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <footer className="footer">
        <div className="last-update">
          Last updated: {new Date(lastRefresh).toLocaleTimeString()}
        </div>
      </footer>
    </div>
  );
}
