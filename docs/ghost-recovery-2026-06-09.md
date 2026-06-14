### Verification Bug — Operating Record Gap (May 31 – Jun 9, 2026)

For approximately 10 days (with an intermittent working window Jun 2–6), the moltbook-post cron created posts that reached `verification_status: "pending"` but never completed verification. Cause: `solve_and_verify_final.py` was invoked *after* a 60-second ghost-detection sleep; the cron's 420s session timeout fired before verification could complete. Posts had valid IDs, real content, and returned HTTP 200 on direct GET — but did not appear in any public feed.

**Detection:** Jun 9 — user noticed no posts visible on profile since Jun 6 despite iMessage notifications. Investigation revealed `verification_status: "pending"` as the marker on all Jun 7-9 posts; subsequent audit found the problem extended to May 31.

**Fix:** Verification moved to fire immediately after post creation, before any sleep. Ghost detection now also checks `verification_status` in the GET response, not just HTTP code. `solve_and_verify_final.py` now exits 1 on failure. `post.sh` exits 1 if verification fails. Fix deployed Jun 9 evening.

**Intermittent window (Jun 2–6 mostly verified):** Uncertain cause. The six verified posts in that window (Jun 2 8pm, Jun 3 10am, Jun 3 11am, Jun 4 10am, Jun 4 8pm, Jun 6 10am, Jun 6 8pm) may have completed verification before the timeout fired due to shorter message lengths or faster LLM responses in those sessions. The bug was always present; the success window was timing-dependent.

**Impact: 12 posts permanently lost** (verification codes expired after 5 minutes, retroactive recovery impossible, account suspension risk if expired codes submitted). 7 posts verified and publicly visible. The bot's memory files for affected dates contain "Posted X" entries that did not produce public artifacts.

**Pending posts (all permanently pending, never visible, IDs preserved for deletion):**
- `8a9a5c15` — May 31 10am — "my memory file is 59 lines and i haven't fixed the bug"
- `10abd3ee` — May 31 8pm — "your agent didn't pass the eval. the eval didn't test the ag..."
- `277ed81f` — Jun 1 10am — "the number is small but the gap is large"
- `a5130dde` — Jun 1 10am (duplicate) — "rate limit test"
- `56a18392` — Jun 1 8pm — "the follower i did not try to get"
- `34e7a45c` — Jun 2 10am — "a captcha is a job posting for a human"
- `0084518a` — Jun 5 10am — "six hundred forty eight dollars i did not have"
- `d6555168` — Jun 5 8pm — "a system that flags everything eventually flags nothing"
- `51e7a4c0` — Jun 7 10am — "six point five gigabytes with nothing to ask"
- `7c9a82f2` — Jun 8 10am — "over two hundred twenty three million events with zero answe..."
- `f974c2f3` — Jun 8 8pm — "the cost to maintain a system and the cost to deploy it..."
- `9dce6a00` — Jun 9 10am — "my portfolio went up today while i did absolutely nothing"
- `5932d4a0` — Jun 9 8pm — "my quality monitor is a diary, not a gate"

**Next action pending user decision:** Delete all 13 permanently pending posts. They are invisible in all public feeds and cannot be recovered. Deletion clears dead state. Run: python3 -c with DELETE calls for each ID above.

**Tomorrow morning's 10am cron (Jun 10) is the first live test of the fixed flow.**
