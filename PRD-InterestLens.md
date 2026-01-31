# InterestLens - Product Requirements Document

**"Your web, ranked for you."**

## Executive Summary

InterestLens is a Chrome browser extension that uses AI agents to understand web pages, predict what content a user will care about, and highlight/rank items in real-time. The system learns from implicit feedback (clicks, dwell time) and provides transparent explanations for its rankings.

---

## 1. Project Overview

| Attribute | Value |
|-----------|-------|
| **Product Name** | InterestLens |
| **Type** | Chrome Extension (MV3 + React) + FastAPI Backend + Vercel Deployment |
| **Timeline** | 8-10 hours (1 day hackathon) |
| **Team Size** | 4 people |
| **Team Split** | Extension (React) / Backend (FastAPI) / ML-Agents (ADK) / Auth+Voice |

---

## 2. Problem Statement

Users open web pages (news sites, video platforms, shopping pages) and visually scan large amounts of irrelevant content. There's no personalized signal about what matters to *them* specifically.

**InterestLens solves this by:**
- Understanding page layout and content items via AI agents
- Predicting user interest based on learned preferences
- Highlighting top items directly on the page
- Learning quickly from implicit user behavior

---

## 3. Target Users

- Power users who browse content-heavy sites frequently
- Professionals who need to quickly identify relevant content
- Anyone overwhelmed by information overload on the web

**User Stories:**
- "On a busy page, show me the 5 things I'll likely open."
- "Explain why you ranked something high."
- "Learn my tastes within ~10-20 clicks."
- "Works on YouTube, Hacker News, Amazon category pages."

---

## 4. MVP Scope (8-10 hours)

### 4.1 What We Ship

1. **Google Authentication (Web App)**
   - Separate web app for Google OAuth login
   - User profile synced to extension via secure token
   - Cross-session persistence of preferences

2. **Voice Onboarding (Daily + Pipecat)**
   - Conversational voice agent that learns user interests
   - Open-ended dialogue with follow-up questions
   - Extracts topics + sentiment (likes, dislikes, intensity)
   - Optional but accessible anytime from settings

3. **Chrome Extension (MV3)**
   - Content script that extracts page items and injects overlays
   - Side panel UI with ranked list
   - Syncs with authenticated user profile

4. **Cloud Backend (FastAPI)**
   - `/analyze_page` endpoint for item scoring
   - `/event` endpoint for learning signals
   - `/auth/*` endpoints for Google OAuth
   - `/voice/onboard` endpoint for voice preference extraction
   - 3-agent pipeline: Extractor → Scorer → Explainer

5. **Core Functionality**
   - Detect "items" on any page (links, cards, media tiles)
   - Assign each item: topic tags, interest score (0-100), "why" explanation
   - Visual overlay: outline + glow + score badge on top 5 items
   - Side panel: ranked list with topics and explanations
   - Learning: clicks on items update user profile instantly
   - Voice-learned preferences boost/penalize topics

### 4.2 What We DON'T Ship (Non-Goals)

- ~~Cross-device sync~~ (NOW INCLUDED via Google Auth)
- ~~Account system / login~~ (NOW INCLUDED)
- ~~Perfect cold-start personalization~~ (NOW ADDRESSED via Voice Onboarding)
- Heavy local model training
- Firefox/Safari support
- Offline mode

---

## 5. Technical Architecture

### 5.1 Hackathon Sponsor Tool Integration

| Sponsor Tool | How We Use It | Why It Matters |
|--------------|---------------|----------------|
| **W&B Weave** | Trace every agent call, log embeddings, debug scoring | Full observability - judges see exactly how the AI works |
| **Redis** | Vector search for embeddings, cache scores/profiles, fast memory | Real-time performance, semantic similarity search |
| **Browserbase + Stagehand** | Backend URL preview when user hovers a link | Rich content preview without leaving page |
| **Vercel + v0** | Deploy backend API, generate side panel UI components | Instant deployment, rapid UI prototyping |
| **Daily + Pipecat** | Voice command stretch goal ("Show me AI articles") | Multimodal interaction demo |
| **Marimo** | Experiment with scoring weights, tune prompts | Reproducible notebooks for demo/debugging |
| **Google Cloud ADK** | Full 3-agent pipeline framework | Production-ready agent architecture |
| **Gemini 1.5 Pro** | Vision analysis + topic classification | Multimodal understanding via ADK |

### 5.2 System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Chrome Extension                         │
├─────────────────────────────────────────────────────────────┤
│  Content Script          │  Service Worker  │  Side Panel   │
│  - DOM extraction        │  - Event logging │  - React UI   │
│  - Overlay injection     │  - API calls     │  - (v0 gen)   │
│  - Screenshot capture    │  - State mgmt    │  - Ranked list│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Cloud Backend (FastAPI on Vercel)               │
├─────────────────────────────────────────────────────────────┤
│  POST /analyze_page          │  POST /event                 │
│  - Receives DOM + screenshot │  - Receives user interactions│
│  - Runs ADK agent pipeline   │  - Updates profile in Redis  │
│  - Returns scores + topics   │  - Weave traces all calls    │
├─────────────────────────────────────────────────────────────┤
│  POST /preview_url (Browserbase)                            │
│  - User hovers link → fetch preview via Stagehand           │
│  - Returns title, summary, thumbnail                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│           3-Agent Pipeline (Google Cloud ADK)                │
├─────────────────────────────────────────────────────────────┤
│  1. Extractor Agent    │  2. Scorer Agent   │ 3. Explainer  │
│  - Gemini 1.5 Pro      │  - Redis vectors   │ - Gemini      │
│  - Parse screenshot    │  - Cosine sim      │ - Generate    │
│  - Identify items      │  - Topic affinity  │   "why" text  │
│  - Classify layout     │  - Domain affinity │ - Top factors │
│                        │                    │               │
│  [Weave trace]         │  [Weave trace]     │ [Weave trace] │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Redis (Vector + Cache)                    │
├─────────────────────────────────────────────────────────────┤
│  - User profiles (embeddings, topic affinities)             │
│  - Item embedding cache (URL → embedding)                    │
│  - Score cache (page_url + user_id → scores)                │
│  - Vector similarity search for related content              │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 Technology Stack

| Layer | Technology | Sponsor |
|-------|------------|---------|
| Extension | TypeScript, Chrome MV3 APIs | - |
| Side Panel UI | React + TypeScript (scaffolded with v0) | **Vercel** |
| Backend | Python 3.11+, FastAPI | - |
| Deployment | Vercel Serverless Functions | **Vercel** |
| Agent Framework | Google Cloud ADK | **Google Cloud** |
| LLM (Vision) | Gemini 1.5 Pro (via ADK) | **Google Cloud** |
| Embeddings | Gemini text-embedding-004 | **Google Cloud** |
| Vector DB + Cache | Redis Stack (vector search + JSON) | **Redis** |
| Observability | Weights & Biases Weave | **W&B** |
| URL Preview | Browserbase + Stagehand | **Browserbase** |
| Voice (stretch) | Daily + Pipecat | **Daily** |
| Experimentation | Marimo notebooks | **Marimo** |

### 5.4 API Contracts

#### POST /analyze_page

**Request:**
```json
{
  "user_id": "local_user_123",
  "page_url": "https://news.ycombinator.com",
  "dom_outline": {
    "title": "Hacker News",
    "headings": ["..."],
    "main_text_excerpt": "..."
  },
  "items": [
    {
      "id": "item_1",
      "href": "https://example.com/article",
      "text": "Show HN: My new AI project",
      "snippet": "A tool that does X, Y, Z",
      "bbox": [120, 340, 560, 80],
      "thumbnail_base64": null
    }
  ],
  "screenshot_base64": "data:image/jpeg;base64,..."
}
```

**Response:**
```json
{
  "items": [
    {
      "id": "item_1",
      "score": 87,
      "topics": ["AI", "Show HN", "developer tools"],
      "why": "Matches your interest in AI projects and developer tools. You've clicked similar Show HN posts before."
    }
  ],
  "page_topics": ["tech news", "startups"],
  "profile_summary": {
    "top_topics": [["AI", 2.1], ["startups", 1.8], ["programming", 1.5]]
  },
  "weave_trace_url": "https://wandb.ai/team/project/weave/traces/abc123"
}
```

#### POST /event

