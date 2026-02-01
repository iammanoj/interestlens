# InterestLens

**"Your web, ranked for you."**

AI-powered Chrome extension that personalizes any webpage by highlighting the content most relevant to you.

## Features

- **Google Authentication** - Login for cross-device profile sync
- **Voice Onboarding** - Tell the AI your interests through conversation
- **Smart Highlighting** - Top 5 items highlighted on any page
- **Transparent Explanations** - See why each item is ranked high
- **Continuous Learning** - Clicks refine preferences over time

## Tech Stack

| Component | Technology |
|-----------|------------|
| Extension | Chrome MV3, React 18, TypeScript 5, Vite |
| Backend | FastAPI, Python 3.8+, Uvicorn |
| AI Agents | Google Cloud ADK, Gemini 2.0 Flash |
| Vector DB | Redis Stack (Vector Search + JSON) |
| Observability | W&B Weave |
| URL Preview | Browserbase + Stagehand |
| Voice | Daily.co + Pipecat |
| Deployment | Vercel |

## Prerequisites

Before building, ensure you have the following installed:

| Requirement | Version | Check Command |
|-------------|---------|---------------|
| Python | 3.8+ | `python --version` |
| Node.js | 16+ | `node --version` |
| npm | 8+ | `npm --version` |
| Redis | 7+ (with RediSearch & RedisJSON) | `redis-server --version` |
| Chrome | Latest | Developer mode enabled |

### External Services Required

You'll need accounts and API keys for:

