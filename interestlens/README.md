# InterestLens

**"Your web, ranked for you."**

AI-powered Chrome extension that personalizes any webpage by highlighting the content most relevant to you.

## Features

- **Google Authentication** - Login for cross-device profile sync
- **Voice Onboarding** - Tell the AI your interests through natural conversation
- **Text Onboarding** - Alternative text-based preference setup
- **Smart Highlighting** - Top items highlighted with gold/blue borders
- **Transparent Explanations** - See why each item is ranked high
- **Continuous Learning** - Clicks and thumbs feedback refine preferences over time
- **Real-time Updates** - WebSocket notifications for instant preference sync

## Tech Stack

| Component | Technology |
|-----------|------------|
| Extension | Chrome MV3, React 18, TypeScript 5, Vite, CRXJS |
| Backend | FastAPI, Python 3.11+, Uvicorn |
| AI Agents | Google Gemini 2.0 Flash (Extractor, Scorer, Explainer) |
| Vector DB | Redis Stack (Vector Search + JSON) |
| Observability | W&B Weave |
| URL Preview | Browserbase + Stagehand |
| Voice | Daily.co + Pipecat + OpenAI TTS/STT |

---

## Prerequisites

### Required Software

| Requirement | Version | Check Command | Installation |
|-------------|---------|---------------|--------------|
| Python | 3.11+ | `python3 --version` | [python.org](https://python.org) |
| Node.js | 18+ | `node --version` | [nodejs.org](https://nodejs.org) |
| npm | 9+ | `npm --version` | Comes with Node.js |
| Redis Stack | 7+ | `redis-server --version` | See below |
| Chrome | Latest | - | Developer mode enabled |

### Installing Redis Stack

**macOS (Homebrew):**
```bash
brew tap redis-stack/redis-stack
brew install redis-stack
brew services start redis-stack
```

**Docker (recommended for cross-platform):**
```bash
docker run -d --name redis-stack -p 6379:6379 -p 8002:8001 redis/redis-stack:latest
```

**Linux:**
```bash
curl -fsSL https://packages.redis.io/gpg | sudo gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/redis.list
sudo apt-get update
sudo apt-get install redis-stack-server
```

---

## External Services Setup

You'll need accounts and API keys for the following services:

### 1. Google Cloud (Required)

**For Gemini API + OAuth:**

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing
3. Enable the **Generative Language API** (Gemini)
4. Go to **APIs & Services → Credentials**
5. Create an **API Key** for Gemini
6. Create **OAuth 2.0 Client ID**:
   - Application type: Web application
   - Authorized redirect URIs:
     - `http://localhost:8001/auth/callback`
     - `http://localhost:3000/auth/callback` (if using webapp)

### 2. Redis (Required)

- **Local:** Use Redis Stack (installed above)
- **Cloud:** [Redis Cloud](https://redis.com/try-free/) free tier available

### 3. Weights & Biases (Required for observability)

1. Sign up at [wandb.ai](https://wandb.ai)
2. Get API key from [wandb.ai/authorize](https://wandb.ai/authorize)
3. Create a project named `interestlens`

### 4. Daily.co (Required for voice onboarding)

1. Sign up at [daily.co](https://daily.co)
2. Get API key from Dashboard → Developers → API Keys
3. Note your domain (e.g., `yourname.daily.co`)

### 5. OpenAI (Required for voice TTS/STT)

1. Get API key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Used for Whisper (speech-to-text) and TTS (text-to-speech)

### 6. Browserbase (Optional - for URL previews)

1. Sign up at [browserbase.com](https://browserbase.com)
2. Get API key and Project ID from dashboard

---

## Step-by-Step Setup

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd interestlens
```

### Step 2: Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create Python virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# OR
.venv\Scripts\activate     # Windows

# Install Python dependencies
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your API keys
nano .env  # or use your preferred editor
```

**Required `.env` variables:**

```bash
# Google Cloud - Gemini API (REQUIRED)
GOOGLE_API_KEY=your-gemini-api-key
GOOGLE_CLOUD_PROJECT=your-project-id

# Google OAuth (REQUIRED for authentication)
GOOGLE_CLIENT_ID=your-oauth-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-oauth-client-secret

# Redis Connection (REQUIRED)
REDIS_URL=redis://localhost:6379

# JWT Authentication (REQUIRED - generate a secure secret)
JWT_SECRET=your-secure-random-string-at-least-32-chars
JWT_ALGORITHM=HS256

# W&B Weave Observability (REQUIRED)
WANDB_API_KEY=your-wandb-api-key
WANDB_PROJECT=interestlens

# Frontend URLs (REQUIRED)
FRONTEND_URL=http://localhost:3000
EXTENSION_ID=your-chrome-extension-id

# Daily.co Voice (REQUIRED for voice onboarding)
DAILY_API_KEY=your-daily-api-key
DAILY_DOMAIN=your-domain.daily.co

# OpenAI TTS/STT (REQUIRED for voice)
OPENAI_API_KEY=your-openai-api-key

# Browserbase (OPTIONAL - for URL previews)
BROWSERBASE_API_KEY=your-browserbase-key
BROWSERBASE_PROJECT_ID=your-project-id
```

**Generate a secure JWT secret:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Step 4: Start Redis

```bash
# If using local Redis Stack
redis-server

# OR if using Docker
docker start redis-stack
```

### Step 5: Start the Backend Server

```bash
# Make sure you're in the backend directory with venv activated
cd backend
source .venv/bin/activate

# Start the server
python main.py
```

The backend will be available at:
- **API:** `http://localhost:8001`
- **Health Check:** `http://localhost:8001/health`
- **OpenAPI Docs:** `http://localhost:8001/docs`
- **ReDoc:** `http://localhost:8001/redoc`

### Step 6: Extension Setup

Open a **new terminal** window:

```bash
# Navigate to extension directory
cd interestlens/extension

# Install Node.js dependencies
npm install

# Build the extension
npm run build
```

### Step 7: Load Extension in Chrome

1. Open Chrome and navigate to `chrome://extensions`
2. Enable **Developer mode** (toggle in top-right corner)
3. Click **Load unpacked**
4. Select the `extension/dist` folder
5. **Copy the Extension ID** (shown under the extension name)
6. **Update your `.env`** with the Extension ID:
   ```bash
   EXTENSION_ID=abcdefghijklmnopqrstuvwxyz
   ```
7. **Restart the backend** to pick up the new Extension ID

### Step 8: Verify Installation

1. **Check backend health:**
   ```bash
   curl http://localhost:8001/health
   # Should return: {"status":"healthy"}
   ```

2. **Check extension:**
   - Click the InterestLens icon in Chrome toolbar
   - The side panel should open
   - You should see "Limited Mode" if not logged in

3. **Test authentication:**
   - Click "Login with Google" in the side panel
   - Complete OAuth flow
   - You should see your name after login

---

## Usage Guide

### Voice Onboarding (Recommended)

1. Click the InterestLens extension icon to open the side panel
2. Click **"🎤 Tell me your interests"**
3. A Daily.co voice room will be created
4. Click **"Open Voice Room"** to join
5. Speak naturally about your interests (e.g., "I love AI, technology, and programming")
6. Say **"that's all"** when done
7. Confirm with **"yes"** when the bot summarizes your interests
8. The page will automatically refresh with personalized highlights

### Text-Based Onboarding (Alternative)

If voice doesn't work, you can use the text API directly:

```bash
# Start a text session
curl -X POST http://localhost:8001/voice/text-message \
  -H "Content-Type: application/json" \
  -d '{"session_id": "my-session", "message": "I love technology and AI"}'

# Continue the conversation
curl -X POST http://localhost:8001/voice/text-message \
  -H "Content-Type: application/json" \
  -d '{"session_id": "my-session", "message": "thats all"}'

# Confirm
curl -X POST http://localhost:8001/voice/text-message \
  -H "Content-Type: application/json" \
  -d '{"session_id": "my-session", "message": "yes"}'
```

### Browsing with Personalization

1. Navigate to any content-heavy page (news sites, Reddit, Hacker News, etc.)
2. The extension automatically analyzes the page
3. Top items are highlighted:
   - **Gold border:** Top 2 most relevant items
   - **Blue border:** Items 3-5
4. Hover over items to see topics and relevance score
5. Open the side panel to see ranked list with explanations

### Providing Feedback

- **👍 Thumbs up:** Click to indicate you like content like this
- **👎 Thumbs down:** Click to indicate you're not interested
- **Clicks:** Simply clicking on highlighted items helps refine your profile

---

## API Reference

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/analyze_page` | Analyze and score page items |
| `POST` | `/event` | Log user interaction (click, thumbs) |

### Authentication Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/auth/google` | Initiate Google OAuth |
| `GET` | `/auth/callback` | OAuth callback handler |
| `GET` | `/auth/me` | Get current user info |
| `POST` | `/auth/dev-token` | Generate dev token (dev only) |

### Voice Onboarding Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/voice/start-session` | Create Daily.co voice room |
| `POST` | `/voice/text-message` | Send text message (fallback) |
| `GET` | `/voice/text-session/opening` | Get opening message |
| `POST` | `/voice/text-session/{id}/end` | End text session |
| `GET` | `/voice/session/{id}/status` | Get session status |
| `WS` | `/voice/session/{id}/updates` | WebSocket for real-time updates |
| `GET` | `/voice/preferences` | Get user preferences |
| `POST` | `/voice/save-preferences` | Save preferences |
| `DELETE` | `/voice/preferences` | Clear preferences |
| `GET` | `/voice/debug/user-profile` | Debug: view user profile |

### Utility Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/preview_url?url=...` | Generate URL preview |
| `POST` | `/check_authenticity` | Verify content authenticity |

Full interactive API documentation: `http://localhost:8001/docs`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Chrome Extension                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │  Content    │  │  Service    │  │  Side Panel │                  │
│  │  Script     │  │  Worker     │  │  (React)    │                  │
│  │  (DOM)      │  │  (Background)│  │             │                  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                  │
└─────────┼────────────────┼────────────────┼─────────────────────────┘
          │                │                │
          └────────────────┼────────────────┘
                           │ HTTP/WebSocket
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend (Port 8001)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │  Auth       │  │  Voice      │  │  Activity   │                  │
│  │  Routes     │  │  Routes     │  │  Routes     │                  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                  │
│         │                │                │                          │
│         └────────────────┼────────────────┘                          │
│                          ▼                                           │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    AI Agent Pipeline                           │  │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐                  │  │
│  │  │ Extractor │─▶│  Scorer   │─▶│ Explainer │                  │  │
│  │  │ (Gemini)  │  │ (Gemini)  │  │ (Gemini)  │                  │  │
│  │  └───────────┘  └───────────┘  └───────────┘                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                          │                                           │
│                          ▼                                           │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              Redis Stack (Vectors + JSON + Cache)              │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### AI Pipeline Flow

1. **Extractor Agent** - Identifies content items on the page with topics
2. **Scorer Agent** - Calculates interest scores (0-100) using user profile
3. **Explainer Agent** - Generates human-readable "why" explanations

---

## Project Structure

```
interestlens/
├── backend/                    # FastAPI Backend
│   ├── main.py                # Application entry point (port 8001)
│   ├── requirements.txt       # Python dependencies
│   ├── .env.example          # Environment template
│   ├── .venv/                # Python virtual environment
│   ├── auth/                  # Google OAuth & JWT
│   │   ├── routes.py         # Auth endpoints
│   │   ├── jwt.py            # Token generation/validation
│   │   └── dependencies.py   # Auth middleware
│   ├── agents/               # AI Agent Pipeline
│   │   └── pipeline.py       # 3-agent orchestration
│   ├── voice/                # Voice Onboarding
│   │   ├── routes.py         # Voice API endpoints
│   │   ├── bot.py            # Conversational agent logic
│   │   ├── pipeline.py       # Pipecat voice processing
│   │   ├── session_manager.py # Daily.co room management
│   │   ├── text_fallback.py  # Text-based alternative
│   │   ├── websocket.py      # Real-time notifications
│   │   └── extraction.py     # Preference extraction
│   ├── services/             # Core Services
│   │   ├── redis_client.py   # Redis vector DB
│   │   └── profile.py        # User profiles
│   ├── models/               # Pydantic Models
│   │   ├── requests.py       # API request schemas
│   │   ├── responses.py      # API response schemas
│   │   └── profile.py        # User profile model
│   └── tests/                # Test suite
│
├── extension/                 # Chrome Extension (MV3)
│   ├── manifest.json         # Extension manifest
│   ├── package.json          # Node dependencies
│   ├── vite.config.ts        # Vite + CRXJS config
│   ├── src/
│   │   ├── content/          # Content script
│   │   │   └── index.ts      # DOM extraction & overlays
│   │   ├── background/       # Service worker
│   │   │   └── service-worker.ts
│   │   ├── sidepanel/        # React side panel
│   │   │   ├── App.tsx       # Main UI component
│   │   │   └── styles.css    # Styling
│   │   └── shared/           # Shared utilities
│   │       ├── api.ts        # API communication
│   │       └── types.ts      # TypeScript types
│   ├── popup.html            # Extension popup
│   ├── sidepanel.html        # Side panel entry
│   └── dist/                 # Built extension
│
└── webapp/                    # Next.js Web App (Optional)
    └── ...
```

---

## Development

### Running in Development Mode

**Backend with auto-reload:**
```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

**Extension with hot reload:**
```bash
cd extension
npm run dev
```
Then reload the extension in Chrome (`chrome://extensions` → refresh icon).

### Running Tests

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

### Useful Debug Commands

```bash
# Check backend health
curl http://localhost:8001/health

# Check user profile (for anonymous user)
curl http://localhost:8001/voice/debug/user-profile

# Get voice preferences
curl http://localhost:8001/voice/preferences

# Clear preferences (to re-onboard)
curl -X DELETE http://localhost:8001/voice/preferences

# View API docs
open http://localhost:8001/docs
```

---

## Troubleshooting

### Backend Issues

**"Redis connection failed":**
```bash
# Check if Redis is running
redis-cli ping
# Should return: PONG

# If not running, start it:
redis-server
# OR with Docker:
docker start redis-stack
```

**"Module not found" errors:**
```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

**"Address already in use" (port 8001):**
```bash
# Find and kill the process using the port
lsof -i :8001
kill -9 <PID>

# Or use a different port
uvicorn main:app --port 8002
```

### Extension Issues

**Extension not loading:**
- Ensure you're loading the `dist/` folder, not `src/`
- Run `npm run build` first
- Check Chrome console: `chrome://extensions` → Details → "Inspect views"

**"Failed to fetch" or CORS errors:**
- Verify backend is running on port 8001
- Check that EXTENSION_ID in `.env` matches your extension
- Restart the backend after changing EXTENSION_ID

**Side panel not opening:**
- Click the extension icon (puzzle piece) in toolbar
- Pin InterestLens for easier access
- Try right-clicking the extension icon

### Voice Issues

**"Daily API key not configured":**
- Add DAILY_API_KEY to your `.env` file
- Restart the backend

**Voice room opens but no response:**
- Check OPENAI_API_KEY is set (required for TTS/STT)
- Check backend logs for errors
- Ensure microphone permissions are granted

**Text fallback not working:**
- Use the `/voice/text-message` endpoint directly
- Check backend logs for extraction errors

### OAuth Issues

**"Redirect URI mismatch":**
1. Go to Google Cloud Console → APIs & Services → Credentials
2. Edit your OAuth 2.0 Client ID
3. Add these to Authorized redirect URIs:
   - `http://localhost:8001/auth/callback`
   - `http://localhost:3000/auth/callback` (if using webapp)

**"Invalid client" error:**
- Verify GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in `.env`
- Ensure no extra spaces or quotes in the values

---

## Common Workflows

### Reset and Re-onboard

```bash
# Clear your preferences
curl -X DELETE http://localhost:8001/voice/preferences

# Verify cleared
curl http://localhost:8001/voice/debug/user-profile
# Should show voice_onboarding_complete: false
```

### View Your Profile

```bash
curl http://localhost:8001/voice/debug/user-profile | python3 -m json.tool
```

### Test Scoring

```bash
curl -X POST http://localhost:8001/analyze_page \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "anonymous",
    "page_url": "https://test.com",
    "dom_outline": "Test page",
    "items": [
      {"id": "1", "text": "AI news", "bbox": [0,0,100,50]},
      {"id": "2", "text": "Sports update", "bbox": [0,60,100,50]}
    ]
  }'
```

---

## Team

Built at WB Hackathon 2026

## License

MIT
