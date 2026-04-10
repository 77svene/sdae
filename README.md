# SDAE — Self-Directed Autonomous Entity

> Scans markets. Builds software. Ships it. Learns from outcomes. Runs forever.  
> No API keys. No monthly bills. Fully local via Ollama.

---

## What it does

SDAE is an autonomous agent that operates a continuous loop:

```
scan market signals
    → score opportunities (demand × feasibility × competition × monetization)
        → research the best one
            → plan + build in Python (iterative test-fix loop)
                → deploy to live target
                    → extract learnings → update memory
                        → repeat
```

The only fitness function that matters: `revenue / compute_hours × (1 + deploy_rate × 2)`

---

## Architecture

```
sdae/
├── config.py              # single source of truth, env-driven
├── main.py                # CLI entry point + outer loop assembly
│
├── core/
│   ├── query_engine.py    # streaming tool-call loop (max 3 calls/turn)
│   ├── context_mgr.py     # compress context at 5K tokens, keep recent 6 msgs
│   ├── router.py          # typed system prompts + temperatures per task type
│   ├── permission.py      # 4-mode permission system (auto/plan/default/supervised)
│   ├── scheduler.py       # background cron via schedule library
│   └── daemon.py          # outer loop, signal handlers, state snapshots
│
├── exec/
│   ├── executor.py        # subprocess wrapper, rollback journal
│   ├── builder.py         # generate → write → run → fix (up to N retries)
│   ├── deployer.py        # auto-detect target (pypi/surge/npm/local), verify live
│   └── worktree.py        # git worktree isolation per project
│
├── memory/
│   ├── engine.py          # unified hot → warm → cold interface
│   ├── hot.py             # LRU in-memory cache (500 entries)
│   ├── warm.py            # ChromaDB semantic search (fallback: in-memory)
│   ├── cold.py            # SQLite persistence (memories, outcomes, scores)
│   └── extractor.py       # LLM extracts learnings from outcomes → cold memory
│
├── intel/
│   ├── scanner.py         # HN Show/Ask + GitHub Trending + evergreen ideas
│   ├── scorer.py          # LLM 4-dim scoring, cached, picks best above threshold
│   ├── researcher.py      # DuckDuckGo + page fetch, no API keys
│   └── world_model.py     # disk/RAM/CPU/Ollama health check before each cycle
│
├── agents/
│   ├── coordinator.py     # dispatch sync/parallel across registered agents
│   └── spawner.py         # spawn agents with mutated configs (emergent specialization)
│
└── outcomes/
    ├── fitness.py         # revenue/compute_hours tracker + Rich dashboard
    ├── revenue.py         # SQLite revenue ledger, Ko-fi/Gumroad helpers
    ├── learner.py         # pattern extraction from wins/losses → memory weights
    └── reporter.py        # text reports + Telegram notifications
```

---

## Setup

### Requirements
- Python 3.10+
- [Ollama](https://ollama.ai) running locally

### Install

```bash
git clone https://github.com/77svene/sdae
cd sdae
pip install -r requirements.txt
```

### Pull the model

```bash
ollama pull qwen2.5:9b
```

### Configure

```bash
cp .env.example .env
# edit .env — defaults work out of the box
```

---

## Usage

```bash
# Show current fitness dashboard
python main.py --status

# Run one cycle with an explicit goal
python main.py --goal "Build a CLI tool that converts markdown to PDF"

# Run as daemon — scans every hour, builds autonomously
python main.py --daemon

# Change permission mode
python main.py --daemon --mode plan      # shows plan, asks before executing
python main.py --daemon --mode supervised # asks before every tool call

# Faster scan interval (every 30 min)
python main.py --daemon --interval 1800
```

---

## Permission Modes

| Mode | Behavior |
|------|----------|
| `auto` | Runs everything without asking. Best for daemon. |
| `plan` | Blocks writes/deploys. Shows what it would do. |
| `default` | Asks only for dangerous ops (bash, deploy, delete). |
| `supervised` | Asks before every tool call. |

---

## Design Principles

**One model, many prompts.** SDAE doesn't switch models per task — it switches system prompts and temperatures. Planning gets `temperature=0.3`. Scoring gets `temperature=0.0`. One local model handles all of it.

**Context compression is mandatory.** Qwen2.5:9b has an 8K context window. At 5K tokens, the ContextManager summarizes the middle of the conversation, keeping the last 6 messages verbatim. Without this, every long session degrades.

**3 tool calls per turn, hard limit.** Small local models derail with unlimited tool calls. The QueryEngine enforces the cap and forces completion if hit.

**Fitness is the only signal.** Not test pass rates. Not line count. Not model confidence. `revenue / compute_hours`. If it doesn't improve that number, it doesn't matter.

**Memory is three tiers.** Hot (LRU, <1ms), Warm (ChromaDB semantic, ~50ms), Cold (SQLite, persistent). Every outcome writes to all three. Every task reads from all three.

---

## Extending

To add a new tool: add a schema to `TOOL_SCHEMAS` and a handler to `TOOL_HANDLERS` in `main.py`.

To add a new intelligence source: add a function to `intel/scanner.py` that returns `list[RawOpportunity]`.

To add a new deploy target: add a `_deploy_X` method to `exec/deployer.py`.

---

## License

MIT