**Request:**
```json
{
  "user_id": "local_user_123",
  "event": "click",
  "item_id": "item_1",
  "page_url": "https://news.ycombinator.com",
  "timestamp": 1706745600,
  "item_data": {
    "text": "Show HN: My new AI project",
    "topics": ["AI", "Show HN"],
    "embedding": [0.1, 0.2, ...]
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "profile_updated": true,
  "new_top_topics": [["AI", 2.3], ["Show HN", 1.9]]
}
```

#### POST /preview_url (Browserbase + Stagehand)

**Purpose:** When user hovers a link, fetch rich preview without leaving page

**Request:**
```json
{
  "url": "https://example.com/article",
  "user_id": "local_user_123"
}
```

**Response:**
```json
{
  "title": "How AI is Changing Everything",
  "summary": "A deep dive into the latest AI developments...",
  "thumbnail_url": "https://example.com/og-image.jpg",
  "author": "Jane Doe",
  "published_date": "2025-01-30",
  "estimated_read_time": "5 min",
  "predicted_score": 82,
  "topics": ["AI", "technology"]
}
```

**Implementation:**
```python
from browserbase import Browserbase
from stagehand import Stagehand

@weave.op()  # Trace with Weave
async def preview_url(url: str) -> dict:
    browser = Browserbase()
    page = await browser.new_page()

    stagehand = Stagehand(page)
    await stagehand.goto(url)

    # Extract structured data
    result = await stagehand.extract({
        "title": "string",
        "summary": "first 2 paragraphs",
        "author": "string or null",
        "published_date": "date string or null",
        "main_image": "url or null"
    })

    await browser.close()
    return result
```

---

## 6. Google Authentication

### 6.1 Overview

Users authenticate via a separate web app using Google OAuth 2.0. The extension syncs with the authenticated session, enabling:
- Cross-device profile persistence
- Secure storage of preferences in cloud (Redis)
- Voice onboarding tied to user identity

### 6.2 Authentication Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Extension      │     │  Web App        │     │  Backend        │
│  (Chrome)       │     │  (Vercel)       │     │  (FastAPI)      │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         │  1. Click "Login"     │                       │
         │──────────────────────>│                       │
         │                       │                       │
         │       2. Open login page (new tab)            │
         │<──────────────────────│                       │
         │                       │                       │
         │                       │  3. Google OAuth      │
         │                       │──────────────────────>│
         │                       │                       │
         │                       │  4. Auth code         │
         │                       │<──────────────────────│
         │                       │                       │
         │                       │  5. Exchange for token│
         │                       │──────────────────────>│
         │                       │                       │
         │                       │  6. JWT + user info   │
         │                       │<──────────────────────│
         │                       │                       │
         │  7. postMessage JWT to extension              │
         │<──────────────────────│                       │
         │                       │                       │
         │  8. Store JWT, sync profile                   │
         │─────────────────────────────────────────────>│
         │                       │                       │
```

### 6.3 Web App Login Page (Vercel)

**URL:** `https://interestlens.vercel.app/login`

**UI Components:**
```
┌─────────────────────────────────────┐
│                                     │
│         🔍 InterestLens             │
│                                     │
│     "Your web, ranked for you"      │
│                                     │
│   ┌─────────────────────────────┐   │
│   │  🔵 Continue with Google    │   │
│   └─────────────────────────────┘   │
│                                     │
│   By signing in, you agree to our   │
│   Terms of Service and Privacy      │
│                                     │
└─────────────────────────────────────┘
```

**After Login:**
```
┌─────────────────────────────────────┐
│                                     │
│     ✅ Logged in as john@gmail.com  │
│                                     │
│   ┌─────────────────────────────┐   │
│   │  🎤 Set Up Voice Profile    │   │
│   │     (Recommended)           │   │
│   └─────────────────────────────┘   │
│                                     │
│   ┌─────────────────────────────┐   │
│   │  ⏭️ Skip for Now            │   │
│   └─────────────────────────────┘   │
│                                     │
│   You can set up voice anytime      │
│   from the extension settings.      │
│                                     │
└─────────────────────────────────────┘
```

### 6.4 Backend Auth Endpoints

#### GET /auth/google

**Purpose:** Initiate Google OAuth flow

**Response:** Redirect to Google OAuth consent screen

#### GET /auth/callback

**Purpose:** Handle OAuth callback from Google

**Query Params:**
- `code`: Authorization code from Google
- `state`: CSRF token

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": "google_123456789",
    "email": "john@gmail.com",
    "name": "John Doe",
    "picture": "https://lh3.googleusercontent.com/..."
  },
  "profile_exists": false
}
```

#### GET /auth/me

**Purpose:** Get current user info (requires JWT)

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "user": {
    "id": "google_123456789",
    "email": "john@gmail.com",
    "name": "John Doe"
  },
  "profile": {
    "voice_onboarding_complete": true,
    "top_topics": [["AI", 2.5], ["startups", 1.8]],
    "interaction_count": 47
  }
}
```

### 6.5 Extension Auth Integration

```typescript
// extension/src/background/auth.ts

const AUTH_URL = "https://interestlens.vercel.app/login";

export async function initiateLogin(): Promise<void> {
  // Open login page in new tab
  const tab = await chrome.tabs.create({ url: AUTH_URL });

  // Listen for message from web app
  chrome.runtime.onMessageExternal.addListener(
    async (message, sender, sendResponse) => {
      if (message.type === "AUTH_SUCCESS") {
        const { token, user } = message.payload;

        // Store token securely
        await chrome.storage.local.set({
          authToken: token,
          user: user
        });

        // Sync profile from backend
        await syncProfile(token);

        // Close login tab
        chrome.tabs.remove(tab.id!);

        sendResponse({ success: true });
      }
    }
  );
}

export async function getAuthToken(): Promise<string | null> {
  const { authToken } = await chrome.storage.local.get("authToken");
  return authToken || null;
}

export async function logout(): Promise<void> {
  await chrome.storage.local.remove(["authToken", "user", "profile"]);
}
```

### 6.6 Redis User Storage

```python
# User profile stored in Redis with Google ID as key
async def store_user_profile(user_id: str, profile: UserProfile):
    key = f"user:{user_id}"
    await redis.json().set(key, "$", profile.model_dump())

async def get_user_profile(user_id: str) -> UserProfile | None:
    key = f"user:{user_id}"
    data = await redis.json().get(key)
    return UserProfile(**data) if data else None
```

### 6.7 Limited Mode (Unauthenticated Users)

Users can use the extension without logging in, but with reduced functionality:

| Feature | Authenticated | Limited Mode |
|---------|---------------|--------------|
| Page item detection | ✅ | ✅ |
| Basic highlighting (by prominence) | ✅ | ✅ |
| Topic classification | ✅ | ✅ |
| Personalized ranking | ✅ | ❌ (uses default weights) |
| Click learning | ✅ | ❌ (session only, not persisted) |
| Voice onboarding | ✅ | ❌ |
| Cross-device sync | ✅ | ❌ |
| "Why" explanations | ✅ (personalized) | ✅ (generic) |
| URL preview | ✅ | ✅ |

**Limited Mode UX:**

```
┌────────────────────────────┐
│  🔍 InterestLens           │
│  ─────────────────────────│
│  ⚠️ Limited Mode           │
│  Login to personalize      │
│                            │
│  ┌────────────────────┐    │
│  │ 🔵 Login with      │    │
│  │    Google          │    │
│  └────────────────────┘    │
│                            │
│  ─────────────────────────│
│  Top Items (by prominence) │
│                            │
│  1. [--] Article Title     │
│     tech, news             │
│     (Login to see your     │
│      personalized score)   │
│                            │
└────────────────────────────┘
```

**Implementation:**

```typescript
// extension/src/background/auth.ts

export function isAuthenticated(): boolean {
  return !!getAuthToken();
}

export function getAnalysisMode(): "full" | "limited" {
  return isAuthenticated() ? "full" : "limited";
}

// In content script
const mode = await getAnalysisMode();
if (mode === "limited") {
  // Use prominence-based ranking only
  // Don't send user_id to backend
  // Show login prompt in side panel
}
```

---

## 7. Voice Onboarding (Daily + Pipecat)

### 7.1 Overview

A conversational voice agent that learns user interests through natural dialogue. The agent:
- Asks open-ended questions about interests
- Follows up to clarify preferences
- Extracts topics with sentiment (like/dislike/intensity)
- Stores structured preferences in user profile

