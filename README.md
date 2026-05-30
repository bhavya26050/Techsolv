# Creator RAG Intelligence Demo

Full-stack RAG chatbot for comparing two social videos side by side.

## What it does

- Accepts one YouTube URL and one Instagram Reels URL.
- Pulls metadata, engagement numbers, creator info, and transcript text when available.
- Chunks transcripts, embeds them, and stores them in Chroma.
- Uses LangChain for retrieval + answer generation with streaming responses.
- Keeps per-session chat memory so follow-up questions stay grounded.
- Shows a side-by-side video comparison UI with a chat panel.

## Stack

- Frontend: Next.js + React
- Backend: FastAPI
- Orchestration: LangChain
- Embeddings: Hugging Face sentence-transformers
- Vector DB: Chroma
- LLM: Gemini (default) or OpenAI fallback via environment switch
- Transcript: youtube-transcript-api, yt-dlp

## Why this is the lowest-cost practical setup

For a demo or a small production rollout, this stack keeps fixed infrastructure costs low:

- Chroma runs locally or in a small container, so there is no managed vector DB bill for early traffic.
- Local embeddings avoid per-request embedding charges.
- Transcript extraction is attempted from native caption sources first, which is much cheaper than calling a paid transcription API for every upload.
- The backend only retrieves a handful of chunks per question, so LLM spend stays bounded even as the corpus grows.

For scale beyond a few thousand creators per day, the better cost-quality tradeoff is usually Qdrant or pgvector with batched embeddings and a cheaper hosted model, but Chroma is the fastest path for a clean demo.

## Local setup

1. Create a Python virtual environment and install backend dependencies.
2. Install frontend dependencies.
3. Copy `.env.example` to `.env` and fill in the values.
4. Start the backend and frontend separately.

### Backend

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Environment variables

See `.env.example` for the full list.

## Notes

- Transcript extraction is best on public videos with available captions or subtitle tracks.
- Gemini is the default live model path when `GOOGLE_API_KEY` is set.
- The backend enforces a hard budget cap using `CREDIT_BUDGET_USD` and blocks new requests once remaining credit reaches `MINIMUM_REMAINING_CREDIT_USD`.
- The frontend shows an animated credit meter with used/remaining budget and updates it after every streamed response.
- If a video has no transcript source, the backend returns a clear error instead of silently fabricating one.
- The chat response streams token-by-token and appends citations that point to the exact video chunk used.
