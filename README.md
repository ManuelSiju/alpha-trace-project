# Alpha-Tracer

OSINT intelligence platform. Local LLM (Ollama). Free / open-source only. No paid APIs.

## Intended use

Built for security research, journalism, and due-diligence checks on entities that have
consented to being investigated (e.g. vetting your own digital footprint, a hiring
background check with the candidate's knowledge, an authorized pentest engagement). It is
**not** built for, and must not be used for, stalking, harassment, or investigating someone
without a lawful basis to do so. Findings are probabilistic (an HTTP 200 on a profile URL
is not proof of ownership) — treat everything as a lead to verify, not a fact.

## What it does

Given an email / username / phone / name / domain, fans out across 11 OSINT agents
(Sherlock username sweep, Holehe email-to-site enumeration, GitHub profile + linked
website/handles, DuckDuckGo-backed multi-engine search incl. portfolio discovery,
Instaloader, PRAW, WHOIS/DNS/crt.sh, XposedOrNot breach lookup, EXIF, Gravatar public
profile, Wayback CDX archived-page mining, and cross-platform handle correlation),
aggregates findings, and uses a local LLM to synthesize a structured briefing + an
interactive Q&A session ("the Consulting Room").

## Quick start

```bash
git clone <this repo>
cd alpha-trace-project
./alpha              # macOS/Linux
alpha.bat            # Windows
# or, if you have `make`:
make run
```

That's it — `./alpha` / `alpha.bat` provisions everything itself:

- Installs [`uv`](https://docs.astral.sh/uv/) for your user account only (no sudo/admin) if
  it isn't already on your PATH.
- Creates `.venv` with Python 3.11 and installs `requirements.txt` via `uv`.
- Runs a one-time `playwright install chromium`. No agent in the current codebase actually
  does browser-based scraping yet — this step exists for a possible future browser-based
  agent — so a failure here is just a warning, never a blocker.
- Installs Ollama if it isn't on PATH, starts the daemon if it isn't already running, and
  pulls the model (`qwen2.5:3b-instruct` by default, ~2-4 GB) if it isn't already pulled —
  all automatic, no separate step. If any of that fails, it says so and continues anyway
  with a deterministic, non-LLM fallback rather than blocking the app from starting.
- Launches the app: a splash screen, then "Press any key to open a new case."

From there: pick an identifier type, enter a value, watch the Evidence Board as each
operative (agent) reports in, read the deductions, then ask Watson questions in the
Consulting Room. Type `/done` to leave chat, then `[N]` to open another case or `[Q]` to
close the case file — both destroy the case's data; closing also prints a confirmation
once the purge is verified.

### Ollama (for LLM-backed deductions)

`./alpha` / `alpha.bat` / `make run` handle this for you — install, start, and pull the
model happen automatically on first run. To do it by hand instead (e.g. to pick a
different model):

```bash
curl -fsSL https://ollama.com/install.sh | sh   # Linux; see ollama.com/download for macOS/Windows
ollama serve &
ollama pull qwen2.5:3b-instruct                 # ~2 GB, fits in 8 GB RAM
```

If the automatic install/start/pull fails for any reason, Alpha-Tracer still works — briefings fall back to a deterministic,
non-LLM summary, and the Consulting Room's chat and `/timeline` will say so plainly instead
of pretending to have an answer.

### Manual setup (if you'd rather not use the launcher)

```bash
python3 -m venv .venv
source .venv/bin/activate      # .venv\Scripts\activate on Windows
pip install -r requirements.txt
playwright install chromium    # optional
python main.py                 # interactive CLI/GUI picker
python main.py cli interactive # go straight to the CLI's guided flow
python main.py gui             # Streamlit GUI on localhost:8501
```

### Optional configuration

```bash
cp .env.example .env
# edit .env to add Reddit API keys (free tier) if you want SocialMediaAgent's
# Reddit lookup active — without them it's skipped, not broken
```

Drop a logo at `assets/alpha-trace.png` if you want one in the Streamlit GUI's header and
sidebar; it's entirely optional and the GUI works fine without it.

### CLI flags

- `--plain` — no color, no box-drawing. Use for piped output, logging, or no-color terminals.
- `--fast` — skip the typewriter reveal animation.

Both are options on the `cli` group, e.g. `python main.py cli --plain --fast interactive`
or `./alpha cli --fast investigate --email someone@example.com`.

## Privacy and the session store — what's actually guaranteed

Case data (the target's identifiers, the briefing, the chat history) lives only in this
process's memory for the duration of one case. It is never written to disk in plaintext.
The one place disk *is* used — an opt-in per-agent HTTP cache — writes only inside a
per-session temporary directory, encrypted with a random key generated fresh for that
session and held only in memory. Closing a case (or opening a new one) drops the record,
drops the key, deletes that directory, and runs `gc.collect()`; a crash-free process exit
does the same via an `atexit` hook; every launch sweeps and deletes any leftover session
directories from a previous run that didn't exit cleanly (e.g. a hard kill).

**What this does not guarantee**, because no user-space Python program can:

- **SSD wear-leveling and copy-on-write filesystems** can retain a copy of data in a block
  the drive/filesystem silently relocated, even after the file referencing it is deleted.
- **OS swap** can have paged out a process's memory (including the in-RAM session record)
  to disk before it was ever explicitly written anywhere.
- **The OS page cache and journaling filesystems** can retain fragments of a deleted file's
  prior contents for some time after deletion.
- None of the above is something `os.remove()`, encryption-then-delete, or `gc.collect()`
  can reach into and scrub — they operate below the filesystem API this program uses.

In short: Alpha-Tracer does everything it reasonably can at the application layer (nothing
is deliberately persisted, and the one disk-touching path is encrypted and purged), but it
cannot make a mathematically-certain "unrecoverable" claim about a general-purpose OS and
disk it doesn't control. If that residual risk matters for your use case (e.g. full-disk
forensic resistance), run it in a VM or container you destroy after the session, or on
encrypted-at-rest, swap-disabled infrastructure.

Logging: identifiers (email, username, phone, name, domain) are redacted before they ever
reach `alpha_tracer.log` or the console — see `core/utils/validators.py::redact`.

`/export` (in the Consulting Room) is the only way data leaves a session, and only to a
path you explicitly provide, on explicit request.

## Troubleshooting

- **"uv was installed but isn't on PATH"** — open a new terminal (so it picks up the
  updated PATH from the installer) and re-run `./alpha` / `alpha.bat`.
- **"Ollama server is not reachable"** — the launcher tries to install/start/pull it
  automatically on every run; if you still see this it means that failed silently in the
  background (check `/tmp/alpha-tracer-ollama.log` on Linux/macOS) or you launched via
  `python main.py` directly instead of `./alpha`/`alpha.bat`/`make run`. It's a warning, not
  a failure — the app continues with a deterministic fallback briefing either way. Manual
  fix: `ollama serve &` (Linux/macOS) or open the Ollama app (Windows).
- **`sherlock error ...: No such file or directory`** — usually means `.venv`'s installed
  console scripts point at a stale interpreter path (e.g. the project directory was moved
  or renamed after the first `pip install`). Recreate the environment:
  `rm -rf .venv && ./alpha ...`.
- **Playwright/Chromium install failed** — nothing in the app currently depends on
  Playwright; everything else still works.
- **GUI shows "Ollama offline — fallback mode"** — same as the CLI case above; check the
  fix line shown in the sidebar.

## Architecture

```
main.py
  └─ cli/main.py                 click entrypoint — the detective-themed guided flow
  └─ gui/app.py                  streamlit entrypoint
alpha / alpha.bat                launchers: provision via uv, then run main.py
core/
  llm/ollama_client.py           local LLM via Ollama HTTP (num_ctx always set explicitly)
  llm/preflight.py               one Ollama status/fix contract shared by CLI and GUI
  agents/orchestrator.py         asyncio fan-out of all agents, emits real per-agent events
  agents/*_agent.py              per-source intelligence gatherers
  analyzers/profile_synthesizer.py  dedupe + per-category ranking, then one LLM call;
                                     evidence-id-bounded top-k retrieval for chat
  analyzers/timeline_builder.py  LLM-driven event timeline (degrades honestly when offline)
  analyzers/relationship_mapper.py  deterministic target→finding→URL graph
  knowledge_graph/               networkx graph + GUI visualizer
  memory/session_store.py        RAM-first case record; encrypted per-session temp-dir cache
  utils/keypress.py              single-keypress start / [N]/[Q] menu (termios/msvcrt)
  utils/branding.py              detective-theme palette, splash, dividers
```

## Stack

- **LLM**: Ollama running `qwen2.5:3b-instruct` (default) or `phi3.5:3.8b` (low-RAM fallback)
- **Session privacy**: `cryptography` (Fernet) for the encrypted per-session cache
- **Scraping**: requests/httpx
- **Search**: `ddgs`, whose `backend="auto"` already fans out across multiple real engines
  (DuckDuckGo, Brave, Startpage, Yandex, Google, Yahoo, Mojeek, and more) per query; wrapped
  with `tenacity` retry and a shared timeout budget
- **OSINT CLIs**: sherlock-project, holehe (called via subprocess)
- **Social**: instaloader (IG), praw (Reddit, needs free-tier API keys in `.env` to activate)
- **Network**: python-whois, dnspython, crt.sh (subdomains)
- **UI**: rich (CLI), streamlit + streamlit-agraph (GUI)
- **Launcher**: `uv` for Python/dependency provisioning

## Legal

Public-source OSINT only. No data-broker or people-search-site scraping — PhoneAgent and
PeopleSearchAgent are intentionally limited to lawful structured lookups (`phonenumbers`
parsing, public wayback-archive availability) and say so explicitly in the briefing when
that's all they have. LinkedIn/Facebook scraping is disabled by default (ToS risk). Use
only against entities you have authorization to investigate.

## Testing

`pytest` from the repo root. The suite runs fully offline — an autouse fixture blocks real
socket connections, so any test that accidentally needs the real network fails loudly
instead of silently succeeding against the internet. All fixtures use synthetic identities,
never real people.

## Test target

The one identity used across the test suite and this README's examples is a synthetic
fixture (`jamiecarter2004@gmail.com` / "Jamie Carter") — never a real third party.

## Development tracker

See [`CASEBOOK.md`](CASEBOOK.md) for the full backlog, what's done, and open decisions.