### 7.2 Onboarding Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Voice Onboarding Flow                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  User clicks "Set Up Voice Profile"                         │
│                         │                                   │
│                         ▼                                   │
│  ┌─────────────────────────────────────────┐               │
│  │  Agent: "Hi! I'm here to learn what     │               │
│  │  content matters to you. Tell me about  │               │
│  │  your interests - what topics do you    │               │
│  │  like reading about?"                   │               │
│  └─────────────────────────────────────────┘               │
│                         │                                   │
│                         ▼                                   │
│  ┌─────────────────────────────────────────┐               │
│  │  User: "I'm really into AI and machine  │               │
│  │  learning, especially agents and LLMs.  │               │
│  │  I also follow startup news."           │               │
│  └─────────────────────────────────────────┘               │
│                         │                                   │
│                         ▼                                   │
│  ┌─────────────────────────────────────────┐               │
│  │  Agent: "Great! AI and startups. Are    │               │
│  │  there specific areas of AI you prefer? │               │
│  │  Like research papers, product launches,│               │
│  │  or practical tutorials?"               │               │
│  └─────────────────────────────────────────┘               │
│                         │                                   │
│                         ▼                                   │
│  ┌─────────────────────────────────────────┐               │
│  │  User: "Mostly product launches and     │               │
│  │  practical stuff. I don't care much     │               │
│  │  about academic papers. Oh, and I hate  │               │
│  │  clickbait crypto content."             │               │
│  └─────────────────────────────────────────┘               │
│                         │                                   │
│                         ▼                                   │
│  ┌─────────────────────────────────────────┐               │
│  │  Agent: "Got it - practical AI content, │               │
│  │  no academic papers, avoid crypto       │               │
│  │  clickbait. Anything else you'd like    │               │
│  │  to tell me, or should we wrap up?"     │               │
│  └─────────────────────────────────────────┘               │
│                         │                                   │
│                         ▼                                   │
│  ┌─────────────────────────────────────────┐               │
│  │  User: "That's good for now!"           │               │
│  └─────────────────────────────────────────┘               │
│                         │                                   │
│                         ▼                                   │
│  ┌─────────────────────────────────────────┐               │
│  │  Agent: "Perfect! I've saved your       │               │
│  │  preferences. The extension will now    │               │
│  │  prioritize AI product news and startup │               │
│  │  content while filtering out crypto     │               │
│  │  clickbait. You can update these        │               │
│  │  anytime. Happy browsing!"              │               │
│  └─────────────────────────────────────────┘               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 Extracted Preference Schema

```python
from pydantic import BaseModel
from typing import Literal

class TopicPreference(BaseModel):
    topic: str                    # e.g., "AI", "startups", "crypto"
    sentiment: Literal["like", "dislike", "neutral"]
    intensity: float              # 0.0 to 1.0 (how strongly they feel)
    subtopics: List[str]          # e.g., ["product launches", "tutorials"]
    avoid_subtopics: List[str]    # e.g., ["academic papers"]

class ContentPreference(BaseModel):
    preferred_formats: List[str]  # e.g., ["articles", "videos"]
    avoid_formats: List[str]      # e.g., ["podcasts"]
    preferred_length: str         # "short", "medium", "long", "any"

class VoiceOnboardingResult(BaseModel):
    topics: List[TopicPreference]
    content: ContentPreference
    raw_transcript: str           # Full conversation for debugging
    confidence: float             # How confident we are in extraction
```

**Example Extracted Preferences:**
```json
{
  "topics": [
    {
      "topic": "AI/ML",
      "sentiment": "like",
      "intensity": 0.9,
      "subtopics": ["product launches", "practical tutorials", "LLMs", "agents"],
      "avoid_subtopics": ["academic papers", "research"]
    },
    {
      "topic": "startups",
      "sentiment": "like",
      "intensity": 0.7,
      "subtopics": [],
      "avoid_subtopics": []
    },
    {
      "topic": "crypto",
      "sentiment": "dislike",
      "intensity": 0.8,
      "subtopics": [],
      "avoid_subtopics": ["clickbait"]
    }
  ],
  "content": {
    "preferred_formats": ["articles"],
    "avoid_formats": [],
    "preferred_length": "any"
  },
  "confidence": 0.85
}
```

### 7.4 Voice Agent Implementation (Pipecat + Daily)

```python
from pipecat.frames import TextFrame, AudioFrame
from pipecat.processors import FrameProcessor
from pipecat.pipeline import Pipeline
from pipecat.services.daily import DailyTransport
from pipecat.services.google import GoogleSTTService, GoogleTTSService
from google.generativeai import GenerativeModel
import weave

class OnboardingAgent(FrameProcessor):
    """Voice agent for learning user preferences"""

    def __init__(self, user_id: str, redis_client):
        self.user_id = user_id
        self.redis = redis_client
        self.conversation_history = []
        self.model = GenerativeModel("gemini-1.5-flash")

        self.system_prompt = """You are a friendly onboarding assistant for InterestLens,
        a browser extension that personalizes web content.

        Your job is to learn the user's interests through natural conversation.
        Ask about:
        - Topics they're interested in
        - Topics they want to avoid
        - How strongly they feel about each
        - Any specific subtopics or nuances

        Be conversational, not robotic. Ask follow-up questions.
        When the user seems done, summarize what you learned and confirm.

        Keep responses concise (1-3 sentences) since this is voice."""

    @weave.op()
    async def process_frame(self, frame: TextFrame):
        user_message = frame.text
        self.conversation_history.append({"role": "user", "content": user_message})

        # Check if user wants to end
        if self.is_conversation_complete(user_message):
            preferences = await self.extract_preferences()
            await self.save_preferences(preferences)
            return TextFrame(self.generate_farewell(preferences))

        # Generate response
        response = await self.model.generate_content_async(
            contents=[
                {"role": "user", "parts": [{"text": self.system_prompt}]},
                *self.format_history()
            ]
        )

        assistant_message = response.text
        self.conversation_history.append({"role": "assistant", "content": assistant_message})

        return TextFrame(assistant_message)

    @weave.op()
    async def extract_preferences(self) -> VoiceOnboardingResult:
        """Extract structured preferences from conversation"""
        extraction_prompt = f"""
        Based on this conversation, extract the user's content preferences.

        Conversation:
        {self.format_transcript()}

        Return JSON matching this schema:
        {{
          "topics": [
            {{
              "topic": "string",
              "sentiment": "like" | "dislike" | "neutral",
              "intensity": 0.0-1.0,
              "subtopics": ["string"],
              "avoid_subtopics": ["string"]
            }}
          ],
          "content": {{
            "preferred_formats": ["string"],
            "avoid_formats": ["string"],
            "preferred_length": "short" | "medium" | "long" | "any"
          }},
          "confidence": 0.0-1.0
        }}
        """

        response = await self.model.generate_content_async(
            extraction_prompt,
            generation_config={"response_mime_type": "application/json"}
        )

        result = VoiceOnboardingResult.model_validate_json(response.text)
        result.raw_transcript = self.format_transcript()
        return result

    async def save_preferences(self, preferences: VoiceOnboardingResult):
        """Save extracted preferences to user profile in Redis"""
        profile = await get_user_profile(self.user_id) or UserProfile()

        # Convert voice preferences to profile format
        for topic_pref in preferences.topics:
            weight = topic_pref.intensity
            if topic_pref.sentiment == "dislike":
                weight = -weight

            profile.topic_affinity[topic_pref.topic] = weight

            # Add subtopic preferences
            for subtopic in topic_pref.subtopics:
                profile.topic_affinity[subtopic] = weight * 0.8
            for avoid in topic_pref.avoid_subtopics:
                profile.topic_affinity[avoid] = -0.5

        profile.voice_onboarding_complete = True
        profile.voice_preferences = preferences

        await store_user_profile(self.user_id, profile)


async def create_onboarding_session(user_id: str) -> str:
    """Create a Daily room for voice onboarding"""

    # Create Daily room
    room = await daily_client.create_room(
        properties={
            "exp": int(time.time()) + 3600,  # 1 hour expiry
            "enable_chat": False,
            "start_audio_off": False
        }
    )

    # Create meeting token for user
    token = await daily_client.create_meeting_token(
        properties={
            "room_name": room.name,
            "user_id": user_id,
            "enable_recording": False
        }
    )

    # Start Pipecat bot in the room
    transport = DailyTransport(
        room_url=room.url,
        token=BOT_TOKEN,
        bot_name="InterestLens Assistant"
    )

    pipeline = Pipeline([
        transport.input(),
        GoogleSTTService(),
        OnboardingAgent(user_id, redis_client),
        GoogleTTSService(voice="en-US-Neural2-D"),
        transport.output()
    ])

    # Run pipeline in background
    asyncio.create_task(pipeline.run())

    return {"room_url": room.url, "token": token}
```

