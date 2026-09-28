# Alpha-Tracer

OSINT intelligence platform. Local LLM (Ollama). Free / open-source only. No paid APIs.

## What it does

Given an email / username / phone / name / domain, fans out across 10 OSINT agents (Sherlock, Holehe, GitHub, DuckDuckGo, Instaloader, snscrape, PRAW, WHOIS/DNS, breach DBs, EXIF), aggregates findings, and uses a local LLM to synthesize a structured intelligence briefing + interactive Q&A.

## Behavior

1. Run `investigate` → all enabled agents fan out → findings collected.
2. CLI/GUI renders structured briefing **and** a full plain-text dump of every raw finding.
3. **Chat session auto-starts** with the gathered context as the LLM's working memory.
4. Type `end` / `end session` (or `quit`, `exit`, `q`, `bye`) → session JSON deleted + HTTP cache wiped → nothing retained on disk.
5. In the Streamlit GUI, sidebar "End session & wipe data" button does the same.

## Setup

```bash
# 1. Ollama daemon
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &                       # in background
ollama pull qwen2.5:3b-instruct      # ~2 GB, fits 8 GB RAM

# 2. Python venv + deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Optional browsers (only if you want LinkedIn scraping)
playwright install chromium

# 4. Env file
cp .env.example .env
# edit if you have Reddit/Shodan free-tier keys

# 5. Drop project logo at assets/alpha-trace.png (optional)
```

## Run

```bash
# Interactive menu (CLI or GUI choice)
python main.py

# CLI direct
python main.py cli investigate --email jamiecarter2004@gmail.com --name "Jamie Carter"

# Streamlit GUI on localhost:8501
python main.py gui
```

## Architecture

```
main.py
  └─ cli/main.py            click entrypoint
  └─ gui/app.py             streamlit entrypoint
core/
  llm/ollama_client.py      local LLM via Ollama HTTP
  agents/orchestrator.py    asyncio fan-out of all agents
  agents/*_agent.py         per-source intelligence gatherers
  analyzers/synthesizer.py  LLM-driven briefing builder
  knowledge_graph/          networkx entity graph
  memory/                   session JSON + sqlite cache
```

## Stack

- **LLM**: Ollama running `qwen2.5:3b-instruct` (default) or `phi3.5:3.8b` (low-RAM fallback)
- **Scraping**: requests/httpx/bs4/cloudscraper; Playwright lazy-loaded
- **OSINT CLIs**: sherlock-project, holehe (called via subprocess)
- **Social**: snscrape (X), instaloader (IG), praw (Reddit)
- **Network**: python-whois, dnspython, ipwhois, crt.sh (subdomains)
- **UI**: rich (CLI), streamlit + streamlit-agraph (GUI)

## Legal

Public-source OSINT only. Default config disables LinkedIn / Facebook (ToS risk). Respects `robots.txt`. Rate-limited per-host. Use against entities you have authorization to investigate.

## Test target

System ships with an end-to-end test using a synthetic fixture identity (`jamiecarter2004@gmail.com`) — never a real third party.
