"""Watch Reddit, Hacker News and job feeds for work Growthfern can do; email a digest with drafted replies."""
import html, json, os, re, smtplib, sqlite3, time, urllib.parse, urllib.request
from email.message import EmailMessage

SERVICES = ("Growthfern (growthfern.in): small studio that designs and builds websites, "
            "web apps and custom software, product strategy and UI/UX, branding and creative "
            "design, SEO built in, hosting and launch, growth marketing and campaigns.")

SUBREDDITS = os.getenv("SUBREDDITS", "forhire+hiring+slavelabour+startups+smallbusiness+Entrepreneur+marketing+web_design+SaaS")
# Job-board feeds: every item is already a hiring post, so only a service keyword is needed.
FEEDS = os.getenv("FEEDS", ",".join([
    "https://weworkremotely.com/categories/remote-design-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss"])).split(",")
HN_QUERY = '"seeking freelancer"'  # monthly HN "Freelancer? Seeking freelancer?" thread
UA = os.getenv("USER_AGENT", "growthfern-leads/1.0")

_WHO = "(?:someone|a|an)(?: \\w+)? (?:developer|dev|designer|agency|freelancer|marketer|expert|consultant)"
HIRING = ["[hiring]", "hiring", "to hire", "freelancer wanted", "need someone to", "looking for someone to",
          f"re:(?:looking for|need|seeking|recommend) {_WHO}"]
SERVICE_KW = ["website", "web app", "webapp", "landing page", "web developer", "web designer",
              "shopify", "wordpress", "webflow", "ui/ux", "ux designer", "ui designer", "mvp",
              "saas", "branding", "brand identity", "logo", "seo", "marketing agency",
              "growth marketing", "digital marketing", "ads", "redesign", "product designer",
              "frontend", "front-end", "full stack", "full-stack", "react", "next.js"]
SKIP = ["[for hire]", "for hire", "[offer]", "hire me", "my portfolio"]


def kw_match(title, body="", hiring_implied=False):
    """Cheap first-pass filter: a service keyword, plus a hiring signal unless the source implies one.
    Job-board items (hiring_implied) are matched on the title only: their descriptions mention everything."""
    t = title.lower() if hiring_implied else f"{title}\n{body}".lower()
    if any(s in title.lower() for s in SKIP):
        return False
    pat = lambda k: k[3:] if k.startswith("re:") else r"(?<!\w)" + re.escape(k) + r"(?!\w)"
    has = lambda kws: any(re.search(pat(k), t) for k in kws)
    return (hiring_implied or has(HIRING)) and has(SERVICE_KW)


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20).read()