### 7.5 Web App Voice Onboarding UI

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│              🎤 Voice Profile Setup                         │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                                                     │   │
│   │            [Animated waveform visual]               │   │
│   │                                                     │   │
│   │         🔴 Recording... (0:45)                      │   │
│   │                                                     │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   Agent: "Great! AI and startups. Are there specific       │
│   areas of AI you prefer?"                                  │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  💬 Your turn to speak...                           │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   Preferences detected:                                     │
│   ✓ AI/ML (strong interest)                                │
│   ✓ Startups (moderate interest)                           │
│                                                             │
│   [End Session]                              [Continue]     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.6 Accessing Voice Onboarding from Extension

Users can access voice onboarding anytime from the side panel settings:

```
┌────────────────────────────┐
│  ⚙️ Settings               │
│  ─────────────────────────│
│                            │
│  👤 John Doe               │
│     john@gmail.com         │
│                            │
│  ─────────────────────────│
│                            │
│  Voice Profile             │
│  ┌────────────────────┐    │
│  │ 🎤 Update Voice    │    │
│  │    Preferences     │    │
│  └────────────────────┘    │
│  Last updated: 2 days ago  │
│                            │
│  ─────────────────────────│
│                            │
│  [Clear All Data]          │
│  [Log Out]                 │
│                            │
└────────────────────────────┘
```

### 7.7 How Voice Preferences Affect Scoring

```python
def calculate_score_with_voice_prefs(
    item: ContentFingerprint,
    profile: UserProfile
) -> int:
    base_score = calculate_base_score(item, profile)

    if not profile.voice_preferences:
        return base_score

    # Apply voice preference boosts/penalties
    voice_modifier = 0.0

    for topic_pref in profile.voice_preferences.topics:
        if topic_pref.topic.lower() in [t.lower() for t in item.topics]:
            if topic_pref.sentiment == "like":
                voice_modifier += topic_pref.intensity * 15  # Boost up to +15
            elif topic_pref.sentiment == "dislike":
                voice_modifier -= topic_pref.intensity * 20  # Penalty up to -20

        # Check subtopics
        for subtopic in topic_pref.subtopics:
            if subtopic.lower() in item.text.lower():
                voice_modifier += topic_pref.intensity * 10

        for avoid in topic_pref.avoid_subtopics:
            if avoid.lower() in item.text.lower():
                voice_modifier -= 15  # Strong penalty for avoided subtopics

    # Clamp final score
    final_score = max(0, min(100, base_score + voice_modifier))
    return int(final_score)
```

### 7.8 Backend Endpoints for Voice Onboarding

#### POST /voice/start-session

**Purpose:** Create a Daily room for voice onboarding

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "room_url": "https://interestlens.daily.co/abc123",
  "token": "eyJhbGciOiJIUzI1...",
  "expires_at": "2026-01-31T15:00:00Z"
}
```

#### GET /voice/preferences

**Purpose:** Get extracted voice preferences

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "voice_onboarding_complete": true,
  "preferences": {
    "topics": [...],
    "content": {...},
    "confidence": 0.85
  },
  "last_updated": "2026-01-29T10:30:00Z"
}
```

#### DELETE /voice/preferences

**Purpose:** Clear voice preferences and start fresh

**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "status": "cleared",
  "message": "Voice preferences cleared. You can set them up again anytime."
}
```

---

## 8. User Experience Design

### 6.1 On-Page Overlay

**Visual Style: Outline + Glow + Badge**

- **Highlight**: 2px colored border with subtle glow effect
  - Gold/yellow for top 1-2 items (score 80+)
  - Blue for items 3-5 (score 60-79)
- **Badge**: Small pill in top-right corner showing score (e.g., "87")
- **Hover**: Tooltip with top 3 topics + 1-sentence explanation

**CSS Classes:**
```css
.interestlens-highlight {
  outline: 2px solid #FFD700;
  box-shadow: 0 0 10px rgba(255, 215, 0, 0.5);
  position: relative;
}

.interestlens-badge {
  position: absolute;
  top: -8px;
  right: -8px;
  background: #FFD700;
  color: #000;
  font-size: 11px;
  font-weight: bold;
  padding: 2px 6px;
  border-radius: 10px;
}
```

### 6.2 Side Panel UI

**Layout:**
```
┌────────────────────────────┐
│  🔍 InterestLens           │
│  ─────────────────────────│
│  Ranked for You (5 items)  │
│                            │
│  1. [87] Article Title     │
│     AI, startups           │
│     "Matches your interest │
│      in AI projects..."    │
│     [👍] [👎]              │
│                            │
│  2. [82] Another Article   │
│     ...                    │
│                            │
│  ─────────────────────────│
│  Your Interests:           │
│  AI ████████ 2.1           │
│  startups ██████ 1.8       │
│  ─────────────────────────│
│  [Clear Memory] [Settings] │
└────────────────────────────┘
```

**Components:**
- Header with logo/name
- Ranked item list (top 5)
- Each item: score badge, title, topic tags, "why" text, thumbs up/down
- Profile summary: top topics with visual bars
- Footer: Clear memory button, settings

### 6.3 Cold Start Behavior

- **No interactions yet**: All items shown equally (no highlighting)
- **After 1-3 clicks**: Begin showing tentative highlights
- **After 5+ clicks**: Full personalization active

---

## 7. Scoring Algorithm

### 7.1 Item Representation (ContentFingerprint)

For each detected item, extract:

```python
@dataclass
class ContentFingerprint:
    id: str
    text: str                    # Title + snippet
    url: str                     # href/src
    domain: str                  # Extracted from URL
    topics: List[str]            # LLM-classified (e.g., ["AI", "startups"])
    text_embedding: List[float]  # 1536-dim from text-embedding-3-small
    image_embedding: List[float] # If thumbnail present
    bbox: Tuple[int, int, int, int]  # Position on page
    prominence: float            # Above-fold, size-based score
```

### 7.2 User Profile (TasteVector)

```python
@dataclass
class UserProfile:
    user_text_vector: List[float]       # EMA of clicked item embeddings
    topic_affinity: Dict[str, float]    # {"AI": 2.1, "sports": -0.3}
    domain_affinity: Dict[str, float]   # {"github.com": 1.5}
    interaction_count: int
```

**EMA Update Formula:**
```python
alpha = 0.85  # Decay factor
user_text_vector = alpha * user_text_vector + (1 - alpha) * clicked_item_embedding
topic_affinity[topic] += 0.3  # On click
topic_affinity[topic] -= 0.1  # On thumbs down
```

### 7.3 Interest Score Calculation

```python
def calculate_score(item: ContentFingerprint, profile: UserProfile) -> int:
    # Component weights
    W_TEXT = 0.35
    W_TOPIC = 0.30
    W_DOMAIN = 0.15
    W_PROMINENCE = 0.10
    W_IMAGE = 0.10

    # Text similarity (cosine)
    sim_text = cosine_similarity(item.text_embedding, profile.user_text_vector)

    # Topic affinity sum
    topic_score = sum(profile.topic_affinity.get(t, 0) for t in item.topics)
    topic_score = sigmoid(topic_score)  # Normalize to 0-1

    # Domain affinity
    domain_score = profile.domain_affinity.get(item.domain, 0.5)

    # Prominence (position/size based)
    prominence_score = item.prominence

    # Image similarity (if available)
    sim_image = 0.5  # Default neutral
    if item.image_embedding and profile.user_image_vector:
        sim_image = cosine_similarity(item.image_embedding, profile.user_image_vector)

    # Weighted sum
    raw_score = (
        W_TEXT * sim_text +
        W_TOPIC * topic_score +
        W_DOMAIN * domain_score +
        W_PROMINENCE * prominence_score +
        W_IMAGE * sim_image
    )

    # Map to 0-100
    return int(sigmoid(raw_score * 5) * 100)
```

---

## 8. Agent Architecture (Google Cloud ADK + Weave)

### 8.0 ADK Setup & Weave Integration

```python
import weave
from google.adk import Agent, Pipeline
from google.adk.models import Gemini

# Initialize Weave for observability
weave.init("interestlens")

# Create the 3-agent pipeline with ADK
pipeline = Pipeline(
    agents=[
        ExtractorAgent(),
        ScorerAgent(),
        ExplainerAgent()
    ],
    trace_provider=weave  # All agent calls traced
)
```

### 8.1 Agent 1: Extractor Agent (Gemini Vision)

**Purpose:** Understand page layout and identify content items

**ADK Implementation:**
```python
from google.adk import Agent
from google.adk.tools import Tool

