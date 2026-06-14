# Security Policy — Public Repo

This document describes the mechanical controls that prevent sensitive content from entering the public git history.

## What Gets Scanned

Two hooks run automatically. Both check the same pattern list.

### Pre-commit hook (`scripts/git-hooks/pre-commit`)

Runs on every `git commit`. Scans staged files only (the index, not the working tree). Blocks the commit if any pattern matches.

**Patterns blocked:**

| Category | Examples |
|---|---|
| API keys | `sk-...`, `ghp_...`, `github_pat_...`, `gsk_...`, `AIza...`, `moltbook_sk_...`, AWS AKIA keys, Slack xox tokens |
| Auth tokens | `Bearer ...`, JWT (`eyJ...`) |
| Hardcoded env secrets | `DEEPSEEK_API_KEY = "..."`, `GITHUB_PAT = "..."`, and similar |
| Password assignments | `password = "..."` |
| Phone numbers | E.164 format (`+1...`), US format `(NXX) NXX-XXXX` |
| Internal infrastructure | `10.0.0.5` (worker machine), `192.168.x.x`, `172.16-31.x.x` |
| Name blacklist | `Glass` (incorrect last name — should never appear) |

### Pre-push hook (`scripts/git-hooks/pre-push`)

Runs on every `git push`. Scans all commits in the push range (`origin/main..HEAD`) that the remote doesn't have yet. This is the second layer: if a bad commit somehow landed locally (e.g., `--no-verify` was used), the pre-push hook catches it before it reaches GitHub.

## Extensible Pattern File

Add custom patterns to `.gitignore-secrets` in the repo root (one ERE pattern per line, `#` for comments). Both hooks load this file automatically.

Example:
```
# Block internal hostnames
internal\.company\.net
# Block specific account numbers
ACC-[0-9]{8}
```

## Bypass Policy

Bypassing requires explicit sign-off:

1. **Pre-commit bypass:** `git commit --no-verify`
2. **Pre-push bypass:** `git push --no-verify`

Either bypass requires sending an iMessage to the operator explaining the reason before proceeding. Undocumented bypasses are a policy violation.

## Setting Up Hooks After Clone

Hooks live in `scripts/git-hooks/` (versioned) and are symlinked into `.git/hooks/` by the install script. After cloning:

```bash
bash scripts/install-hooks.sh
```

This symlinks `pre-commit` and `pre-push`. If `.git/hooks/pre-commit` already exists, it is backed up to `.git/hooks/pre-commit.bak` before replacement.

## Historical Note

A one-time manual secrets scan was run on the full commit history on 2026-06-13 before the first public push. Findings: no credentials, API keys, or phone numbers in any commit. Two deleted files remain accessible in history (a fabricated blog draft and two Substack outlines from the bootstrap phase); neither contains sensitive data.

If a secret is ever found in history, the remediation path is `git-filter-repo` to rewrite history, followed by a force push and immediate credential rotation.