def text(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


def from_feed(url, src, hiring_implied):
    import feedparser
    for e in feedparser.parse(fetch(url)).entries:
        yield dict(id=f"{src}:{e.get('id', e.link)}", src=src, title=text(e.title), url=e.link,
                   body=text(e.get("summary", "")), hiring_implied=hiring_implied)


def posts():
    sources = [reddit, hn]
    sources += [lambda f=f: from_feed(f, urllib.parse.urlparse(f).netloc, True) for f in map(str.strip, FEEDS) if f]
    for s in sources:  # one broken source must not stop the others
        try:
            yield from list(s())
        except Exception as e:
            print("source error:", e, flush=True)


def reddit():
    """Official API (read-only OAuth) if a Reddit script app is configured; else the public RSS feed,
    which is tightly rate-limited and often blocked from cloud IPs."""
    if not os.getenv("REDDIT_CLIENT_ID"):
        yield from from_feed(f"https://www.reddit.com/r/{SUBREDDITS}/new/.rss?limit=100", "reddit", False)
        return
    import praw
    r = praw.Reddit(client_id=os.environ["REDDIT_CLIENT_ID"],
                    client_secret=os.environ["REDDIT_CLIENT_SECRET"], user_agent=UA)
    for s in r.subreddit(SUBREDDITS).new(limit=100):
        yield dict(id=f"reddit:t3_{s.id}", src="reddit", title=s.title, body=s.selftext,
                   url=f"https://www.reddit.com{s.permalink}", hiring_implied=False)


def hn():
    since = int(time.time()) - 86400
    hn = json.loads(fetch("https://hn.algolia.com/api/v1/search_by_date?tags=comment&hitsPerPage=100"
                          f"&numericFilters=created_at_i>{since}&query=" + urllib.parse.quote(HN_QUERY)))
    for h in hn["hits"]:
        body = text(h.get("comment_text"))
        yield dict(id=f"hn:{h['objectID']}", src="hackernews", title=body[:100], body=body,
                   url=f"https://news.ycombinator.com/item?id={h['objectID']}", hiring_implied=True)


def db(path=os.getenv("DB_PATH", "leads.db")):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("create table if not exists seen(id text primary key, ts real)")
    return c


def template_reply(title):
    return (f"Hi! Saw your post \"{title[:90]}\". We're Growthfern, a small studio that designs and "
            "builds websites, web apps and brands. Happy to share a quick plan and estimate. "
            "Free site audit too: growthfern.in")


def classify(title, body):
    """Return (fit, reply). Uses Claude if ANTHROPIC_API_KEY is set, else keywords + template."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return True, template_reply(title)
    import anthropic
    r = anthropic.Anthropic().messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-haiku-5-5"), max_tokens=2000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": {
            "type": "object", "additionalProperties": False, "required": ["fit", "reply"],
            "properties": {"fit": {"type": "boolean"}, "reply": {"type": "string"}}}}},
        system=(f"{SERVICES}\nDecide if this post is a real request to hire or pay someone (freelancer, "
                "agency, contractor, or a role a studio could pitch for) for work this studio does. "
                "Not fit: people offering services, job seekers, discussions. If fit, write a short, "
                "specific, friendly first message (max 80 words) referencing their need, no hype, no "
                "invented results or clients, end with growthfern.in. If not fit, reply is empty."),
        messages=[{"role": "user", "content": f"Title: {title}\n\n{body[:4000]}"}])
    if r.stop_reason != "end_turn":
        return False, ""
    d = json.loads(next(b.text for b in r.content if b.type == "text"))
    return d["fit"], d["reply"]


def email(leads):
    m = EmailMessage()
    m["Subject"] = f"{len(leads)} new lead{'s' * (len(leads) > 1)}: {leads[0]['title'][:60]}"
    m["From"], m["To"] = os.environ["SMTP_USER"], os.environ["ALERT_EMAIL"]
    m.set_content("\n\n".join(f"[{p['src']}] {p['title']}\n{p['url']}\n\nDraft reply:\n{p['reply']}\n{'-' * 50}"
                              for p in leads))
    with smtplib.SMTP_SSL(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "465"))) as s:
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"].strip('"').replace(" ", ""))  # Google shows spaces; docker keeps quotes
        s.send_message(m)


def cycle(c, items, dry, prime=False):
    """Process new items; return the matched ones. prime=True only marks items as seen (first run)."""
    leads = []
    for p in items:
        if c.execute("select 1 from seen where id=?", (p["id"],)).fetchone():
            continue
        c.execute("insert into seen values(?,?)", (p["id"], time.time())); c.commit()
        if prime or not kw_match(p["title"], p["body"], p["hiring_implied"]):
            continue
        fit, p["reply"] = classify(p["title"], p["body"])
        if fit:
            leads.append(p)
    if leads and dry:
        for p in leads:
            print(f"MATCH [{p['src']}] {p['title']}\n{p['url']}\n{p['reply']}\n{'-' * 60}", flush=True)
    elif leads:
        email(leads)
    return leads


def main():
    dry = os.getenv("DRY_RUN", "1") == "1"
    c = db()
    prime = not c.execute("select 1 from seen limit 1").fetchone() and not dry  # don't email the backlog
    print(f"polling every {os.getenv('POLL_SECONDS', '120')}s dry_run={dry}", flush=True)
    while True:
        try:
            print(f"{time.strftime('%H:%M')} {len(cycle(c, posts(), dry, prime))} new leads", flush=True)
            prime = False
        except Exception as e:
            print("error:", e, flush=True)
        if os.getenv("RUN_ONCE") == "1":  # scheduled runners (GitHub Actions) do one check per run
            return
        time.sleep(int(os.getenv("POLL_SECONDS", "120")))


if __name__ == "__main__":
    main()
