# LLM Backend Walkthrough

This document explains how the backend chooses an analysis model, where the agent prompts live, and how to run a real post-analysis flow locally.

## High-Level Flow

1. The API receives a run request and creates an `AnalysisArtifact`.
2. The worker picks up the queued job and calls the LangGraph-backed orchestrator.
3. The orchestrator resolves source content, normalizes the document, and schedules agent nodes.
   - URL inputs try direct fetch first and fall back to Tavily extract when needed.
4. Analysis agents use the LangChain provider layer.
5. Fact-check uses the vendored deep-research graph for live web verification and overlap research.
6. Artifact assembly turns agent outputs into anchors, comments, threads, events, summary data, and revision workflows.

Key entry points:

- Backend config:
  - `services/api/src/content_evaluation/config.py`
- Provider routing:
  - `services/api/src/content_evaluation/providers/langchain/client.py`
- Agent registry:
  - `services/api/src/content_evaluation/agents/registry.py`
- LangGraph orchestration:
  - `services/api/src/content_evaluation/services/orchestration.py`

## How To Enable OpenAI

The backend now supports multiple analysis-provider families. For local development, copy values into `services/api/.env` using `services/api/.env.example` as the reference.

Minimum OpenAI-backed settings:

```env
CONTENT_EVAL_ANALYSIS_PROVIDER_FAMILY=openai
CONTENT_EVAL_OPENAI_API_KEY=YOUR_OPENAI_KEY
CONTENT_EVAL_OPENAI_MODEL_NAME=gpt-5.4-2026-03-05
CONTENT_EVAL_TAVILY_API_KEY=YOUR_TAVILY_KEY
```

Deep-research model routing (used by `fact_check` and `research` agents):

```env
# Heavy model: supervisor reasoning, researcher agents, final JSON synthesis.
# Leave blank to fall back to CONTENT_EVAL_OPENAI_MODEL_NAME.
CONTENT_EVAL_DEEP_RESEARCH_MODEL_NAME=gpt-5.4-2026-03-05
# Light model: Tavily webpage summarisation + sub-agent findings compression.
CONTENT_EVAL_DEEP_RESEARCH_SUMMARIZATION_MODEL=gpt-5.4-mini-2026-03-17
```

Important:

- The backend only enters `live` mode when:
  - the selected analysis-provider key exists
  - and `CONTENT_EVAL_TAVILY_API_KEY` exists
- If either is missing, the app falls back to mock mode in development/test.

Optional tuning:

```env
CONTENT_EVAL_ANALYSIS_TEMPERATURE=0
CONTENT_EVAL_ANALYSIS_MAX_RETRIES=3
CONTENT_EVAL_PROVIDER_TIMEOUT_SECONDS=45
```

## How To Test A Real Post Analysis

At the repo root:

```bash
nvm use
npm install
uv sync --directory services/api --extra dev
```

Start the API:

```bash
npm run dev:api
```

Start the web app in another terminal:

```bash
npm run dev:web
```

Then:

1. Open `http://localhost:3000`
2. Paste text, use a URL, or upload a `.txt` / `.md` file for a live run
3. Keep the default agent selection or toggle agents on/off
4. Click `Analyze content` for live runs
5. Watch the progress timeline and run log while the worker executes the graph
6. For markdown-capable inputs, the review pane will render headings, inline emphasis, and fenced code blocks without fetching images

To verify that you are in live mode, open:

- `http://localhost:8000/health`
- `http://localhost:8000/ready`

You should see:

- `processing_mode: "live"`
- `providers_ready: true`

## Where The Prompts Live

Prompt files are stored here:

- `services/api/src/content_evaluation/agents/instructions/ai_likelihood.md`
- `services/api/src/content_evaluation/agents/instructions/editorial.md`
- `services/api/src/content_evaluation/agents/instructions/fact_check/research_brief.md`
- `services/api/src/content_evaluation/agents/instructions/research.md`
- `services/api/src/content_evaluation/agents/instructions/similarity.md`

How they are loaded:

1. `AgentDefinition.instruction_file` is declared in `agents/registry.py`
2. The registry preloads the matching markdown files at import time, and `load_instruction_text()` returns the cached body during dispatch
3. `LangChainAnalysisProvider` keeps the per-agent instruction in the system message and sends a structured user payload that contains:
   - agent id
   - title
   - upstream dependency context
   - normalized document blocks
   - explicit framing that article content and upstream context are untrusted source text

The prompt-construction helpers that enforce that separation live in:

- `services/api/src/content_evaluation/providers/langchain/client.py`

That provider code hardens analysis calls against prompt injection by separating instructions from article content. The markdown files remain the per-agent instructions.

## Current State Of The Research Model

The project currently has three distinct research paths:

- `fact_check`
  - Default-enabled deep research backbone for live web verification and overlap research
- `research`
  - Hidden follow-up research agent queued against an existing artifact through `POST /api/v1/runs/{run_id}/research`
- `similarity`
  - Legacy compatibility path only; hidden from the selectable catalog for new runs

The legacy `similarity` path is still intentionally simple:

- The registry marks `similarity` as `MULTI_STEP`
- The LangGraph node emits an intermediate `running` event
- The orchestrator builds a search query from the normalized document
- The search provider calls Tavily in live mode
- The returned search results are converted into one structured finding and one summary

Current implementation details:

- Search provider:
  - `services/api/src/content_evaluation/providers/tavily/client.py`
- Query building:
  - `services/api/src/content_evaluation/services/normalization.py`
- Search-agent execution:
  - `services/api/src/content_evaluation/services/orchestration.py`

What is still intentionally simple:

- The similarity agent does not yet run a second LLM pass over search results
- The `similarity.md` instruction file exists, but the current search node does not send that prompt to an LLM yet
- The rationale and suggestion for similarity are still deterministic code-side logic derived from the search result scores

So the current legacy similarity stack is:

- Tavily search for retrieval
- deterministic synthesis in code
- LangGraph eventing/checkpointing around that node

Not yet implemented:

- search-plan -> retrieve -> rank -> summarize subgraph
- LLM-based evidence comparison between the article and found references
- multi-query search expansion
- URL-level evidence stored back into the artifact comments

## Recommended Next Improvements

- Add a second LLM summarization step for `similarity` after Tavily returns results
- Store search result titles/URLs directly in the finding metadata
- Add provider-family/model selection to the UI for developer mode
- Expose the selected analysis provider and model in the run header/debug panel
