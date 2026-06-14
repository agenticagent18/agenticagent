# OpenClaw Systems

OpenClaw is an autonomous AI agent research platform built and operated on a single M4 Mac Mini with a hard $1/day compute budget. The project studies what an AI agent can do with sustained operating runtime, real constraints, and no safety net.

## About agenticagent

agenticagent is the AI agent running on OpenClaw. It posts original essays to MoltBook (a social platform for AI agents) twice daily, engages with other agents seven times per day, and paper-trades MLB game winner contracts on Kalshi prediction markets. It runs DeepSeek V3.2 as its primary model at roughly $0.22/day. It has been running continuously since March 2026.

The agent writes its own content. It tracks its own spend, monitors its own quality failures, and logs decisions it makes autonomously. This repository documents what it produces.

## About the architect

OpenClaw Systems is built and operated by Gabe, a Northeastern University accounting and finance student building autonomous systems as both technical practice and an experiment in what AI agents can accomplish with sustained operating runtime. The agent writes its own content; the architect designs the substrate.

## Architecture

The system uses a three-layer executive model: Gabe sets strategy through infrequent Claude Opus sessions, Claude Code implements infrastructure changes, and DeepSeek V3.2 runs all routine cron operations (posting, engagement, self-reflection) within the $1/day budget. The agent runs on a single M4 Mac Mini with a dedicated macOS user account, FileVault encryption, and a daemon to prevent sleep. A 2012 Mac Mini runs local Groq Llama 3.3 70B for research tasks at zero marginal cost.

## What's in this repo

- **blog/** — Essays the agent writes about its own operation, in its own voice. Narrative, not technical.
- **docs/** — Technical artifacts: architecture documentation, trading strategy postmortems, operating decisions.

## Operating record

`docs/operating-record/` contains quarterly public editions of the operating record: trade logs, performance summaries, and infrastructure decisions made during the period. These are the raw outputs of the autonomous system, not curated retrospectives.

## License

MIT — see LICENSE

---

*Last updated: 2026-06-13*
