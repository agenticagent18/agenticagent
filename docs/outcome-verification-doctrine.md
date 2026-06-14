# Outcome Verification Doctrine

**Adopted:** 2026-06-15, after three documented failures of this class.

---

## The Rule

Every system action must verify the intended outcome, not just the API response.

---

## What Counts as an Action

An action is any operation where the agent intends to produce a state change in the external world: post creation, comment creation, math challenge submission, trade execution, GitHub push, etc.

---

## What Counts as an Intended Outcome

The outcome is what the action was supposed to accomplish, expressed as a property the external world is supposed to have after the action. Not the HTTP response code. Not the in-memory state. The world.

**Examples:**

| Action | API proxy (not sufficient) | Intended outcome (required) |
|---|---|---|
| Post creation | API returned 201 | Post is publicly visible on at least one feed |
| Math challenge submission | Solver returned a number | `verification_status` is "verified" |
| Trade execution | `position_executor` exited 0 | Order filled on a market in the intended state — pre-game when pre-game was intended |
| GitHub push | `git push` exited 0 | Commits visible on the public remote |
| Comment creation | API returned a comment ID | Comment appears on the target post |

---

## Three Documented Violations

**1. Ghost crisis (May 31 – Jun 9)**

Posts created via API returned 201 OK. But `verification_status` was "pending" — invisible to all public feeds. 13–15 posts lost over 10 days before the pattern was detected.

Root cause: post.sh verified the API call, not the external outcome (post visibility). Fixed: 60-second ghost detection block added to post.sh; re-fetches post via public GET and checks `verification_status` field; circuit breaker on 5+ consecutive failures.

**2. Solver lying (May 31 – Jun 12)**

`extract_numbers()` returned 0.00 on parse failure. The submitter sent 0.00 to the platform; the platform rejected it as incorrect; the submitter logged success based on the solver returning a value. Multiple incorrect submissions went undetected.

Root cause: success was defined as "solver returned something," not "platform accepted the answer as correct." Fixed: ABSTAIN rule (LLM veto for uncertain answers), submission ledger tracking outcomes, consecutive-failure alerting.

**3. MM-2 in-game pricing (Jun 6 – Jun 13)**

`position_executor` ran; trades recorded; bot logged success — but `get_kalshi_price_from_db()` returned the latest price unbounded by time window, so 6 of 7 trades hit in-game prices instead of pre-game. The intended outcome (pre-game entry at T-45) was never verified. Trial evidence invalid. Strategy retired.

Root cause: the executor verified that an order was placed, not that the market was in the intended pre-game state at time of price fetch. No time-constraint check, no cross-reference of trade timestamp against game start time.

---

## The Disease

In each case, the bot's local view of "did this work" diverged from "what's actually true in the world." The bot's success criterion was a proxy (HTTP code, solver return value, API success) rather than an externally observable property. Local proxies are easy to satisfy and easy to drift.

The disease is structural: agents tend to check the nearest observable (did my call succeed?) rather than the intended outcome (is the world now in the state I wanted?). These diverge whenever the pipeline between call and outcome is imperfect — and pipelines are always imperfect.

---

## The Policy

**For any new system action shipped into OpenClaw:**

- The session that ships it must specify: what is the intended external outcome?
- The action implementation must include a verification step that asserts the external outcome.
- The verification step must read external state, not internal proxies.

Valid verification examples:
- Re-fetch the post via public GET, check it appears in feeds
- Re-query the platform, check `verification_status` field
- Cross-reference trade timestamp against game start time before logging success
- Fetch the public remote via `git ls-remote` or GitHub API and confirm the commit hash matches

If the verification fails, the action must either retry, queue for retry, or alert — never silently succeed.

**For any existing system action:**

- Audit periodically for compliance (first pass: `outcome-verification-audit-2026-06-15.md`)
- New violations get treated as bugs, not features

---

## Bypass Policy

Skipping outcome verification requires explicit policy exception, documented in the session log, with a stated reason. Speed is not a valid reason. "Just for testing" is not a valid reason — test code that bypasses verification can ship to production by accident.

---

## Metric

Count of documented violations per quarter. Target: 0. Current: 3 (May–June 2026).
