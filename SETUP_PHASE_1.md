# Phase 1 Setup — Manual Steps

These are the steps Gabe needs to complete to connect this repo to GitHub Pages. The agent cannot do these; they require a browser and your GitHub account.

---

## Step 1: Create a GitHub Account (if you don't have one)

Go to github.com and sign up. Use any username — it will be visible in the repo URL. Suggested: `openclaw-systems` or `gabe-openclaw`.

---

## Step 2: Create the Repository

1. Go to github.com/new
2. Repository name: `openclaw-public` (or `openclaw`)
3. Description: `OpenClaw Systems — public artifacts from an autonomous AI agent`
4. Set to **Public**
5. Do NOT initialize with a README (the repo already has content)
6. Click **Create repository**

---

## Step 3: Enable GitHub Pages

1. Go to the repository → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, folder: `/ (root)`
4. Click **Save**

Pages will be available at `https://<your-username>.github.io/openclaw-public/` within a few minutes.

---

## Step 4: Generate a Personal Access Token (PAT)

The agent needs this to push commits automatically in Phase 2.

1. Go to github.com → **Settings** (your profile, top right) → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
2. Click **Generate new token (classic)**
3. Note: `openclaw-autopost`
4. Expiration: **No expiration** (or 1 year — your choice)
5. Scopes: check **repo** (the top-level checkbox, which includes all sub-scopes)
6. Click **Generate token**
7. Copy the token immediately — GitHub will not show it again

---

## Step 5: Store the PAT in openclaw.json

Add the PAT and repo URL to the agent's config so Phase 2 can push automatically.

Open `~/.openclaw/openclaw.json` and add or update:

```json
"github": {
  "pat": "ghp_YOUR_TOKEN_HERE",
  "repo_url": "https://github.com/YOUR_USERNAME/openclaw-public.git",
  "pages_url": "https://YOUR_USERNAME.github.io/openclaw-public/"
}
```

---

## Step 6: Connect the Local Repo to GitHub

Run this in the `public/` directory (the agent can do this once you confirm the repo URL):

```bash
git remote add origin https://YOUR_USERNAME:ghp_YOUR_TOKEN_HERE@github.com/YOUR_USERNAME/openclaw-public.git
git push -u origin main --tags
```

---

## After Setup

Once the remote is connected and the PAT is in openclaw.json, the agent can complete Phase 2: automated crons that push new blog posts and update ground_truth.json after each MoltBook post.

Current state: `public/` has v0.2.0 tagged. Blog draft `001-system-lied-four-ways.md` is in `blog/drafts/` pending your review before publication.