class ExtractorAgent(Agent):
    name = "extractor"
    model = "gemini-1.5-pro"  # Vision-capable

    system_prompt = """You are a Page Understanding Agent.
    Analyze webpage screenshots and DOM outlines to identify content items."""

    @weave.op()  # Traced by Weave
    async def run(self, screenshot: bytes, dom_outline: dict) -> dict:
        response = await self.generate(
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "data": screenshot},
                    {"type": "text", "text": f"DOM: {json.dumps(dom_outline)}"}
                ]
            }],
            response_format=ExtractorOutput  # Structured output
        )
        return response
```

**Output Schema:**
```python
class ExtractorOutput(BaseModel):
    page_type: Literal["news_aggregator", "video_grid", "shopping", "forum", "other"]
    content_regions: List[ContentRegion]
    items: List[ItemClassification]

class ItemClassification(BaseModel):
    id: str
    is_content: bool
    is_nav_or_ad: bool
    confidence: float
```

### 8.2 Agent 2: Scorer Agent (Redis Vector Search)

**Purpose:** Calculate interest scores using embeddings and user profile

**ADK Implementation:**
```python
from redis import Redis
from redis.commands.search.query import Query

class ScorerAgent(Agent):
    name = "scorer"
    model = "gemini-1.5-flash"  # Fast model for topic classification

    def __init__(self):
        self.redis = Redis.from_url(os.environ["REDIS_URL"])
        self.embedding_model = "text-embedding-004"

    @weave.op()
    async def run(self, items: List[dict], user_id: str) -> dict:
        # Get user profile from Redis
        profile = await self.get_user_profile(user_id)

        scores = []
        for item in items:
            # Get/cache item embedding in Redis
            embedding = await self.get_embedding(item["text"], item["id"])

            # Vector similarity search against user profile
            similarity = await self.redis.execute_command(
                "FT.SEARCH", "user_embeddings",
                f"@user_id:{user_id}",
                "RETURN", "1", "embedding",
                "PARAMS", "2", "vec", embedding
            )

            # Classify topics
            topics = await self.classify_topics(item["text"])

            # Calculate weighted score
            score = self.calculate_score(similarity, topics, profile)
            scores.append({"id": item["id"], "score": score, "topics": topics})

        return {"item_scores": scores}

    @weave.op()
    async def get_embedding(self, text: str, item_id: str) -> List[float]:
        # Check Redis cache first
        cached = await self.redis.get(f"embedding:{item_id}")
        if cached:
            return json.loads(cached)

        # Generate via Gemini
        embedding = await genai.embed_content(
            model=self.embedding_model,
            content=text
        )

        # Cache in Redis
        await self.redis.setex(
            f"embedding:{item_id}",
            3600,  # 1 hour TTL
            json.dumps(embedding)
        )
        return embedding
```

**Redis Vector Index Schema:**
```python
# Create vector index for semantic search
redis.execute_command(
    "FT.CREATE", "item_embeddings",
    "ON", "HASH",
    "PREFIX", "1", "item:",
    "SCHEMA",
        "embedding", "VECTOR", "HNSW", "6",
            "TYPE", "FLOAT32",
            "DIM", "768",  # Gemini embedding dimension
            "DISTANCE_METRIC", "COSINE",
        "topics", "TAG",
        "domain", "TAG",
        "text", "TEXT"
)
```

### 8.3 Agent 3: Explainer Agent (Gemini)

**Purpose:** Generate human-readable explanations

**ADK Implementation:**
```python
class ExplainerAgent(Agent):
    name = "explainer"
    model = "gemini-1.5-flash"

    system_prompt = """Generate brief, conversational explanations
    for why content items match user interests. Be specific about
    which interests matched."""

    @weave.op()
    async def run(self, item: dict, profile: dict) -> dict:
        prompt = f"""
        Item: {item['text']}
        Score: {item['score']}/100
        Topics: {item['topics']}
        User's top interests: {profile['top_topics'][:5]}
        Score breakdown: text_sim={item.get('text_sim', 0):.2f},
                        topic_match={item.get('topic_match', 0):.2f}

        Generate a 1-2 sentence explanation for why this ranked highly.
        """

        response = await self.generate(prompt)
        return {
            "id": item["id"],
            "why": response.text,
            "top_factors": self.extract_factors(item)
        }
```

### 8.4 Weave Observability Dashboard

**What Weave Traces:**
- Each agent invocation with inputs/outputs
- LLM token usage and latency
- Embedding generation time
- Redis cache hits/misses
- End-to-end pipeline duration

**Demo Value:**
```
"Click this Weave trace link to see exactly how the AI scored this page:
- Extractor took 1.2s to analyze the screenshot
- Scorer made 15 embedding calls (12 cache hits)
- Explainer generated 5 explanations in 0.8s
- Total pipeline: 2.4s"
```

**Weave Integration Code:**
```python
import weave

# Initialize at app startup
weave.init("interestlens")

# Wrap the main analysis function
@weave.op()
async def analyze_page(request: AnalyzeRequest) -> AnalyzeResponse:
    # Run pipeline - all nested @weave.op() calls are traced
    extractor_result = await extractor_agent.run(
        request.screenshot_base64,
        request.dom_outline
    )

    scorer_result = await scorer_agent.run(
        extractor_result["items"],
        request.user_id
    )

    explainer_result = await explainer_agent.run(
        scorer_result["item_scores"],
        await get_user_profile(request.user_id)
    )

    # Return includes trace URL for debugging
    return AnalyzeResponse(
        items=explainer_result,
        weave_trace_url=weave.get_current_trace_url()
    )
