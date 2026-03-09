# Content Evaluation

Agent-first planning scaffold for a Next.js application that evaluates blog posts and long-form text.

The planned product accepts:

- A blog post URL
- An uploaded text file
- Pasted raw text

The planned system runs a multi-agent analysis pipeline that can:

- Search for similar existing posts and possible topical overlap
- Estimate whether content is likely AI-generated
- Identify the post's main value and likely audience
- Score whether the content is worth reading
- Suggest targeted improvements and attach comments to text spans

This repository is intentionally documentation-first. The initial goal is to make the project legible to coding agents before implementing the full application.

Start here:

- Repo map: `ARCHITECTURE.md`
- Agent entrypoint: `AGENTS.md`
- Documentation index: `docs/index.md`
