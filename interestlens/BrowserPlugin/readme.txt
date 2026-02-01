InterestLens Chrome Extension v2.1
===================================

AI-powered content personalization with voice onboarding,
activity tracking, and interest-based content highlighting.

NEW FEATURES (v2.1):
--------------------
1. First-Time User Welcome Flow
   - Welcome modal appears on first browser open after install
   - Explains the extension features and offers voice setup

2. Voice Onboarding (Daily.co Integration)
   - Interactive voice conversation with AI assistant
   - Tell the AI your interests and topics to avoid
   - Categories extracted and saved automatically
   - Falls back to text chat if voice unavailable

3. Activity Tracking
   - Tracks URL visits and time spent on pages
   - Detects content categories from page metadata
   - Records click interactions on articles/links
   - Syncs activity data to backend for personalization

4. Content Highlighting
   - Content matching your interests gets subtle highlighting
   - High-interest items show "For You" badge
   - Medium matches show "Match" badge
   - Disliked categories are dimmed
   - Works on any website automatically

HOW TO LOAD:
------------
1) Open Chrome -> chrome://extensions
2) Enable "Developer mode" (toggle in top right)
3) Click "Load unpacked" and select this BrowserPlugin folder
4) The extension will automatically inject on all web pages

FIRST TIME SETUP:
-----------------
1) After loading the extension, open any webpage
2) A welcome modal will appear explaining the features
3) Click "Start Voice Setup" to begin voice onboarding
4) Talk to the AI about your interests (or use text chat)
5) Once complete, content highlighting begins automatically

KEYBOARD SHORTCUTS:
-------------------
- Ctrl+Shift+S (Windows) / Cmd+Shift+S (Mac): Toggle sidebar visibility

FILES:
------
Core Extension:
- manifest.json   - Extension configuration (v2.1.0)
- background.js   - Service worker for API calls
- content.js      - Sidebar DOM creation

Onboarding:
- welcome.js      - First-time user detection and welcome modal
- welcome.css     - Welcome modal styling

Activity Tracking:
- tracker.js      - Browsing activity tracking (URLs, time, clicks)

Highlighting:
- highlighter.js  - Content detection and highlighting logic
- highlighter.css - Highlight styling (subtle borders/badges)

Sidebar:
- sidebar.js      - Card rendering and voice interaction
- sidebar.css     - Modern UI with light/dark mode

Legacy:
- authLens.js     - Legacy authenticity launcher
- authLens.css    - Legacy launcher styling

REQUIREMENTS:
-------------
The extension requires these backend services running:
1) Scraper API on http://localhost:8000 (for page scraping)
2) Backend API on http://localhost:8001 (for voice, activity, preferences)

To start the backend:
  cd interestlens/backend
  source .venv/bin/activate  (or create venv first)
  python main.py

BACKEND ENDPOINTS USED:
-----------------------
Voice Onboarding:
- POST /voice/start-session    - Create Daily.co voice room
- POST /voice/text-message     - Send text for fallback chat
- GET  /voice/preferences      - Get user's extracted categories
- POST /voice/save-preferences - Save preferences

Activity Tracking:
- POST /activity/track         - Send browsing activity data
- GET  /activity/history       - Get activity history
- GET  /activity/categories    - Get learned categories

Authenticity (existing):
- POST /check_authenticity/batch - Check article authenticity

DEBUGGING:
----------
In browser console, you can access:
- window.__interestLensSidebar    - Sidebar API
- window.__interestLensWelcome    - Welcome modal API
- window.__interestLensTracker    - Activity tracker API
- window.__interestLensHighlighter - Highlighter API

Reset onboarding:
  window.__interestLensWelcome.reset()

Refresh highlights:
  window.__interestLensHighlighter.refresh()

PRIVACY:
--------
- Browsing data stored in Redis with user ID
- No third-party analytics
- Activity data used only for personalization
- Voice conversations processed but not permanently stored
- All data can be cleared via backend endpoints

VERSION HISTORY:
----------------
v2.1.0 - Added welcome flow, voice onboarding, activity tracking, highlighting
v2.0.0 - Added modern sidebar UI with light/dark mode
v1.0.0 - Initial release with authenticity checking