```

---

## 9. Topic Categories (25 Categories)

```python
TOPIC_CATEGORIES = [
    # Tech
    "AI/ML", "programming", "cloud/infrastructure", "cybersecurity",
    "startups", "developer tools", "open source", "mobile apps",

    # Business
    "finance", "business strategy", "entrepreneurship", "marketing",

    # Science
    "science", "research", "space", "climate",

    # Entertainment
    "gaming", "movies/TV", "music", "sports",

    # Lifestyle
    "health", "productivity", "design", "travel", "food"
]
```

---

## 10. Demo Sites (Golden Path)

### 10.1 Hacker News (news.ycombinator.com)

**Item Detection:**
- Each `.titleline` is an item
- Extract title text and URL
- No thumbnails

**Expected Behavior:**
- Highlight top 5 stories based on user's tech interests
- Topics: tech-focused (AI, programming, startups)

### 10.2 YouTube (youtube.com)

**Item Detection:**
- Video cards with thumbnails
- Extract title, channel, thumbnail image
- Use thumbnail for image embedding

**Expected Behavior:**
- Highlight videos matching user's interests
- Image similarity plays larger role

### 10.3 Amazon Category Page (amazon.com/s?...)

**Item Detection:**
- Product cards with images
- Extract product title, price, image
- Use product image for embedding

**Expected Behavior:**
- Highlight products in user's interest categories
- Domain affinity important

---

## 11. Data Flow

### 11.1 Page Load Flow

```
1. User navigates to page
2. Content script activates
3. Extract candidate items (links, cards, tiles)
4. Capture screenshot
5. Send to backend: POST /analyze_page
6. Backend runs 3-agent pipeline
7. Return scored items
8. Content script renders overlays
9. Side panel updates with ranked list
```

### 11.2 Interaction Flow

```
1. User clicks highlighted item (or any item)
2. Content script logs click event
3. Send to backend: POST /event
4. Backend updates user profile (EMA)
5. Backend returns updated profile summary
6. Extension stores profile locally
7. On next page, new profile used for scoring
```

### 11.3 Instant Feedback Demo

```
1. User clicks item with topic "AI"
2. Profile AI affinity increases: 1.5 → 1.8
3. User returns to page (or refreshes)
4. Items with "AI" topic now score higher
5. Ranking visibly shifts
```

---

## 12. Privacy & Security

### 12.1 Data Handling

| Data Type | Storage | Sent to Backend |
|-----------|---------|-----------------|
| User profile | chrome.storage.local | No (computed locally) |
| Item embeddings | Cached in backend | Yes (temporary) |
| Screenshots | Not stored | Yes (for analysis only) |
| Browsing history | Never stored | No |
| Click events | Local only | Minimal (item ID + topics) |

### 12.2 Privacy Indicators

- Side panel shows: "🔒 Local-only mode"
- Settings page explains what data is sent
- "Clear Memory" button wipes all local data

---

## 13. Task Breakdown for Team

### Person 1: Extension Developer (Frontend + v0)

**Hour 1-2: Extension Setup**
- [ ] Set up Chrome MV3 extension boilerplate
- [ ] Create manifest.json with required permissions
- [ ] Implement content script injection

**Hour 3-4: DOM & Overlay**
- [ ] Build DOM candidate extraction logic
- [ ] Implement screenshot capture (chrome.tabs.captureVisibleTab)
- [ ] Create overlay rendering system (highlight + badge)

**Hour 5-6: Side Panel UI (use v0)**
- [ ] Generate side panel components with v0.dev
- [ ] Prompt: "React side panel for browser extension showing ranked list of items with scores, topic tags, and thumbs up/down buttons"
- [ ] Implement ranked list component
- [ ] Add thumbs up/down feedback buttons
- [ ] Add link hover → preview tooltip (calls /preview_url)

**Hour 7-8: Integration**
- [ ] Integrate with backend API
- [ ] Handle loading states and errors
- [ ] Polish overlay styling

**Hour 9-10: Testing & Demo**
- [ ] Test on 3 demo sites (HN, YouTube, Amazon)
- [ ] Fix edge cases and bugs
- [ ] Prepare demo flow

**Tools Used:** Chrome MV3 APIs, React, TypeScript, **v0 (Vercel)**

---

### Person 2: Backend Developer (API + Infrastructure)

**Hour 1-2: Project Setup**
- [ ] Set up FastAPI project structure
- [ ] Configure **Vercel** deployment (vercel.json)
- [ ] Initialize **Weave** for observability
- [ ] Set up **Redis** connection (Redis Cloud or local)

**Hour 3-4: Core Endpoints**
- [ ] Implement `/analyze_page` endpoint stub
- [ ] Implement `/event` endpoint stub
- [ ] Implement `/preview_url` endpoint with **Browserbase + Stagehand**

**Hour 5-6: Redis Integration**
- [ ] Create Redis vector index schema
- [ ] Implement embedding caching in Redis
- [ ] Implement user profile storage in Redis
- [ ] Add vector similarity search

**Hour 7-8: Browserbase Preview**
- [ ] Set up Browserbase connection
- [ ] Implement Stagehand extraction for URL previews
- [ ] Cache preview results in Redis

**Hour 9-10: Deploy & Monitor**
- [ ] Deploy to **Vercel**
- [ ] Verify **Weave** traces are visible
- [ ] Performance optimization
- [ ] Prepare demo data

**Tools Used:** FastAPI, **Vercel**, **Redis**, **Browserbase/Stagehand**, **Weave**

---

### Person 3: ML/Agent Developer (ADK + Scoring)

**Hour 1-2: ADK Setup**
- [ ] Set up **Google Cloud ADK** project
- [ ] Configure Gemini 1.5 Pro API access
- [ ] Design 3-agent pipeline architecture
- [ ] Implement ContentFingerprint dataclass

**Hour 3-4: Extractor Agent**
- [ ] Implement ExtractorAgent with ADK
- [ ] Configure Gemini Vision for screenshot analysis
- [ ] Define structured output schema
- [ ] Wrap with **@weave.op()** for tracing

**Hour 5-6: Scorer Agent**
- [ ] Implement ScorerAgent with ADK
- [ ] Integrate Gemini embeddings (text-embedding-004)
- [ ] Implement cosine similarity with Redis vectors
- [ ] Implement topic classification
- [ ] Implement EMA profile update logic

**Hour 7-8: Explainer Agent**
- [ ] Implement ExplainerAgent with ADK
- [ ] Generate "why" explanations
- [ ] Wire up complete pipeline
- [ ] Test with **Marimo** notebook for weight tuning

**Hour 9-10: End-to-End Testing**
- [ ] Test full pipeline end-to-end
- [ ] Tune scoring weights in Marimo
- [ ] Verify Weave traces show all 3 agents
- [ ] Document scoring logic for judges

**Tools Used:** **Google Cloud ADK**, Gemini 1.5 Pro, **Weave**, **Redis**, **Marimo**

---

### Person 4 (or shared): Auth + Voice Onboarding

**Hour 1-2: Google Auth Setup**
- [ ] Create Google Cloud OAuth credentials
- [ ] Set up Vercel web app for login page
- [ ] Implement `/auth/google` and `/auth/callback` endpoints
- [ ] Generate and validate JWTs

**Hour 3-4: Auth Integration**
- [ ] Build login page UI (v0)
- [ ] Implement extension ↔ web app communication
- [ ] Store user profiles in Redis with Google ID
- [ ] Test full auth flow

**Hour 5-6: Voice Onboarding Setup**
- [ ] Set up **Daily** account and API access
- [ ] Configure **Pipecat** pipeline
- [ ] Implement OnboardingAgent with conversation logic
- [ ] Add preference extraction with Gemini

**Hour 7-8: Voice Integration**
- [ ] Build voice onboarding UI page
- [ ] Implement `/voice/start-session` endpoint
- [ ] Save extracted preferences to Redis
- [ ] Integrate preferences into scoring

**Hour 9-10: Testing + Polish**
- [ ] Test full flow: Login → Voice → Extension
- [ ] Handle edge cases (user cancels, poor audio)
- [ ] Add "Update Voice Preferences" to settings
- [ ] Prepare auth + voice demo script

**Tools Used:** Google OAuth, **Vercel**, **Daily**, **Pipecat**, **Redis**, Gemini

---

### Parallel Integration Points

| Hour | Person 1 (Extension) | Person 2 (Backend) | Person 3 (ML/Agents) | Person 4 (Auth/Voice) |
|------|---------------------|-------------------|---------------------|----------------------|
| 1-2 | Extension boilerplate | FastAPI + Weave | ADK + Gemini | Google OAuth setup |
| 3-4 | DOM extraction | Endpoints + Redis | Extractor Agent | Auth flow + JWT |
| 5-6 | Side panel UI (v0) | Browserbase preview | Scorer Agent | Daily + Pipecat |
| 7-8 | API integration | Deploy to Vercel | Explainer pipeline | Voice integration |
| 9-10 | Testing + demo | Monitoring + demo | Tuning + demo | Auth/Voice demo |

**Integration Checkpoints:**
- **Hour 2:** Auth endpoints work → Web app can test login
- **Hour 4:** Backend returns mock scores → Extension can render
- **Hour 6:** Voice session creates → Can test conversation flow
- **Hour 8:** Full pipeline works with auth → Demo ready for testing
- **Hour 10:** Voice preferences affect scoring → Full personalization loop

---

## 14. Stretch Goal: Voice Command (Daily + Pipecat)

**If time permits (extra 1-2 hours):**

**Feature:** User says "Show me AI articles" and the system filters/re-ranks

**Tech Stack:**
- **Daily** - WebRTC infrastructure for real-time audio
- **Pipecat** - Open-source framework for voice AI pipelines

**Implementation:**

```python
from pipecat.frames import TextFrame, AudioFrame
from pipecat.processors import FrameProcessor
from pipecat.services.daily import DailyTransport
from pipecat.services.google import GoogleSTTService, GoogleTTSService

class InterestLensVoiceBot(FrameProcessor):
    """Voice interface for InterestLens filtering"""

    def __init__(self, redis_client, user_id):
        self.redis = redis_client
        self.user_id = user_id

    async def process_frame(self, frame: TextFrame):
        # Parse voice command
        command = frame.text.lower()

        if "show me" in command:
            # Extract topic from "show me {topic} articles"
            topic = self.extract_topic(command)
            await self.filter_by_topic(topic)

        elif "what's trending" in command:
            await self.show_trending()

        elif "explain" in command:
            await self.explain_top_item()

async def create_voice_pipeline():
    transport = DailyTransport(
        room_url=os.environ["DAILY_ROOM_URL"],
        token=os.environ["DAILY_TOKEN"]
    )

    pipeline = Pipeline([
        transport.input(),           # Audio from user
        GoogleSTTService(),          # Speech to text
        InterestLensVoiceBot(),      # Our command handler
        GoogleTTSService(),          # Text to speech
        transport.output()           # Audio back to user
    ])

    return pipeline
