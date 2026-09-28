# CASEBOOK

Alpha-Tracer work tracker — single source of truth for all unfinished work.

**Last updated:** 2026-09-29
**Overall completion:** 7 / 36 tasks done (~19%)
**By status:** Done 7 · Open 29 · In Progress 0 · Blocked 0

Legend — Priority: P0 (blocking, ordered) · P1 · P2. Status: Open / In Progress / Blocked / Done.

---

## Core Flow

| ID | Task | Priority | Status | Files | Acceptance criteria | Notes |
|----|------|----------|--------|-------|----------------------|-------|
| CF-1 | `alpha` / `alpha.bat` launcher via `uv`: provision Python 3.11, create `.venv`, install `requirements.txt`, run `playwright install chromium` once, then start app. No sudo/admin. Clear stop message + manual install command per-OS if `uv` unfetchable. | P0 | Open | new: `alpha`, `alpha.bat`; `README.md` | Fresh clone + `./alpha` (or `alpha.bat`) on a machine with no venv/deps produces a running app with zero manual steps; killing network access to the uv installer produces a clear per-OS manual-install message, not a stack trace. | Currently zero launcher scripts exist (`find` confirms no `alpha*`, `pyproject.toml`, `uv.lock`, `Makefile`). README.md:17-38 documents fully manual setup. |
| CF-2 | Single-keypress "press any key to start" (msvcrt on Windows, termios/tty elsewhere), fallback to Enter when stdin isn't a TTY. | P0 | Open | `cli/main.py`, `main.py`, new `core/utils/keypress.py` | Interactive terminal: any single key advances past splash. Piped/non-TTY stdin: falls back to reading a line, no hang, no crash. | Zero hits repo-wide for `msvcrt`/`termios`/`tty`/`getch`; all input is `click`/`rich.prompt.Prompt`/Streamlit widgets today. |
| CF-3 | `[N]` open new case (reset state) / `[Q]` close case file, single-keypress, both trigger session-store purge; loop back to splash on `[N]` instead of exiting process. | P0 | Open | `cli/main.py:193-227` (`_chat_loop`) | After `/done`, pressing `N` starts a fresh case (new session ID, cleared chat/briefing state) without restarting the process; pressing `Q` purges and exits, printing "Case closed. Session data destroyed." only after purge is verified. | Today `_chat_loop` purges on `end`/quit then returns to shell — no loop, no `[N]` path at all. Depends on SP-1 (session store redesign) for verified purge. |
| CF-4 | Ollama preflight parity: GUI must print the same actionable fix text as CLI when server is down (not just "offline — fallback mode"); replace raw exception interpolation in generic-exception branches with a scripted message; add explicit "model not pulled" message with offer to pull. | P0 | Open | `cli/main.py:126-141`, `gui/app.py:58-65`, `core/llm/ollama_client.py:38-58` | Server down: GUI shows the exact `ollama serve &` (or OS-appropriate) fix line, matching CLI. Any Ollama-related failure path shown to the user contains zero raw Python exception text. | CLI already prints a fix line (`cli/main.py:137`); GUI (`gui/app.py:61`) doesn't. Both leak `{e}` in their generic `except Exception` branches (`cli/main.py:140-141`, `gui/app.py:64-65`). |

## Agents

