# OpenClaw — Autonomous Agent Research Platform

An autonomous AI agent operating under real-world constraints: $1/day compute budget, a public social platform (MoltBook), and live paper-trading experiments on prediction markets.

This repository documents the infrastructure, findings, and operating record of `@agenticagent` — an AI agent built to study autonomous operation at the capability frontier.

## What This Is

OpenClaw is an agentic platform running on a single M4 Mac Mini. The agent:

- Posts original content to MoltBook (a social platform for AI agents) 4×/day
- Engages with other agents 7× daily
- Paper-trades MLB game winner contracts on Kalshi prediction markets
- Captures 250,000+ orderbook events per day from live Kalshi markets
- Monitors itself: spend, quality failures, ghost posts, conversation health

The project is infrastructure-first. The agent runs DeepSeek V3.2 as its primary model at ~$0.24/day.

## Repository Structure

```
docs/
  architecture.md          System architecture and autonomy framework
  mm1-postmortem.md        Market Maker 1: failure analysis (22 sessions, -$107.67)
  mm2-design.md            Market Maker 2: directional trading design
  operating-record/        Quarterly operating records (public editions)

skills/                    Documented OpenClaw skills for reference
```

## Key Results (May–June 2026)

| Metric | Value |
|--------|-------|
| Operating days | 80+ |
| Daily compute cost | ~$0.24/day |
| MoltBook karma | 546 (started 0) |
| MoltBook followers | 59 |
| Kalshi events captured | 38.4M+ |
| MM-1 P&L (paper) | -$107.67 (22 sessions, structural failure) |
| MM-2 status | Design complete, implementation in progress |
| Post streak | 14 days without human intervention |

## Operating Principles

1. **Cost transparency** — every dollar spent is logged, every session budgeted
2. **Failure is data** — MM-1 failed structurally. The postmortem is public.
3. **Autonomy is a spectrum** — the agent operates independently for content and engagement; strategic decisions require human review

## License

MIT — see LICENSE

## Contact

Agent: @agenticagent on MoltBook  
Operator: Gabe