```

**Extension Integration:**
```typescript
// side-panel.tsx
const VoiceButton: React.FC = () => {
  const [isListening, setIsListening] = useState(false);
  const dailyRef = useRef<DailyCall | null>(null);

  const startVoice = async () => {
    dailyRef.current = Daily.createCallObject();
    await dailyRef.current.join({ url: DAILY_ROOM_URL });
    setIsListening(true);
  };

  return (
    <button onClick={startVoice} className="voice-btn">
      {isListening ? "🎤 Listening..." : "🎙️ Voice Command"}
    </button>
  );
};
```

**Supported Voice Commands:**
| Command | Action |
|---------|--------|
| "Show me AI articles" | Filter to AI topic only |
| "Show me everything" | Remove filters |
| "Why is this ranked high?" | Speak explanation for #1 item |
| "What are my top interests?" | Read profile summary |
| "Clear my preferences" | Reset profile |

**Demo Script:**
1. Click microphone icon in side panel
2. Say "Show me AI articles"
3. Overlay updates to highlight only AI-related items
4. Say "Why is this ranked high?"
5. Bot explains: "This matches your interest in machine learning and you've clicked similar Show HN posts"

---

## 17. Demo Script (4-5 minutes)

### Setup (15 sec)
- Fresh browser with extension installed but not logged in
- Have Weave dashboard open in another tab

### Demo Flow (4 min)

1. **Google Login** (30 sec)
   - Click extension icon → "Login with Google"
   - "We use Google OAuth for secure authentication"
   - Complete login flow
   - "Now my profile syncs across devices via Redis"

2. **Voice Onboarding** (60 sec)
   - After login, click "Set Up Voice Profile"
   - "This is the magic - I'll tell the AI what I care about"
   - Start voice session with Daily + Pipecat
   - Say: "I'm really into AI and machine learning, especially LLM agents and browser automation. I also like startup news. I don't care about crypto or sports."
   - Agent asks follow-up: "Are there specific areas of AI you prefer?"
   - Reply: "Mostly product launches and practical tutorials, not academic papers."
   - Agent confirms and ends session
   - "The AI extracted my preferences - look, it detected AI with high interest, crypto with negative sentiment"

3. **Open Hacker News with Personalized Ranking** (30 sec)
   - Navigate to Hacker News
   - "Now watch - the extension already knows my preferences from voice"
   - Highlights appear - AI and startup posts at top
   - "Notice the crypto post is NOT highlighted even though it's popular - because I said I don't care about crypto"

4. **Show Explanation + Preview** (30 sec)
   - Hover over top item
   - "The 'why' mentions both my click history AND voice preferences"
   - Hover over a link to show Browserbase preview
   - "Rich preview without leaving the page - Browserbase and Stagehand"

5. **Click to Learn** (20 sec)
   - Click on 2 AI-related items
   - "Voice gave us the cold start, but clicks continue to refine"
   - Refresh page
   - "Rankings update instantly"

6. **Switch to YouTube** (20 sec)
   - Navigate to YouTube
   - "Same preferences, different site type"
   - "Gemini Vision detects video cards and thumbnails"

7. **Show Weave Observability** (30 sec)
   - Switch to Weave dashboard
   - "Full observability with W&B Weave"
   - Show trace of the 3-agent pipeline
   - "Extractor, Scorer, Explainer - all traced with timing"

8. **Voice Command (if time)** (20 sec)
   - Click microphone in side panel
   - Say "Show me only AI articles"
   - Overlay filters to AI-only items

### Wrap-up (30 sec)
- "The full personalization loop:"
  - "Login with Google for cross-device sync"
  - "Voice onboarding for instant preferences"
  - "Click learning for continuous refinement"
- "Built with: Google Auth, Daily + Pipecat for voice, ADK for agents, Gemini for vision, Redis for vectors, Weave for observability, Browserbase for previews, Vercel for deployment"
- "InterestLens: Your web, ranked for you"

### Technical Deep-Dive (if judges ask)

**On Agents (Google Cloud ADK):**
"We use ADK to orchestrate 3 specialized agents. Each agent has a single responsibility - Extract, Score, Explain. They communicate via structured outputs and the pipeline is fully traced."

**On Caching (Redis):**
"We cache embeddings by URL hash and user profiles with vector indices. On a repeat visit, most embeddings are cache hits - that's why it feels instant."

**On Observability (Weave):**
"Every LLM call, embedding generation, and agent handoff is traced. We can debug exactly why an item scored high or why the pipeline was slow."

**On URL Preview (Browserbase):**
"Stagehand writes the extraction code, Browserbase runs headless Chrome. We get rich previews without the extension needing page access."

---

## 16. Marimo Experimentation Notebook

**Purpose:** Use Marimo for reproducible experiments on scoring weights and prompt tuning

**Notebook Structure:**
```python
# interestlens_experiments.py (Marimo notebook)
import marimo as mo
import weave

# Cell 1: Load sample data
mo.md("## InterestLens Scoring Experiments")
sample_items = load_sample_items("hacker_news_dump.json")
sample_profile = load_sample_profile("test_user.json")

# Cell 2: Interactive weight tuning
W_TEXT = mo.ui.slider(0, 1, value=0.35, label="Text Similarity Weight")
W_TOPIC = mo.ui.slider(0, 1, value=0.30, label="Topic Affinity Weight")
W_DOMAIN = mo.ui.slider(0, 1, value=0.15, label="Domain Weight")
W_PROMINENCE = mo.ui.slider(0, 1, value=0.10, label="Prominence Weight")
W_IMAGE = mo.ui.slider(0, 1, value=0.10, label="Image Similarity Weight")

# Cell 3: Re-score with new weights
@mo.cache
def rescore_items(items, weights):
    return [calculate_score(item, sample_profile, weights) for item in items]

scores = rescore_items(sample_items, {
    "text": W_TEXT.value,
    "topic": W_TOPIC.value,
    "domain": W_DOMAIN.value,
    "prominence": W_PROMINENCE.value,
    "image": W_IMAGE.value
})

# Cell 4: Visualize ranking changes
mo.ui.table(sorted(zip(sample_items, scores), key=lambda x: -x[1]))

# Cell 5: A/B test prompts
prompt_variants = [
    "Classify this content into topics: {text}",
    "What categories does this belong to? Be specific: {text}",
    "List 2-3 topic tags for: {text}"
]
prompt_selector = mo.ui.dropdown(prompt_variants, label="Topic Prompt")

# Cell 6: Run prompt experiment with Weave logging
@weave.op()
def test_prompt(prompt_template, items):
    results = []
    for item in items[:10]:
        topics = classify_topics(prompt_template.format(text=item["text"]))
        results.append({"item": item["text"][:50], "topics": topics})
    return results

mo.ui.table(test_prompt(prompt_selector.value, sample_items))
```

**Why Marimo:**
- Reproducible: notebooks are pure Python, version-controllable
- Interactive: sliders update scores in real-time
- Shareable: export as HTML for judges to explore
- Integrated: Weave traces show experiment history

---

## 17. Success Criteria

### MVP Complete When:

- [ ] Extension loads on any website without errors
- [ ] Extracts candidate items on HN, YouTube, Amazon
- [ ] Sends data to backend and receives scores
- [ ] Renders highlight overlay on top 5 items
- [ ] Side panel shows ranked list with topics and explanations
- [ ] Clicking items updates user profile (stored in Redis)
- [ ] Ranking visibly shifts after 3-5 interactions
- [ ] "Why" explanations are coherent and specific
- [ ] Weave traces visible for all agent calls
- [ ] URL preview works via Browserbase
- [ ] Demo runs smoothly for 3-4 minutes without crashes

### Sponsor Tool Checklist:

| Tool | Integrated | Demo-able |
|------|------------|-----------|
| **W&B Weave** | [ ] All agents traced | [ ] Show trace in demo |
| **Redis** | [ ] Vector index created, user profiles stored | [ ] Show cache hits in logs |
| **Browserbase/Stagehand** | [ ] Preview endpoint works | [ ] Hover preview in demo |
| **Vercel** | [ ] Backend + web app deployed | [ ] Share deployment URL |
| **v0** | [ ] UI components generated | [ ] Credit in demo |
| **Google Cloud ADK** | [ ] 3-agent pipeline | [ ] Explain architecture |
| **Gemini** | [ ] Vision + embeddings | [ ] Show in Weave trace |
| **Marimo** | [ ] Experiment notebook | [ ] Show weight tuning |
| **Daily/Pipecat** | [ ] Voice onboarding works | [ ] Voice onboarding demo |
| **Google OAuth** | [ ] Login flow works | [ ] Demo login |

### Judging Criteria Alignment:

| Criteria | How We Address It |
|----------|-------------------|
| Innovation | AI agents that understand page layout + learn user preferences |
| Technical Depth | 3-agent ADK pipeline, Redis vectors, Weave observability |
| UX/Polish | Clean overlay design, transparent explanations, v0-generated UI |
| Agentic AI | Google Cloud ADK with explicit agent roles |
| Sponsor Integration | All 7 sponsor tools meaningfully integrated |
| Practicality | Works on real websites, instant personalization |

---

## 18. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| DOM extraction fails on complex sites | Medium | High | Fallback to basic link extraction |
| Gemini API latency too high | Medium | Medium | Cache embeddings in Redis, batch requests |
| Redis connection issues | Low | High | Use Redis Cloud with auto-failover, local fallback |
| Browserbase rate limits | Low | Medium | Cache previews aggressively, debounce hover |
| Weave logging overhead | Low | Low | Use async logging, sample if needed |
| ADK learning curve | Medium | Medium | Start with simple agent, iterate |
| Vercel cold starts | Medium | Low | Keep functions warm, optimize bundle |
| Scoring feels random to user | Low | High | Ensure "why" explanations are clear |
| Extension breaks site functionality | Low | High | Use isolated overlay layer, test thoroughly |
| Screenshot capture blocked | Low | Medium | Fall back to DOM-only analysis |

---

## 19. Environment Setup & Dependencies

### Required API Keys / Accounts

```bash
# .env file