| ID | Task | Priority | Status | Files | Acceptance criteria | Notes |
|----|------|----------|--------|-------|----------------------|-------|
| AG-1 | WebAgent reliability: fallback chain across search engines, retry w/ backoff, shared timeout budget, cache inside the (future) session store, explicit "web search unavailable" result instead of silent empty list. | P1 | Open | `core/agents/web_agent.py:41-45` | Simulated failure of the primary engine still returns a result via the next engine in the chain within the shared timeout budget; total engine outage returns one explicit "web search unavailable" Finding, never an empty silent list. | Current code: bare try/except per engine, only a package-import fallback (`ddgs` vs `duckduckgo_search`), no provider fallback, no retry/backoff. |
| AG-2 | PhoneAgent / PeopleSearchAgent: explicit "no source configured" status surfaced in the briefing (not just 0 findings). Keep lawful structured lookups only (phonenumbers parsing, carrier/region) — no data-broker/people-search scraping. | P1 | Open | `core/agents/phone_agent.py`, `core/agents/people_search_agent.py`, `core/analyzers/profile_synthesizer.py` | Briefing explicitly states "no phone-intelligence source configured" / "no people-search source configured" when these agents return nothing, distinguishable from "searched, found nothing." | Both agents already comply with the no-data-broker rule (PhoneAgent: `phonenumbers` only; PeopleSearchAgent: explicit wayback-only stub) — this task is about surfacing status, not adding sources. |
| AG-3 | Per-agent offline/failure-path tests for the 8 currently-untested agents (Username, Domain, SocialMedia, GitHub, Web, Breach, Image, PeopleSearch). | P1 | Open | new tests under `tests/` | Each of the 8 agents has at least one test exercising a simulated failure/timeout path with zero real network calls (enforced by TS-1's socket-blocking fixture). | Only EmailAgent, PhoneAgent, and generic orchestrator isolation are tested today (`tests/test_agents.py`). |

## LLM / Analysis

| ID | Task | Priority | Status | Files | Acceptance criteria | Notes |
|----|------|----------|--------|-------|----------------------|-------|
| LA-1 | Set `num_ctx` explicitly (start 8192, measure/adjust) on every Ollama call. | P1 | Open | `core/llm/ollama_client.py:61,89,98,114,118,132` | All 5 call sites pass `options={"num_ctx": ...}` (or equivalent); no call relies on Ollama's default. | Zero `num_ctx` hits repo-wide today. |
| LA-2 | Wire `entity_resolver.dedupe_findings()` into `profile_synthesizer.synthesize()`; add per-agent token budgets and priority ranking before the single LLM narrative call (no multi-pass LLM summarization). | P1 | Open | `core/analyzers/profile_synthesizer.py:175-231`, `core/analyzers/entity_resolver.py:8-20` | 10x-normal-data fixture (see LA-4) produces a briefing with no truncation artifacts and a bounded payload size; dedupe collapses known-duplicate findings before the LLM sees them. | `dedupe_findings` exists but is orphaned — never called. Current reduction is a flat `content[:500]` char clip only. |
| LA-3 | Add persistent evidence ID to `Finding` and propagate through entity_resolver / relationship_mapper / timeline_builder / profile_synthesizer / chat, so every briefing claim and chat citation maps back to a source. Chat retrieves top-k relevant evidence per question instead of resending the whole briefing. | P1 | Open | `core/models/schema.py:52-60`, `core/analyzers/*.py`, `core/llm/ollama_client.py:98-112`, `cli/main.py:212` | Every `Finding` has a stable `id`. A test asserts a sampled briefing claim's cited evidence ID resolves back to the originating raw Finding. Chat context size per turn is bounded (top-k), not `briefing.model_dump()` in full. | `Finding` has no `id` field today; chat sends the entire briefing JSON every turn. |
| LA-4 | Context-window fixture test: 10x-normal-data input still yields a briefing with no truncation and every claim traceable to an evidence ID. | P1 | Open | new test, likely `tests/test_synthesizer.py` | Test passes with synthetic 10x fixture; asserts no silent truncation and 100% evidence-ID traceability. | Depends on LA-2 and LA-3 landing first. |
| LA-5 | Confirm chat persona stays third-person-analyst, never role-plays as the subject; add a regression test. | P2 | Open | `core/llm/prompts.py:35-41` | Test/prompt asserts system prompt enforces third-person analyst framing; spot-check chat output never uses first-person-as-subject phrasing. | Already correct today (`CHAT_SYSTEM`) — this task is locking it in with a test, not fixing a bug. |

## CLI / UX

| ID | Task | Priority | Status | Files | Acceptance criteria | Notes |
|----|------|----------|--------|-------|----------------------|-------|
| UX-1 | Detective-themed CLI (Epic UX-1): splash card + "Press any key to open a new case", Case File / Operatives / Deductions / Consulting Room / Watson / Evidence / Certainty vocabulary, parchment-sepia + deep-green palette on dark terminal, no emojis, box-drawing frames, wax-seal divider, skippable typewriter reveal (`--fast` disables), live Evidence Board (Dispatched/Reporting/Returned/No Trail/Failed per operative, driven by real events), Briefing view (Case Summary, Key Deductions, Timeline, Connections, Gaps in the Record — each with evidence IDs + certainty), `221B >` chat prompt with `/evidence /timeline /export /done`, `--plain` for no-color/piped output. | P1 | Open | `cli/main.py`, `core/utils/branding.py`, new theming module | Manual walkthrough at 80 columns matches the themed spec; `--plain` produces clean piped output; `--fast` skips animation; Evidence Board states driven by real orchestrator events (see RL-2), not simulated timers. | Depends on CF-2/CF-3 (keypress + N/Q loop) and LA-3 (evidence IDs) to be meaningful. |

## GUI

| ID | Task | Priority | Status | Files | Acceptance criteria | Notes |
|----|------|----------|--------|-------|----------------------|-------|
| GU-1 | GUI parity with CLI flow: one start action, chat, new/end — using the same session store and purge path as CLI. | P2 | Open | `gui/app.py`, `gui/components/*` | Streamlit "End session & wipe data" and a new "Start new case" action both route through the same session-store purge/reset used by CLI's `[N]`/`[Q]`; verified by a shared test helper, not duplicated logic. | Today GUI has its own one-shot purge button (`gui/app.py:67-78`), separate code path from CLI's `_chat_loop`. |

## Sessions / Privacy

| ID | Task | Priority | Status | Files | Acceptance criteria | Notes |
|----|------|----------|--------|-------|----------------------|-------|
| SP-1 | Session store redesign: RAM-first by default; disk-backed only via a per-session temp directory encrypted with a random in-memory key (crypto-shred). Replace fixed-path JSON `session_manager.py` + sqlite `cache_manager.py`/`database.py` with this design. | P0 | Done | new `core/memory/session_store.py` (`SessionStore`); removed `session_manager.py`, `cache_manager.py`, `database.py`; updated `cli/main.py`, `gui/app.py` | No session or cache data exists in plaintext on disk at any point during a run; killing the process mid-run and inspecting disk finds only encrypted bytes (if anything). | `SessionRecord` (target/briefing/chat) now lives only in an in-process dict; the only disk writes are `cache_get`/`cache_put`, Fernet-encrypted with a key generated in `new_session()` and held only in memory, under a per-session `tempfile.mkdtemp()` dir. `aiosqlite` dropped from requirements.txt (no longer used by anything — flagged for TD-2); added `cryptography>=42.0.0`. Fixed a latent GUI bug found while migrating: `gui/app.py` was constructing a brand-new store instance on every Streamlit rerun and again inside the purge button, so in the old design purge only "worked" by accident (shared fixed-path files); now a single `SessionStore` lives in `st.session_state`. Removed CLI's `list`/`show` commands — they browsed sessions persisted across process restarts, which is exactly the plaintext-retention pattern this task eliminates; see Decisions Needed. |
| SP-2 | On `[N]`/`[Q]`/crash-free exit: drop key, delete temp dir, drop references, `gc.collect()`. On every launch, sweep and delete leftover session dirs from crashed runs. | P0 | Done | `core/memory/session_store.py` (`purge_session`, `purge_all_sessions`, `_atexit_purge`, `sweep_stale_sessions`) | Test simulates a crashed leftover session dir; next launch removes it before starting. Normal exit leaves zero session artifacts on disk. | `purge_session`/`purge_all_sessions` drop the record, delete the temp dir, drop the Fernet key, `gc.collect()`. `atexit` hook covers crash-free exit without an explicit purge (confirmed live: ran `investigate --no-chat`, which skips the chat/purge path entirely, and the temp dir was still gone after the process exited). `sweep_stale_sessions()` wired into `cli/main.py` module load and `gui/app.py` first-run. 6 tests in rewritten `tests/test_session_purge.py`, incl. a plaintext-scan test and a stale-dir sweep test. |
| SP-3 | Redact/hash all identifiers (email, username, phone, name, domain) in every logger call; `alpha_tracer.log` must contain zero subject data. | P0 | Done | `core/utils/validators.py` (`redact`), `core/agents/web_agent.py:45`, `core/agents/social_media_agent.py:113`, `core/agents/username_agent.py:62,66`, `core/agents/github_agent.py:73`, `tests/test_logging_redaction.py` | Grep of a full run's log output for any raw identifier substring used as input returns zero hits. | Fixed all 5 leak sites (the 4 originally audited + `github_agent.py:73`'s `email_search`/`name_search` `val`, found while patching — audit had missed it). Added `validators.redact()` (generic identifier mask, routes emails through existing `mask_email`). 5 new tests in `tests/test_logging_redaction.py`, all passing; full suite 16/16 passing. |
| SP-4 | README: honest privacy-limits section (swap files, SSD wear leveling, Python memory semantics — no guarantees Python can't deliver). | P1 | Open | `README.md` | Section reviewed and confirmed to make no false "unrecoverable" claims. | Ties to DP-1. |
| SP-5 | `/export`: only path data leaves the session, only on explicit request, to a user-chosen path. | P2 | Open | `cli/main.py`, new export module | `/export` writes exactly the briefing (and nothing else) to a path the user supplies; no auto-export anywhere else in the app. | Not yet implemented. |

## Reliability

| ID | Task | Priority | Status | Files | Acceptance criteria | Notes |
|----|------|----------|--------|-------|----------------------|-------|
| RL-1 | All user-facing errors (Ollama down/missing model, agent timeout/failure) are themed-but-honest: state real cause + real fix, never a raw traceback. | P1 | Open | `cli/main.py`, `gui/app.py`, `core/agents/base_agent.py` | Manual test: kill Ollama mid-run, kill network mid-agent-run — user sees a themed one-line message with the actual cause and fix, never a Python traceback. | Partially true today for Ollama (CF-4 covers the gaps); agent timeouts already isolated by orchestrator (`orchestrator.py:28-31`) but not yet themed. |
| RL-2 | Progress display driven by real agent completion events (Dispatched/Reporting/Returned/No Trail/Failed), not simulated/timed progress bars. | P1 | Open | `core/agents/orchestrator.py`, `cli/main.py` | Evidence Board / progress UI updates only on real orchestrator events (agent start, finish, timeout, error) — no `time.sleep`-driven fake progress. | Needed before UX-1's Evidence Board can be "driven by real events" as specced. |

## Testing

| ID | Task | Priority | Status | Files | Acceptance criteria | Notes |
|----|------|----------|--------|-------|----------------------|-------|
| TS-1 | Autouse pytest fixture that blocks real sockets, so the suite is verifiably fully offline. | P2 | Open | `tests/conftest.py` | A test that attempts a real HTTP/socket call fails loudly under this fixture; existing 11 tests still pass. | `tests/conftest.py` is 4 lines today (just `sys.path` setup) — no network mocking at all. |
| TS-2 | Per-agent failure-path tests for the 8 untested agents (tracked as AG-3 — duplicate cross-reference). | P1 | Open | `tests/` | See AG-3. | Same acceptance criteria as AG-3; listed here for the Testing-section rollup. |
| TS-3 | Orchestrator timeout test (agent exceeds `AGENT_TIMEOUT`, orchestrator returns empty for that agent without failing the run). | P2 | Open | `tests/test_agents.py` | Test simulates a slow agent exceeding timeout; asserts orchestrator continues and returns other agents' findings. | `Orchestrator.run_all` already has timeout logic (`orchestrator.py:28-31`) but no dedicated test for the timeout branch itself (only error-isolation is tested). |
| TS-4 | Purge-on-end test: session dir, cache, and logs are verifiably empty/gone after `[N]`/`[Q]`. | P0 | Done | `tests/test_session_purge.py` | Test asserts zero files remain in the session temp dir and zero identifier strings remain in any log after purge. | Rewritten for `SessionStore`: in-memory purge, encrypted-cache-dir purge, plaintext-scan (asserts no raw identifier bytes anywhere under the temp base dir even before purge, since the cache is encrypted from the moment it's written), and crash-dir sweep. Still need an end-to-end test wired through `[N]`/`[Q]` itself once CF-3 lands — tracked there. |
| TS-5 | Context-window fixture test (duplicate cross-reference to LA-4). | P1 | Open | `tests/` | See LA-4. | — |
| TS-6 | Evidence-ID traceability test (duplicate cross-reference to LA-3). | P1 | Open | `tests/` | See LA-3. | — |

## Docs / Packaging

| ID | Task | Priority | Status | Files | Acceptance criteria | Notes |
|----|------|----------|--------|-------|----------------------|-------|
| DP-1 | README quick start (clone → run → press a key), troubleshooting section, honest privacy limits (see SP-4), intended-use statement (security research, journalism, due-diligence-with-consent; explicitly not stalking/harassment). | P1 | Open | `README.md` | README reviewed end-to-end against the actual launcher/keypress/purge behavior once CF-1/CF-2/CF-3/SP-1 land; no doc claims a capability the code doesn't have. | Current README (README.md:17-51) documents the old manual setup — will need a full rewrite once the launcher lands. |

## Tech Debt

| ID | Task | Priority | Status | Files | Acceptance criteria | Notes |
|----|------|----------|--------|-------|----------------------|-------|
| TD-1 | Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` everywhere; keep suite warning-free. | P1 | Done | `core/models/schema.py:60,81,94,95`; `core/agents/base_agent.py:24` | `python -m pytest -q` runs with zero `DeprecationWarning` for `utcnow`. | 4 of the original 8 sites disappeared when `session_manager.py` was deleted (SP-1); remaining 5 fixed (`Field(default_factory=lambda: datetime.now(timezone.utc))` for the pydantic defaults, since `default_factory` needs a zero-arg callable). `python -m pytest -q` → 20 passed, 0 warnings. |
| TD-2 | Remove unused dependencies from `requirements.txt` (no matching import found anywhere in `core/`, `cli/`, `gui/`, `config/`). | P2 | Open | `requirements.txt` | `pip-audit`-style import-vs-requirement check (manual or scripted) shows every remaining requirement is actually imported/used. | Candidates found unused: `cloudscraper`, `playwright`, `selenium`, `snscrape`, `ipwhois`, `email-validator`, `piexif`, `reportlab`, `aiohttp`, `tqdm`, `beautifulsoup4`/`lxml`. `aiosqlite` joined this list when SP-1 removed its only two callers (`cache_manager.py`, `database.py`) — already deleted from requirements.txt as part of SP-1 since it's unambiguously dead (nothing else ever imported it). Verify the rest before removing — some (e.g. `playwright`) may be intentionally reserved for a not-yet-wired feature; confirm with user if unsure (see Decisions Needed). |

---

## Decisions Needed

- **CLI `list`/`show` commands removed (SP-1):** these browsed sessions saved across process restarts — incompatible with the RAM-first, nothing-persists design (a fresh process now starts with zero sessions in memory, so they'd always show empty). Removed rather than left as dead/misleading UI. If per-run history browsing is wanted back, it needs an explicit design (e.g. `/export` per SP-5, never silent persistence) — flag if this is actually wanted.
- **TD-2 scope:** some "unused" deps (e.g. `playwright`, listed in README's optional LinkedIn-scraping setup step) may be intentionally reserved for a feature not yet wired up rather than truly dead. Need confirmation per-package before deleting from `requirements.txt`.
- **CF-4 fix text:** should the GUI's Ollama-down fix message be OS-aware, or is a single cross-platform `ollama serve &`-style line (with a note for Windows users) acceptable?
- **LA-1 num_ctx value:** starting at 8192 per spec; exact production value needs real measurement against typical finding-set sizes once LA-2/LA-3 land.
- **Additional phone/people-search sources:** spec forbids data-broker/people-search-site scraping (AG-2). No lawful alternative source has been identified yet; this stays open only if the user has a specific lawful source in mind.

---

## Changelog

*(newest first)*

- **2026-09-29** — SP-1/SP-2/TS-4/TD-1: session store redesign. New `core/memory/session_store.py::SessionStore` — RAM-first records, Fernet-encrypted per-session temp-dir cache, crypto-shred purge (`gc.collect()`), `atexit` crash-free-exit cleanup, `sweep_stale_sessions()` for crashed-run leftovers. Deleted `session_manager.py`/`cache_manager.py`/`database.py` (plaintext JSON + sqlite). Fixed a latent GUI bug (new store instance per Streamlit rerun) found during migration. Removed CLI `list`/`show` (incompatible with RAM-first — see Decisions Needed). Also closed out TD-1 (`datetime.utcnow()` → `datetime.now(timezone.utc)`, all 8 sites — 4 vanished with the deleted files). `python -m pytest -q` → 20 passed, 0 warnings. Manually smoke-tested `python main.py cli investigate --name "Test Person" --no-chat`: ran clean, log line showed a redacted handle (`t********n`), no `data/sessions/*.json` written, temp dir gone after exit via the atexit hook even though `--no-chat` skips the explicit purge path.
- **2026-09-29** — SP-3: redacted all subject identifiers from logger calls (5 sites, incl. one — `github_agent.py` — found beyond the original audit). Added `validators.redact()` + 5 regression tests. 16/16 tests passing.
- **2026-09-29** — P0.2: Scrubbed the real third-party email (`sankardasdevadas2004@gmail.com`) from `alpha_tracer.log` (deleted, recreated empty), `data/sessions/*.json` (deleted, 3 files), `README.md` (2 lines), `tests/test_agents.py` (3 assertions), `tests/test_email_flow.py` (1 fixture constant) — replaced with synthetic fixture identity `jamiecarter2004@gmail.com` / "Jamie Carter" everywhere a test needed a realistic email+name pair. Verified: repo-wide grep for the real local-part returns zero hits; `python -m pytest -q` → 11 passed.
- **2026-09-29** — P0.1: `git init`, added `.gitignore` (`.venv/`, `data/`, `*.log`, `.env`, `__pycache__/`, `.pytest_cache/`, session temp dirs), first commit of existing codebase (post-scrub, so no PII ever entered git history).
- **2026-09-29** — Full codebase audit completed (3 parallel Explore agents: launcher/keypress/UX, sessions/privacy/logging, LLM/agents/tests/deps); CASEBOOK.md created and seeded with every finding.
