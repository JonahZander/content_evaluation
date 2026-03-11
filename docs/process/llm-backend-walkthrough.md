# LLM Backend Walkthrough

This document explains how the backend chooses an analysis model, where the agent prompts live, and how to run a real post-analysis flow locally.

## High-Level Flow

1. The API receives a run request and creates an `AnalysisArtifact`.
2. The worker picks up the queued job and calls the LangGraph-backed orchestrator.
3. The orchestrator resolves source content, normalizes the document, and schedules agent nodes.
   - URL inputs try direct fetch first and fall back to Tavily extract when needed.
4. Analysis agents use the LangChain provider layer.
5. Search-based similarity uses Tavily directly.
6. Artifact assembly turns agent outputs into anchors, comments, threads, events, and summary data.

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
CONTENT_EVAL_OPENAI_MODEL_NAME=gpt-4.1-mini
CONTENT_EVAL_TAVILY_API_KEY=YOUR_TAVILY_KEY
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
2. Paste text or use a URL
3. Keep the default agent selection or toggle agents on/off
4. Click `Analyze content`
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
- `services/api/src/content_evaluation/agents/instructions/audience.md`
- `services/api/src/content_evaluation/agents/instructions/editorial.md`
- `services/api/src/content_evaluation/agents/instructions/similarity.md`
- `services/api/src/content_evaluation/agents/instructions/synthesis.md`
- `services/api/src/content_evaluation/agents/instructions/value.md`

How they are loaded:

1. `AgentDefinition.instruction_file` is declared in `agents/registry.py`
2. `load_instruction_text()` reads the matching markdown file
3. `LangChainAnalysisProvider._build_prompt()` combines:
   - agent id
   - title
   - instruction text
   - upstream dependency context
   - normalized document blocks

There is also one shared system prompt in:

- `services/api/src/content_evaluation/providers/langchain/client.py`

That system prompt is global. The markdown files are the per-agent instructions.

## Current State Of The Research Model

The similarity/research agent is not yet a full tool-using LLM research chain.

What is implemented today:

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

So the current research stack is:

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
