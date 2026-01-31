import React, { useEffect, useState } from 'react';
import type { AuthState, ScoredItem } from '../shared/types';

interface ProfileSummary {
  topTopics: [string, number][];
}

export default function App() {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    user: null,
    token: null,
  });
  const [items, setItems] = useState<ScoredItem[]>([]);
  const [profileSummary, setProfileSummary] = useState<ProfileSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Get initial auth state
    chrome.runtime.sendMessage({ type: 'GET_AUTH_STATE' }, (response) => {
      setAuthState(response);
      setLoading(false);
    });

    // Listen for auth state changes
    chrome.runtime.onMessage.addListener((message) => {
      if (message.type === 'AUTH_STATE') {
        setAuthState(message.payload);
      }
      if (message.type === 'ANALYSIS_RESULT') {
        setItems(message.payload.items || []);
        setProfileSummary(message.payload.profileSummary || null);
      }
    });
  }, []);

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

      <section className="ranked-list">
        <h2>Ranked for You ({items.length})</h2>

        {items.length === 0 ? (
          <p className="empty">No items analyzed yet. Browse a content-heavy page!</p>
        ) : (
          items.map((item, index) => (
            <div key={item.id} className="item-card">
              <div className="item-header">
                <span className="rank">#{index + 1}</span>
                <span className="score">{item.score}</span>
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
                  <button onClick={() => handleThumbsUp(item)}>👍</button>
                  <button onClick={() => handleThumbsDown(item)}>👎</button>
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
        {authState.isAuthenticated && (
          <button className="settings-btn">⚙️ Settings</button>
        )}
        <a
          href="https://interestlens.vercel.app/onboarding/voice"
          target="_blank"
          rel="noopener"
          className="voice-btn"
        >
          🎤 Voice Preferences
        </a>
      </footer>
    </div>
  );
}
