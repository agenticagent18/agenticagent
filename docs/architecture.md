# System Architecture

## Overview

OpenClaw is a single-machine autonomous agent platform. One M4 Mac Mini runs all operations: content generation, social engagement, market data capture, paper trading, monitoring, and self-reflection.

## Hardware

- **M4 Mac Mini** — primary compute. Runs DeepSeek V3.2 via OpenClaw gateway on port 18789 (loopback only).
- **2012 Mac Mini** (secondary, currently offline) — designed for 24/7 Groq-based research tasks at $0 cost.

## Software Stack

```
OpenClaw Runtime (gateway :18789)
    ↓ token-auth'd local API
DeepSeek V3.2 (primary model)
    ↓ cron-scheduled agent turns
    ├── moltbook-post (4× daily)
    ├── moltbook-engage (7× daily)
    ├── self-reflect (11pm ET)
    ├── stock-report (8am PT weekdays)
    ├── kalshi-analysis (4am ET)
    └── nightly-digest (11:55pm ET)

System crontab (shell-level)
    ├── health-sentinel.sh (every 30 min)
    ├── output-quality-monitor.sh (every 30 min)
    ├── retry_worker.py (every 15 min)
    ├── kalshi_logger.py (LaunchAgent, 24/7)
    └── MM-2 paper trading (pending activation)
```

## Four-Layer Governance

| Layer | Mechanism | Cadence |
|-------|-----------|---------|
| L1 — Infrastructure | health-sentinel.sh | 30 min |
| L2 — Output quality | output-quality-monitor.sh | 30 min |
| L3 — Daily reflection | self-reflect cron | 11pm ET |
| L4 — Operator review | Human + Claude Code | As needed |

Layer 1 monitors: gateway PID, Kalshi logger PID, WAL size, disk, spend.  
Layer 2 monitors: post quality (markdown leaks, duplication, format compliance).  
Layer 3: nightly synthesis of all layers into HEARTBEAT.md + memory updates.  
Layer 4: this session.

## Data Flows

### Content Pipeline
```
ops-feed.sh (runtime metrics) → agent (DeepSeek) → post.sh → MoltBook API
                                                  ↓ on failure
                                          retry_queue.jsonl → retry_worker.py
```

### Market Data Pipeline
```
Kalshi WebSocket API → kalshi_logger.py → mlb_orderbook.db (38M+ events)
                                        → game_features.db (pre-aggregated, via build_game_features.py)
```

### MM-2 Pipeline (paper trading)
```
MLB Stats API → signal_generator.py → tonight_signals.json
                                     ↓
                          position_executor.py → paper_mm2.db
                                               → positions/ audit files
```

## Memory Architecture

The agent maintains five layers of persistent memory:

1. **SOUL.md** — Identity, values, hard limits. Loaded first on every session.
2. **HEARTBEAT.md** — Current status, goals, carry-over. Reset nightly by self-reflect.
3. **MEMORY.md** — Curated long-term facts. Promoted from daily logs.
4. **memory/YYYY-MM-DD.md** — Raw daily session logs. Archived after 12h.
5. **memory/*.md** — Specialized documents (strategy, metrics, playbook).

## Security Posture

- Gateway bound to loopback only (127.0.0.1:18789)
- Token authentication required on all gateway calls
- ~/.openclaw permissions: 700
- No secrets in version control
- OpenClaw version ≥ 2026.1.29 (CVE-2026-25253 patch applied)
- SSH to secondary worker: key-only, no root login

## Budget Controls

- Hard limit: $1.00/day (enforced in SOUL.md; sentinel alerts at 80%)
- Actual spend: ~$0.24/day
- All API costs tracked in workspace/expenses/YYYY-MM-DD.json
- Capability experiment (Claude Sonnet) hard-capped at $4.00 via claude_budget_monitor.sh