1. **Google Cloud** - For Gemini API and OAuth
   - Create project at [console.cloud.google.com](https://console.cloud.google.com)
   - Enable Generative AI API
   - Create OAuth 2.0 credentials

2. **Redis** - Vector database and caching
   - Local: Install Redis Stack (`brew install redis-stack` on macOS)
   - Cloud: [Redis Cloud](https://redis.com/try-free/) free tier

3. **Weights & Biases** - Observability
   - Sign up at [wandb.ai](https://wandb.ai)
   - Get API key from [wandb.ai/authorize](https://wandb.ai/authorize)

4. **Daily.co** - Voice infrastructure (optional, for voice onboarding)
   - Sign up at [daily.co](https://daily.co)
   - Get API key from dashboard

5. **Browserbase** - URL previews (optional)
   - Sign up at [browserbase.com](https://browserbase.com)

6. **OpenAI** - Text-to-speech (optional, for voice)
   - Get API key from [platform.openai.com](https://platform.openai.com)

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd interestlens
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment variables template
cp .env.example .env

# Edit .env with your API keys (see Environment Variables section below)

# Start Redis (if running locally)
redis-server

# Run the backend server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- API: `http://localhost:8000`
- OpenAPI Docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 3. Extension Setup

```bash
cd extension

# Install dependencies
npm install

# Build extension for production
npm run build

# Or run in development mode with hot reload
npm run dev
```

**Loading the extension in Chrome:**

1. Open `chrome://extensions` in Chrome
2. Enable **Developer mode** (toggle in top right)
3. Click **Load unpacked**
4. Select the `extension/dist` folder
5. Note the **Extension ID** (you'll need this for `.env`)

### 4. Web App Setup (Optional - for Login + Voice UI)

```bash
cd webapp

# Install dependencies
npm install

# Run development server
npm run dev
```

The webapp will be available at `http://localhost:3000`

## Environment Variables

Create `backend/.env` with the following variables:

### Required Variables

```bash
# Google Cloud - Gemini API
GOOGLE_API_KEY=your-gemini-api-key

# Google OAuth Credentials
GOOGLE_CLIENT_ID=your-oauth-client-id
GOOGLE_CLIENT_SECRET=your-oauth-client-secret
GOOGLE_CLOUD_PROJECT=your-project-id

# Redis Connection
REDIS_URL=redis://localhost:6379

# JWT Authentication
JWT_SECRET=your-secure-random-string-change-this
JWT_ALGORITHM=HS256

# W&B Weave Observability
WANDB_API_KEY=your-wandb-api-key
WANDB_PROJECT=interestlens

# Frontend Configuration
FRONTEND_URL=http://localhost:3000
EXTENSION_ID=your-chrome-extension-id
```

### Optional Variables

```bash
# Daily.co - Voice Onboarding
DAILY_API_KEY=your-daily-key
DAILY_DOMAIN=your-domain.daily.co

# Browserbase - URL Preview
BROWSERBASE_API_KEY=your-browserbase-key
BROWSERBASE_PROJECT_ID=your-project-id

# OpenAI - Text-to-Speech
OPENAI_API_KEY=your-openai-api-key
```

### Generating JWT Secret

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Project Structure

```
interestlens/
├── backend/                    # FastAPI Backend
│   ├── main.py                # Application entry point
│   ├── requirements.txt       # Python dependencies
│   ├── .env.example          # Environment template
│   ├── auth/                  # Google OAuth & JWT
│   │   ├── routes.py         # Auth endpoints
│   │   ├── jwt.py            # Token generation/validation
│   │   └── dependencies.py   # Auth middleware
│   ├── agents/               # AI Agent Pipeline
│   │   ├── pipeline.py       # 3-agent orchestration
│   │   └── authenticity.py   # Content verification
│   ├── voice/                # Voice Onboarding
│   │   ├── routes.py         # Voice API endpoints
│   │   ├── bot.py            # Conversational agent
│   │   ├── pipeline.py       # Voice processing
│   │   └── session_manager.py # Daily.co integration
│   ├── services/             # Core Services
│   │   ├── redis_client.py   # Redis vector DB
│   │   ├── browserbase.py    # URL previews
│   │   └── profile.py        # User profiles
│   ├── models/               # Pydantic Models
│   │   ├── requests.py       # API request schemas
│   │   ├── responses.py      # API response schemas
│   │   └── profile.py        # User profile model
│   ├── activity/             # User Activity Tracking
│   └── tests/                # Test suite
│
├── extension/                 # Chrome Extension (MV3)
│   ├── manifest.json         # Extension manifest
│   ├── package.json          # Node dependencies
│   ├── vite.config.ts        # Vite build config
│   ├── tsconfig.json         # TypeScript config
│   ├── src/
│   │   ├── content/          # Content script (DOM extraction)
│   │   │   └── index.ts
│   │   ├── background/       # Service worker
│   │   │   └── service-worker.ts
│   │   ├── sidepanel/        # React side panel UI
│   │   │   ├── App.tsx
│   │   │   └── styles.css
│   │   └── shared/           # Shared utilities
│   │       ├── api.ts        # API communication
│   │       └── types.ts      # TypeScript types
│   ├── popup.html            # Extension popup
│   ├── sidepanel.html        # Side panel entry
│   └── dist/                 # Built extension (gitignored)
│
├── webapp/                    # Next.js Web App
│   ├── app/
│   │   ├── page.tsx          # Landing page
│   │   ├── login/            # OAuth login
│   │   ├── auth/callback/    # OAuth callback
│   │   └── onboarding/voice/ # Voice setup
│   └── components/           # React components
│
└── experiments/               # Marimo notebooks
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Chrome         │────▶│  FastAPI        │────▶│  Redis Stack    │
│  Extension      │     │  Backend        │     │  (Vectors+JSON) │
│  (MV3)          │◀────│  (Port 8000)    │◀────│                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  3-Agent AI     │
                        │  Pipeline       │
                        │  (Gemini 2.0)   │
                        └─────────────────┘
                               │
                        ┌──────┼──────┐
                        ▼      ▼      ▼
                   Extractor Scorer Explainer
```

### AI Pipeline Flow

1. **Extractor Agent** - Analyzes page screenshot with Gemini Vision, identifies items
2. **Scorer Agent** - Calculates interest scores using embeddings and user profile
3. **Explainer Agent** - Generates human-readable explanations for rankings

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/analyze_page` | Analyze webpage and score items |
| `POST` | `/event` | Log user interaction |
| `POST` | `/preview_url` | Generate URL preview |
| `GET` | `/auth/google/login` | Initiate Google OAuth |
| `GET` | `/auth/google/callback` | OAuth callback handler |
| `POST` | `/voice/start-session` | Create voice session |
| `POST` | `/voice/text-message` | Text-based voice interaction |
| `GET` | `/voice/preferences` | Get user preferences |
| `POST` | `/check_authenticity` | Verify content authenticity |

Full API documentation available at `http://localhost:8000/docs` when running.

## Development

### Running in Development Mode

**Backend with auto-reload:**
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Extension with hot reload:**
```bash
cd extension
npm run dev
```
Then reload the extension in Chrome after making changes.

### Running Tests

```bash
cd backend
source venv/bin/activate
pytest tests/ -v
```

### API Testing

```bash
# Test the analyze endpoint
curl -X POST http://localhost:8000/analyze_page \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "html": "<html>...</html>"}'

# Check health
curl http://localhost:8000/
```

## Demo Flow

1. **Login** - Click extension icon → Login with Google
2. **Voice Onboarding** - Tell the AI your interests through conversation
3. **Browse** - Visit any content-heavy page (news sites, Reddit, etc.)
4. **See Highlights** - Top 5 items highlighted with scores + explanations
5. **Learn** - Click items to refine your profile over time

## Troubleshooting

### Backend Issues

**Redis connection failed:**
```bash
# Start Redis server
redis-server

# Or use Docker
docker run -d -p 6379:6379 redis/redis-stack:latest
```

**Import errors:**
```bash
# Ensure venv is activated and dependencies installed
source venv/bin/activate
pip install -r requirements.txt
```

### Extension Issues

**Extension not loading:**
- Ensure you're loading the `dist/` folder, not `src/`
- Check Chrome console for errors (`chrome://extensions` → Details → Inspect views)

**CORS errors:**
- Verify backend is running on port 8000
- Check CORS configuration in `backend/main.py`

### OAuth Issues

**Redirect URI mismatch:**
- Add `http://localhost:8000/auth/google/callback` to authorized redirect URIs in Google Cloud Console
- Add `http://localhost:3000/auth/callback` if using webapp

## Team

Built at WB Hackathon 2026

## License

MIT
