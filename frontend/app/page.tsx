"use client";

import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";

type VideoMetadata = {
  video_id: string;
  label: string;
  platform: string;
  url: string;
  title: string;
  creator: string;
  follower_count?: number | null;
  views: number | null;
  likes: number;
  comments: number;
  hashtags: string[];
  upload_date?: string | null;
  duration_seconds?: number | null;
  engagement_rate: number;
  transcript_preview: string;
  hook_preview: string;
  chunk_count: number;
};

type PairPayload = {
  pair_id: string;
  videos: VideoMetadata[];
};

type Message = {
  role: "user" | "assistant";
  content: string;
};

type SourceChunk = {
  video_id: string;
  chunk_id: string;
  chunk_index: number;
  label: string;
  excerpt: string;
  source_url: string;
};

type CreditStatus = {
  budget_usd: number;
  used_usd: number;
  remaining_usd: number;
  used_percent: number;
  input_tokens_est: number;
  output_tokens_est: number;
};

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

function usePersistentState<T>(key: string, initialValue: T) {
  const [state, setState] = useState<T>(initialValue);
  useEffect(() => {
    const raw = window.localStorage.getItem(key);
    if (raw) {
      try {
        setState(JSON.parse(raw));
      } catch {
        window.localStorage.removeItem(key);
      }
    }
  }, [key]);
  useEffect(() => {
    window.localStorage.setItem(key, JSON.stringify(state));
  }, [key, state]);
  return [state, setState] as const;
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat().format(value);
}