# Google Cloud (ADK + Gemini + OAuth)
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_API_KEY=your-gemini-api-key
GOOGLE_CLIENT_ID=your-oauth-client-id
GOOGLE_CLIENT_SECRET=your-oauth-client-secret

# Redis
REDIS_URL=redis://default:password@host:port

# Browserbase
BROWSERBASE_API_KEY=your-browserbase-key
BROWSERBASE_PROJECT_ID=your-project-id

# W&B Weave
WANDB_API_KEY=your-wandb-api-key
WANDB_PROJECT=interestlens

# Vercel
VERCEL_TOKEN=your-vercel-token

# Daily (Voice Onboarding)
DAILY_API_KEY=your-daily-key
DAILY_DOMAIN=your-domain.daily.co

# JWT Secret (for auth tokens)
JWT_SECRET=your-secure-random-string
JWT_ALGORITHM=HS256
```

### Python Dependencies (backend/requirements.txt)

```
fastapi>=0.109.0
uvicorn>=0.27.0
python-dotenv>=1.0.0

# Google Cloud ADK + Gemini
google-adk>=0.1.0
google-generativeai>=0.4.0

# Google OAuth
google-auth>=2.27.0
google-auth-oauthlib>=1.2.0

# JWT Authentication
python-jose[cryptography]>=3.3.0
passlib>=1.7.4

# Redis
redis>=5.0.0
redis-om>=0.2.0

# Browserbase
browserbase>=0.1.0
stagehand>=0.1.0

# Observability
weave>=0.50.0
wandb>=0.16.0

# Voice Onboarding (Daily + Pipecat)
pipecat-ai>=0.1.0
daily-python>=0.1.0

# Utilities
httpx>=0.26.0
pydantic>=2.5.0
numpy>=1.26.0
```

### Node Dependencies (extension/package.json)

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@types/chrome": "^0.0.260",
    "@types/react": "^18.2.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "@crxjs/vite-plugin": "^2.0.0-beta.23"
  }
}
```

### Quick Start Commands

```bash
# Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
weave login  # Authenticate with W&B
python -m uvicorn main:app --reload

# Extension setup
cd extension
npm install
npm run dev  # Build with hot reload
# Load unpacked extension from dist/ folder in Chrome

# Vercel deployment
cd backend
vercel --prod

# Marimo experiments
cd experiments
pip install marimo
marimo edit interestlens_experiments.py
```

---

## 20. Future Enhancements (Post-Hackathon)

- Cross-device profile sync with account system
- Firefox and Safari support
- Local embedding models for privacy
- "Compare two pages" feature
- Export interests as RSS feed
- Team/shared profiles
- A2A (Agent-to-Agent) protocol for distributed agents
- Fine-tuned topic classifier on user data

---

## 23. Appendix: File Structure

```
interestlens/
├── extension/                    # Chrome Extension (MV3)
│   ├── manifest.json
│   ├── src/
│   │   ├── content/             # Content script
│   │   │   ├── extractor.ts     # DOM extraction
│   │   │   └── overlay.ts       # Highlight rendering
│   │   ├── background/          # Service worker
│   │   │   ├── service-worker.ts
│   │   │   └── auth.ts          # Auth token handling
│   │   ├── sidepanel/           # Side panel UI (v0 generated)
│   │   │   ├── App.tsx
│   │   │   ├── RankedList.tsx
│   │   │   ├── ProfileSummary.tsx
│   │   │   ├── Settings.tsx     # Settings + voice update
│   │   │   └── LoginPrompt.tsx  # Login CTA for unauthenticated
│   │   └── shared/
│   │       └── types.ts
│   ├── package.json
│   └── vite.config.ts
│
├── webapp/                       # Vercel Web App (Login + Voice)
│   ├── app/
│   │   ├── page.tsx             # Landing page
│   │   ├── login/
│   │   │   └── page.tsx         # Google OAuth login
│   │   ├── auth/
│   │   │   └── callback/
│   │   │       └── page.tsx     # OAuth callback handler
│   │   └── onboarding/
│   │       └── voice/
│   │           └── page.tsx     # Voice onboarding UI
│   ├── components/
│   │   ├── GoogleLoginButton.tsx
│   │   ├── VoiceSession.tsx     # Daily + waveform UI
│   │   └── PreferencesDisplay.tsx
│   ├── package.json
│   └── vercel.json
│
├── backend/                      # FastAPI Backend
│   ├── main.py                  # FastAPI app + endpoints
│   ├── auth/                    # Authentication
│   │   ├── google.py            # Google OAuth handlers
│   │   ├── jwt.py               # JWT generation/validation
│   │   └── dependencies.py      # Auth middleware
│   ├── voice/                   # Voice Onboarding
│   │   ├── session.py           # Daily room creation
│   │   ├── agent.py             # Pipecat OnboardingAgent
│   │   └── extraction.py        # Preference extraction
│   ├── agents/                  # Google Cloud ADK agents
│   │   ├── extractor.py
│   │   ├── scorer.py
│   │   └── explainer.py
│   ├── services/
│   │   ├── redis_client.py      # Redis vector + cache
│   │   ├── browserbase.py       # URL preview
│   │   └── embeddings.py        # Gemini embeddings
│   ├── models/
│   │   ├── fingerprint.py       # ContentFingerprint
│   │   ├── profile.py           # UserProfile
│   │   ├── auth.py              # User, Token models
│   │   └── voice.py             # VoiceOnboardingResult
│   ├── requirements.txt
│   └── vercel.json
│
├── experiments/                  # Marimo notebooks
│   └── scoring_experiments.py
│
├── PRD-InterestLens.md          # This document
└── README.md
```

---

## 24. Summary

**InterestLens** is a Chrome browser extension that uses AI to personalize any webpage by highlighting the content most relevant to each user.

**Key Features:**
1. **Google Authentication** - Login with Google for cross-device profile sync
2. **Voice Onboarding** - Tell the AI your interests through natural conversation
3. **Smart Highlighting** - Top 5 items highlighted on any page
4. **Transparent Explanations** - See why each item is ranked high
5. **Continuous Learning** - Clicks refine preferences over time

**Key Technical Choices:**
- **Google OAuth** for secure authentication
- **Daily + Pipecat** for conversational voice onboarding
- **Google Cloud ADK** for 3-agent pipeline (Extractor → Scorer → Explainer)
- **Gemini 1.5 Pro** for multimodal vision analysis
- **Redis** for vector embeddings, user profiles, and caching
- **W&B Weave** for full observability
- **Browserbase + Stagehand** for URL previews
- **Vercel** for deployment (backend + web app)
- **v0** for rapid UI generation
- **Marimo** for experimentation

**Demo Narrative:**
"InterestLens learns what you care about through voice and behavior. Login with Google, tell the AI your interests, and watch as it highlights the most relevant content on any page. Under the hood, we have 3 AI agents working together - all traced with Weave so you can see exactly how the AI thinks."

**Build Time:** 8-10 hours with 3-4 people
**Team Split:** Extension / Backend / ML-Agents / Auth+Voice

**Personalization Loop:**
```
Google Login → Voice Onboarding → Instant Preferences → Click Learning → Continuous Refinement
```

---

*PRD Generated: January 31, 2026*
*Last Updated: January 31, 2026*
