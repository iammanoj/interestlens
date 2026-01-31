# InterestLens

**"Your web, ranked for you."**

AI-powered Chrome extension that personalizes any webpage by highlighting the content most relevant to you.

## Features

- 🔐 **Google Authentication** - Login for cross-device profile sync
- 🎤 **Voice Onboarding** - Tell the AI your interests through conversation
- ✨ **Smart Highlighting** - Top 5 items highlighted on any page
- 💡 **Transparent Explanations** - See why each item is ranked high
- 📈 **Continuous Learning** - Clicks refine preferences over time

## Tech Stack

| Component | Technology |
|-----------|------------|
| Extension | Chrome MV3, React, TypeScript |
| Backend | FastAPI, Python |
| AI Agents | Google Cloud ADK, Gemini 1.5 Pro |
| Vector DB | Redis Stack |
| Observability | W&B Weave |
| URL Preview | Browserbase + Stagehand |
| Voice | Daily + Pipecat |
| Deployment | Vercel |

## Quick Start

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env
# Edit .env with your API keys

# Run the server
uvicorn main:app --reload
```

### 2. Extension Setup

```bash
cd extension

# Install dependencies
npm install

# Build extension
npm run build

# Load in Chrome:
# 1. Go to chrome://extensions
# 2. Enable "Developer mode"
# 3. Click "Load unpacked"
# 4. Select the `dist` folder
```

### 3. Web App Setup (for Login + Voice)

```bash
cd webapp

# Install dependencies
npm install

# Run development server
npm run dev
```

## Environment Variables

See `backend/.env.example` for all required variables:

- `GOOGLE_API_KEY` - Gemini API key
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - OAuth credentials
- `REDIS_URL` - Redis connection string
- `DAILY_API_KEY` - Daily.co API key
- `WANDB_API_KEY` - Weights & Biases API key
- `BROWSERBASE_API_KEY` - Browserbase API key

## Project Structure

```
interestlens/
├── extension/          # Chrome Extension (MV3)
├── backend/            # FastAPI Backend
│   ├── auth/          # Google OAuth
│   ├── voice/         # Daily + Pipecat
│   ├── agents/        # ADK Pipeline
│   └── services/      # Redis, Browserbase
├── webapp/            # Vercel Web App
└── experiments/       # Marimo notebooks
```

## Demo Flow

1. **Login** - Click extension → Login with Google
2. **Voice Onboarding** - Tell the AI your interests
3. **Browse** - Visit any content-heavy page
4. **See Highlights** - Top 5 items with scores + explanations
5. **Learn** - Click items to refine your profile

## Team

Built at WB Hackathon 2026

## License

MIT
