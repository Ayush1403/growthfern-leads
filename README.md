# Lead watcher (Growthfern)

Every 2 minutes it checks these sources for people hiring for work Growthfern does (websites,
web apps, UI/UX, branding, SEO, growth marketing):

- **Reddit**: new posts in r/forhire, r/hiring, r/slavelabour, r/startups, r/smallbusiness,
  r/Entrepreneur, r/marketing, r/web_design, r/SaaS (official API, or public RSS without keys)
- **Hacker News**: "Seeking freelancer" comments in the monthly freelancer thread
- **We Work Remotely**: design and full-stack job feeds (add any RSS feed via `FEEDS`)

Matches go through a keyword filter, then (optionally) Claude checks that each one is a real
fit and writes a personalized reply. New leads arrive as one email per check, each with the
link and a drafted reply. You send the reply yourself. SQLite (`leads.db`) records every post
seen, so nothing is emailed twice. On the very first live run it only records what's already
posted, so you don't get a flood of old posts.

## 1. Setup

1. Copy `.env.example` to `.env`.
2. **Email:** turn on 2-Step Verification on the sending Gmail account, create an App
   Password at https://myaccount.google.com/apppasswords, and put it in `SMTP_PASS`. Set
   `SMTP_USER` (sender) and `ALERT_EMAIL` (where leads go).
3. **Reddit (recommended):** https://www.reddit.com/prefs/apps → create app → type **script**,
   redirect `http://localhost:8080`. Put the id (under the name) and secret in `REDDIT_CLIENT_ID` /
   `REDDIT_CLIENT_SECRET`. Without it Reddit falls back to public RSS, which rate-limits hard.
4. **Claude (optional):** API key from https://console.anthropic.com in `ANTHROPIC_API_KEY`.
   Without it, every keyword match is sent with a generic template reply.

Never commit `.env`.

## 2. Run locally

```bash
uv run --python 3.12 --no-project --with-requirements requirements.txt --env-file .env leads.py
```

With `DRY_RUN=1` it prints matches instead of emailing. Set `DRY_RUN=0` to send email.

Tests:

```bash
uv run --python 3.12 --no-project --with pytest --with-requirements requirements.txt pytest -q
```

## 3. Tune

Keywords and the services blurb are at the top of `leads.py` (`HIRING`, `SERVICE_KW`, `SKIP`,
`SERVICES`). Sources: `SUBREDDITS`, `FEEDS`, `HN_QUERY`.

Replying: answer in the thread or by the contact the poster asked for. Unsolicited mass DMs
break Reddit's spam rules and Responsible Builder Policy and get accounts banned.

## 4. Deploy (always on)

One small worker process, no web port. Keep `/data` on a persistent volume so the database
survives restarts.

**GitHub Actions (free, no card):** push this folder to a **public** GitHub repo (unlimited free
minutes; private repos get 2,000/month, enough only for a check every ~30 min). Add repo secrets
`ALERT_EMAIL`, `SMTP_USER`, `SMTP_PASS` (and optionally `ANTHROPIC_API_KEY`, `REDDIT_CLIENT_ID`,
`REDDIT_CLIENT_SECRET`). `.github/workflows/leads.yml` runs one check every ~5 minutes and commits
`state/leads.db` so posts are not emailed twice. Code and the seen-post list are public; secrets are not.

**Any VPS / Oracle Cloud free tier (Docker):**

```bash
docker build -t leads .
docker run -d --restart unless-stopped --env-file .env -e DRY_RUN=0 -v leads-data:/data --name leads leads
docker logs -f leads
```

**Railway:** New project → deploy from repo (uses the Dockerfile) → add the env vars → add
a Volume mounted at `/data`.

**Fly.io:**

```bash
fly launch --no-deploy
fly volumes create data --size 1
```

Add to `fly.toml`: `[mounts] source="data" destination="/data"` and remove the `[http_service]`
block. Then `fly secrets set SMTP_PASS=... ...` and `fly deploy`.

If Reddit starts returning 403/429 from a cloud host, that host's IP range is blocked for
unauthenticated feeds. Run it on a home machine or a VPS instead.