function formatDuration(seconds?: number | null) {
  if (!seconds) return "-";
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}:${String(remaining).padStart(2, "0")}`;
}

function isPairNotFound(value: unknown) {
  return typeof value === "string" && value.toLowerCase().includes("unknown pair_id");
}

function renderInlineMarkdown(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

function renderAssistantContent(content: string) {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const nodes: ReactNode[] = [];
  let listItems: string[] = [];
  let listType: "ul" | "ol" | null = null;

  const flushList = () => {
    if (!listItems.length || !listType) return;
    const items = listItems.map((item, index) => <li key={`${listType}-${index}`}>{renderInlineMarkdown(item)}</li>);
    nodes.push(listType === "ol" ? <ol key={`ol-${nodes.length}`}>{items}</ol> : <ul key={`ul-${nodes.length}`}>{items}</ul>);
    listItems = [];
    listType = null;
  };

  for (const [index, line] of lines.entries()) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      continue;
    }

    const heading = trimmed.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      flushList();
      nodes.push(
        <div className={`md-heading level-${heading[1].length}`} key={`heading-${index}`}>
          {renderInlineMarkdown(heading[2])}
        </div>,
      );
      continue;
    }

    const bullet = trimmed.match(/^[-*]\s+(.*)$/);
    if (bullet) {
      if (listType && listType !== "ul") flushList();
      listType = "ul";
      listItems.push(bullet[1]);
      continue;
    }

    const numbered = trimmed.match(/^\d+\.\s+(.*)$/);
    if (numbered) {
      if (listType && listType !== "ol") flushList();
      listType = "ol";
      listItems.push(numbered[1]);
      continue;
    }

    flushList();
    nodes.push(
      <p key={`p-${index}`}>
        {renderInlineMarkdown(trimmed)}
      </p>,
    );
  }

  flushList();
  return <div className="message-markdown">{nodes}</div>;
}

export default function Home() {
  const [videoAUrl, setVideoAUrl] = useState("");
  const [videoBUrl, setVideoBUrl] = useState("");
  const [pair, setPair] = usePersistentState<PairPayload | null>("creator-rag-pair", null);
  const [messages, setMessages] = usePersistentState<Message[]>("creator-rag-messages", []);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [sources, setSources] = useState<SourceChunk[]>([]);
  const [credits, setCredits] = useState<CreditStatus | null>(null);
  const [providers, setProviders] = useState<Record<string, { available: boolean; model: string }>>({});
  const [selectedProvider, setSelectedProvider] = usePersistentState<string | null>("creator-rag-provider", null);
  const [selectedModel, setSelectedModel] = usePersistentState<string | null>("creator-rag-model", null);
  const [testStatus, setTestStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const threadId = useMemo(() => "thread-main", []);
  const logRef = useRef<HTMLDivElement | null>(null);

  async function fetchCredits(pairId: string, targetThreadId: string) {
    const response = await fetch(`${BACKEND_URL}/api/credits/${pairId}?thread_id=${encodeURIComponent(targetThreadId)}`);
    if (!response.ok) {
      return;
    }
    const payload = (await response.json()) as CreditStatus;
    setCredits(payload);
  }

  useEffect(() => {
    if (pair?.pair_id) {
      fetch(`${BACKEND_URL}/api/pairs/${pair.pair_id}`)
        .then(async (response) => {
          if (response.ok) return response.json();
          if (response.status === 404) {
            setPair(null);
            setMessages([]);
            setSources([]);
            setCredits(null);
            setError("Saved pair is no longer available. Please ingest the videos again.");
            window.localStorage.removeItem("creator-rag-pair");
          }
          return null;
        })
        .then((payload) => {
          if (payload?.videos) {
            setPair(payload);
            fetchCredits(payload.pair_id, threadId).catch(() => undefined);
          }
        })
        .catch(() => undefined);
    }
  }, [pair?.pair_id, setPair, threadId]);

    useEffect(() => {
      (async () => {
        try {
          const r = await fetch(`${BACKEND_URL}/api/providers`);
          const body = r.ok ? await r.json() : {};
          const respBody = (body ?? {}) as any;
          setProviders(respBody ?? {});

          if (selectedProvider) return;

          const priority = ["gemini"];
          for (const key of priority) {
            const info = respBody?.[key];
            if (!info || !info.available) continue;
            setTesting(true);
            setTestStatus(null);
            try {
              const res = await fetch(`${BACKEND_URL}/api/providers/test`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider: key, model: info.model }),
              });
              const j = await res.json();
              if (j.ok) {
                setSelectedProvider(key);
                setSelectedModel(info.model ?? null);
                setTestStatus({ ok: true, message: `Using ${key} — ${info.model}` });
                setTesting(false);
                return;
              } else {
                setTestStatus({ ok: false, message: `${key} test failed: ${j.error ?? 'unknown'}` });
              }
            } catch (err) {
              setTestStatus({ ok: false, message: String(err) });
            } finally {
              setTesting(false);
            }
          }

          setTestStatus({ ok: false, message: 'No working Gemini provider found. Set GOOGLE_API_KEY.' });
        } catch {
          setProviders({});
          setTestStatus({ ok: false, message: 'Failed to fetch providers' });
        }
      })();
    }, [selectedProvider, setSelectedModel, setSelectedProvider]);

  useEffect(() => {
    const node = logRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [messages, streaming]);

  async function handleIngest(event: FormEvent) {
    event.preventDefault();
    if (ingesting) return;
    setLoading(true);
    setIngesting(true);
    setError("");
    setSources([]);
    try {
      const response = await fetch(`${BACKEND_URL}/api/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_a_url: videoAUrl, video_b_url: videoBUrl }),
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Failed to ingest videos.");
      }
      const payload = (await response.json()) as PairPayload;
      setPair(payload);
      setMessages([]);
      await fetchCredits(payload.pair_id, threadId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ingestion failed.");
    } finally {
      setLoading(false);
      setIngesting(false);
    }
  }

  async function sendMessage(nextQuestion: string) {
    if (!pair?.pair_id || !nextQuestion.trim()) return;
    setStreaming(true);
    setError("");
    setSources([]);
    setQuestion("");
    setMessages((current) => [...current, { role: "user", content: nextQuestion }, { role: "assistant", content: "" }]);
    try {
      const response = await fetch(`${BACKEND_URL}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pair_id: pair.pair_id, message: nextQuestion, thread_id: threadId, model: selectedModel }),
      });
      if (!response.ok || !response.body) {
        let detail = "Streaming endpoint unavailable.";
        try {
          const payload = await response.json();
          detail = payload.detail ?? detail;
        } catch {
          const text = await response.text();
          if (text) {
            detail = text;
          }
        }
        throw new Error(detail);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";
        for (const block of blocks) {
          if (block.startsWith("event: sources")) {
            const dataLine = block.split("\n").find((line) => line.startsWith("data: "));
            if (dataLine) {
              try {
                setSources(JSON.parse(dataLine.slice(6)) as SourceChunk[]);
              } catch {
                setSources([]);
              }
            }
            continue;
          }
          if (block.startsWith("event: token")) {
            const dataLine = block.split("\n").find((line) => line.startsWith("data: "));
            if (dataLine) {
              let token = "";
              try {
                token = JSON.parse(dataLine.slice(6)) as string;
              } catch {
                token = dataLine.slice(6);
              }
              setMessages((current) => {
                const next = [...current];
                next[next.length - 1] = { role: "assistant", content: `${next[next.length - 1]?.content ?? ""}${token}` };
                return next;
              });
            }
          }
          if (block.startsWith("event: budget")) {
            const dataLine = block.split("\n").find((line) => line.startsWith("data: "));
            if (dataLine) {
              try {
                setCredits(JSON.parse(dataLine.slice(6)) as CreditStatus);
              } catch {
              }
            }
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Chat failed.";
      if (isPairNotFound(message)) {
        setPair(null);
        setMessages([]);
        setSources([]);
        setCredits(null);
        window.localStorage.removeItem("creator-rag-pair");
        setError("Saved pair is no longer available. Please ingest the videos again.");
      } else {
        setError(message);
      }
      setMessages((current) => current.slice(0, -1));
    } finally {
      setStreaming(false);
      fetchCredits(pair.pair_id, threadId).catch(() => undefined);
    }
  }

  const usedPercent = Math.min(100, Math.max(0, credits?.used_percent ?? 0));
  const budgetIsFinite = (credits?.budget_usd ?? 0) > 0;
  const remainingPercent = Math.max(0, 100 - usedPercent);

  function creditSeverityClass() {
    if (!budgetIsFinite) return "good";
    if (remainingPercent > 40) return "good";
    if (remainingPercent > 15) return "warn";
    return "low";
  }
  const criticalThreshold = 5;
  const [flash, setFlash] = useState(false);

  useEffect(() => {
    if (!budgetIsFinite) return;
    if (remainingPercent <= criticalThreshold) {
      setFlash(true);
      const t = setTimeout(() => setFlash(false), 2200);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [remainingPercent, budgetIsFinite]);

  const promptPresets = [
    "Why did Video A get more engagement than Video B?",
    "What's the engagement rate of each?",
    "Compare the hooks in the first 5 seconds.",
    "Who's the creator of Video B and what's their follower count?",
    "Suggest improvements for B based on what worked in A.",
  ];

  return (
    <main className="shell">
      <section className="hero">
        <div className="hero-card">
          <div className="eyebrow">Creator intelligence dashboard</div>
          <h1>Compare two videos with grounded, streamed analysis.</h1>
          <p>
            Drop in one YouTube URL and one Instagram Reel, index both transcripts, and ask the assistant why one
            outperformed the other. Answers stream live and cite the exact chunk they came from.
          </p>
        </div>
        <div className="panel stats">
          <div className="stat">
            <div className="stat-label">Vector DB</div>
            <div className="stat-value">MongoDB</div>
          </div>
          <div className="stat">
            <div className="stat-label">Orchestration</div>
            <div className="stat-value">LangChain</div>
          </div>
          <div className="stat">
            <div className="stat-label">Responses</div>
            <div className="stat-value">Streaming</div>
          </div>
          <div className="stat">
            <div className="stat-label">Memory</div>
            <div className="stat-value">Per thread</div>
          </div>
        </div>
      </section>

      <section className="workspace">
        <div className="left-column">
          <form className="panel" onSubmit={handleIngest}>
            <h2>Load the two URLs</h2>
            {ingesting ? (
              <div className="ingest-banner" aria-live="polite">
                <div className="ingest-spinner" />
                <div>
                  <div className="ingest-title">Ingesting videos</div>
                  <div className="small">Fetching metadata, transcript, and chunks. This can take a moment.</div>
                </div>
              </div>
            ) : null}
            <div className="form-grid">
              <div className="field">
                <label htmlFor="video-a">YouTube URL</label>
                <input
                  id="video-a"
                  value={videoAUrl}
                  onChange={(event) => setVideoAUrl(event.target.value)}
                  placeholder="https://www.youtube.com/watch?v=..."
                />
              </div>
              <div className="field">
                <label htmlFor="video-b">Instagram Reel URL</label>
                <input
                  id="video-b"
                  value={videoBUrl}
                  onChange={(event) => setVideoBUrl(event.target.value)}
                  placeholder="https://www.instagram.com/reel/..."
                />
              </div>
              <div className="row">
                <button className="button primary" type="submit" disabled={loading || ingesting}>
                  {loading ? "Loading videos..." : "Ingest videos"}
                </button>
                <button
                  className="button secondary"
                  type="button"
                  disabled={!pair}
                  onClick={() => {
                    setMessages([]);
                    setSources([]);
                    setQuestion("");
                  }}
                >
                  Reset chat
                </button>
              </div>
              {error ? <div className="error">{error}</div> : null}
            </div>
          </form>

          {pair?.videos ? (
            <div className="grid-two">
              {pair.videos.map((video) => (
                <article className="video-card" key={video.video_id}>
                  <div className="video-top">
                    <span className="badge">{video.label}</span>
                    <span className="small">{video.platform}</span>
                  </div>
                  <div className="video-body">
                    <div className="video-title">{video.title}</div>
                    <div className="small">{video.creator}</div>
                    <div className="meta-grid">
                      <div className="meta">
                        <span className="key">Views</span>
                        <span className="value">{formatNumber(video.views)}</span>
                      </div>
                      <div className="meta">
                        <span className="key">Engagement</span>
                        <span className="value">{video.engagement_rate.toFixed(2)}%</span>
                      </div>
                      <div className="meta">
                        <span className="key">Likes</span>
                        <span className="value">{formatNumber(video.likes)}</span>
                      </div>
                      <div className="meta">
                        <span className="key">Comments</span>
                        <span className="value">{formatNumber(video.comments)}</span>
                      </div>
                      <div className="meta">
                        <span className="key">Followers</span>
                        <span className="value">{formatNumber(video.follower_count)}</span>
                      </div>
                      <div className="meta">
                        <span className="key">Duration</span>
                        <span className="value">{formatDuration(video.duration_seconds)}</span>
                      </div>
                    </div>
                    <div className="stack">
                      <div className="small"><strong>Hook:</strong> {video.hook_preview || "No hook preview available."}</div>
                      <div className="small"><strong>Transcript preview:</strong> {video.transcript_preview || "No preview available."}</div>
                      <div className="small">
                        <strong>Hashtags:</strong> {video.hashtags.length ? video.hashtags.map((tag) => `#${tag}`).join(" ") : "-"}
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : null}
        </div>

        <div className="right-column">
          <section className="panel chat-box">
            <h2>Chat with memory</h2>
            {error ? <div className="error-banner">{error}</div> : null}
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
              <div className="small">Model status:</div>
              {testing ? (
                <div className="small">Testing provider…</div>
              ) : testStatus ? (
                <div className={testStatus.ok ? 'small' : 'error'}>{testStatus.message}</div>
              ) : (
                <div className="small">Detecting provider…</div>
              )}
            </div>
            <div className="credit-meter">
              <div className="credit-head">
                <span className="small">Credit usage</span>
                <span className="small">{(credits?.used_usd ?? 0).toFixed(4)} / {(credits?.budget_usd ?? 0) > 0 ? (credits?.budget_usd ?? 0).toFixed(2) + ' USD' : 'Free tier'}</span>
              </div>
              <div className="credit-track" aria-label="Credit usage bar">
                <div className={`credit-fill ${creditSeverityClass()} ${flash ? 'flashing' : ''}`} style={{ width: `${usedPercent}%` }} />
                <div className={`credit-knob ${creditSeverityClass()} ${flash ? 'flashing' : ''}`} style={{ left: `${usedPercent}%`, transform: 'translateX(-50%)' }} aria-hidden />
              </div>
              <div className="credit-foot">
                <span className="small">Used: {(credits?.used_usd ?? 0).toFixed(4)} USD</span>
                <span className="small">Left: {(credits?.remaining_usd ?? 0).toFixed(4)} USD</span>
              </div>
            </div>
            <div className="row">
              {promptPresets.map((preset) => (
                <button
                  key={preset}
                  className="button secondary"
                  type="button"
                  disabled={!pair || streaming || (credits?.remaining_usd ?? 0) <= 0}
                  onClick={() => sendMessage(preset)}
                >
                  {preset}
                </button>
              ))}
            </div>

            <div className="field">
              <label htmlFor="question">Ask a custom question</label>
              <textarea
                id="question"
                rows={4}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Why did Video A outperform Video B?"
              />
            </div>

            <div className="row">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button
                  className="button primary"
                  type="button"
                  disabled={!pair || streaming || !question.trim() || (budgetIsFinite && (credits?.remaining_usd ?? 0) <= 0)}
                  onClick={() => sendMessage(question)}
                >
                  {streaming ? "Streaming answer..." : "Send"}
                </button>
                <div className="small" style={{ color: (!pair ? 'var(--muted)' : streaming ? 'var(--muted)' : (budgetIsFinite && (credits?.remaining_usd ?? 0) <= 0) ? 'var(--danger)' : 'var(--muted)') }}>
                  {!pair ? 'Ingest videos to enable chat' : streaming ? 'Answer streaming' : (budgetIsFinite && (credits?.remaining_usd ?? 0) <= 0) ? 'Insufficient credits' : ''}
                </div>
              </div>
            </div>

            <div className="chat-log" ref={logRef}>
              {messages.length ? messages.map((message, index) => (
                <div className={`bubble ${message.role}`} key={`${message.role}-${index}`}>
                  {message.role === "assistant"
                    ? (message.content ? renderAssistantContent(message.content) : (streaming ? <span className="typing">● ● ●</span> : ""))
                    : (message.content || "")}
                </div>
              )) : <div className="small">Load the videos, then ask one of the preset questions to start the RAG flow.</div>}
            </div>

            <div className="sources">
              {sources.map((source) => (
                <span className="source-chip" key={source.chunk_id}>
                  {source.label} · chunk {source.chunk_index}
                </span>
              ))}
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}
