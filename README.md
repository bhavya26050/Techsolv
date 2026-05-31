# Techsolv Creator Intelligence

A full-stack RAG app that compares two social videos side by side. It ingests a YouTube URL and an Instagram Reel URL, extracts metadata and transcripts, stores pairs, chats, credits, and transcript chunks in MongoDB, and streams grounded answers with citations.

<details>
<summary><strong>What this project does</strong></summary>

- Ingests one YouTube video and one Instagram Reel.
- Extracts metadata, hook previews, transcript text, and engagement stats.
- Chunks transcripts, embeds them, stores them in MongoDB, and searches them with cosine similarity.
- Streams answers token-by-token through Gemini with citations.
- Tracks per-thread memory and budget usage.
- Shows a live UI with an animated credit meter.

</details>

<details>
<summary><strong>Stack</strong></summary>

| Layer | Tech |
| --- | --- |
| Frontend | Next.js 15 + React 19 |
| Backend | FastAPI + Uvicorn |
| Persistence | MongoDB Atlas |
| Retrieval | Mongo-stored embeddings + cosine similarity |
| Model | Google Gemini |
| Embeddings | sentence-transformers |
| Video extraction | yt-dlp, youtube-transcript-api, instaloader |
| Deployment | Vercel + Render |

</details>

<details>
<summary><strong>Best free-tier deployment</strong></summary>

Use this setup if you want the simplest free path:

- Frontend: Vercel
- Backend: Render
- Database: MongoDB Atlas free tier

This setup keeps the app data and retrieval data inside MongoDB, so it is not tied to local files.

</details>

## Quick checklist

- [ ] Add `GOOGLE_API_KEY`
- [ ] Add `MONGO_URI`
- [ ] Set `MONGO_DB_NAME`
- [ ] Deploy backend first and copy its public URL
- [ ] Set `NEXT_PUBLIC_BACKEND_URL` in Vercel to the Render URL
- [ ] Deploy the frontend
- [ ] Ingest the two public video URLs
- [ ] Ask a comparison question

## Deploy now

### 1) Render backend

The repo includes [`render.yaml`](render.yaml) for the backend service.

1. Push this repo to GitHub.
2. Create a new Render service from the repo.
3. Use the `render.yaml` blueprint or point Render at the `backend` folder.
4. Set `GOOGLE_API_KEY`, `MONGO_URI`, and `MONGO_DB_NAME` in Render.
5. Deploy.

Your backend will expose endpoints like:

- `GET /api/health`
- `POST /api/ingest`
- `POST /api/chat/stream`

### 2) Vercel frontend

1. Import the same GitHub repo into Vercel.
2. Set the project root directory to `frontend`.
3. Add the environment variable:

```text
NEXT_PUBLIC_BACKEND_URL=https://your-render-backend-url.onrender.com
```

4. Deploy.

If you want Vercel to call the backend correctly, the backend URL must be public and reachable over HTTPS.

## Local development

### Backend

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

## Environment variables

Use `.env.example` as the source of truth.

| Variable | Purpose |
| --- | --- |
| `GOOGLE_API_KEY` | Required Gemini key |
| `GEMINI_MODEL` | Gemini model name |
| `CREDIT_BUDGET_USD` | Overall spending cap |
| `GEMINI_CREDIT_BUDGET_USD` | Provider budget |
| `DAILY_RESET_ENABLED` | Reset budget daily in UTC |
| `NEXT_PUBLIC_BACKEND_URL` | Frontend API base URL |
| `MONGO_URI` | MongoDB connection string |
| `MONGO_DB_NAME` | MongoDB database name |

## Interactive guide

<details>
<summary><strong>Need a clean first run?</strong></summary>

- Start the backend first.
- Open `/api/health` in the browser.
- Deploy the frontend after the backend URL is known.
- Ingest the two URLs only after the UI can reach the backend.

</details>

<details>
<summary><strong>Budget behavior</strong></summary>

- If `CREDIT_BUDGET_USD` is `0`, the UI shows `Free tier`.
- The credit meter turns green, yellow, or red based on remaining budget.
- Low credit triggers a flashing warning state.

</details>

<details>
<summary><strong>Troubleshooting</strong></summary>

- If the app says the pair is missing, re-ingest the videos.
- If Gemini is unavailable, verify `GOOGLE_API_KEY` and reload config.
- If transcripts are missing, the source video may not expose captions.
- If MongoDB is unreachable, check the connection string and network access rules.

</details>
