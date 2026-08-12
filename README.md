# Undertow

A full site now, not just a dashboard: a marketing home page, About, Careers,
and the live data product itself — a retail-sentiment + market analytics
dashboard cross-checking StockTwits/Reddit/ApeWisdom chatter against real
price action and news sentiment, with auto-generated signals. Runs as a real
website, updated automatically once a day, with nothing to run yourself.

**Site structure** (all under `docs/`, served by GitHub Pages):
- `index.html` — marketing homepage (static, hand-written)
- `about.html` — about/philosophy page (static)
- `careers.html` — careers page (static, honest: this is a solo project)
- `dashboard.html` — the live data dashboard — **the only page regenerated
  daily** by `main.py`

**How it works:** GitHub runs the Python script on a daily timer (free,
via GitHub Actions), the script rewrites `docs/dashboard.html`, and GitHub
Pages serves the whole `docs/` folder as a website you can open from any
browser or your phone — even when your computer is off. No server to
maintain, no hosting bill.

## One-time setup (about 10 minutes, all in your browser)

### 1. Create a GitHub account

If you don't have one already: go to https://github.com/signup — it's free.

### 2. Create a new repository

1. Click the **+** in the top right of GitHub → **New repository**
2. Name it something like `stock-pulse`
3. Set it to **Public** (GitHub Pages needs a public repo on the free plan —
   see the privacy note below)
4. Don't check any of the "initialize with" boxes
5. Click **Create repository**

### 3. Upload these files

1. On your new (empty) repo page, click **uploading an existing file**
2. Unzip this project on your computer, then drag the **entire contents** of
   the `stock_pulse` folder into the upload area — all the files and folders
   (`main.py`, `config.json`, `.github`, `docs`, `data`, etc.)
3. Scroll down, click **Commit changes**

   GitHub sometimes hides folders that start with a dot (`.github`) in drag-
   and-drop. If `.github/workflows/update-dashboard.yml` didn't upload, use
   **Add file → Upload files** again and drag just that file in, recreating
   the `.github/workflows/` path when prompted, or use GitHub Desktop
   (https://desktop.github.com) instead, which handles this without issue.

### 4. Reddit API access (not available — skip this)

Reddit locked down new API access in late 2025 behind a manual approval
process (their "Responsible Builder Policy"), and this project's request
was submitted and **rejected** — personal/hobby projects are routinely
turned down. `reddit.py` is built and will pick up credentials
automatically if that ever changes (a future reapplication, a policy
change), but there's nothing to do here right now.

This isn't a blocker: Undertow gets Reddit-adjacent signal two other
ways that need no approval — see **ApeWisdom** and **Reddit mention
spikes** further down. Nothing here is required to get a working
dashboard.

### 5. Get a free Gemini API key (for AI-powered stock analysis)

The analyst model (`analyst.py`) — the layer that reads a stock's
fundamentals, sentiment, and news together and writes an actual reasoned
take, instead of a fixed formula — runs on Google's Gemini API. The free
tier is genuinely free and indefinite: no credit card, just a Google
account.

1. Go to https://aistudio.google.com and sign in with any Google account
2. Click **Get API key** → **Create API key**
3. Copy the key (starts with `AIza...`)

One honest tradeoff on the free tier: Google may use the data you send
to improve their products. That's fine here — we're only sending public
market data (tickers, aggregated sentiment stats, headlines), nothing
personal — but worth knowing. If you ever want to switch to a paid
provider (Claude, GPT) for guaranteed data privacy or better quality,
that's a small, contained change in `analyst.py`, not a rewrite.

Skip this and everything else still works — the analyst model just won't
run, same graceful-skip pattern as Reddit.

### 6. Add your Reddit credentials as repo secrets

Skip this if you skipped step 4.

1. Go to your repo's **Settings** tab → **Secrets and variables** → **Actions**
2. Click **New repository secret**, add these three (one at a time):
   - `REDDIT_CLIENT_ID` — the string under your app's name
   - `REDDIT_CLIENT_SECRET` — the "secret" value
   - `REDDIT_USER_AGENT` — any descriptive string, e.g. `stock-pulse-yourname/1.0`
   - `GEMINI_API_KEY` — the key from step 5, if you got one

Secrets are encrypted and never shown in logs — this is the standard,
safe way to give a GitHub Actions job credentials.

### 7. Let Actions write back to your repo

1. Go to your repo's **Settings** tab → **Actions** → **General**
2. Scroll to **Workflow permissions**
3. Select **Read and write permissions**
4. Click **Save**

   (This lets the daily job commit the updated dashboard back into your repo.)

### 8. Turn on GitHub Pages

1. Still in **Settings**, click **Pages** in the left sidebar
2. Under **Build and deployment** → **Source**, choose **Deploy from a branch**
3. Under **Branch**, select `main` and folder `/docs`, then **Save**
4. GitHub will show you your site's URL — something like
   `https://yourusername.github.io/stock-pulse/`. That's your website.

### 9. Run it for the first time

Don't wait for the schedule — trigger it manually once to confirm everything works:

1. Go to the **Actions** tab on your repo
2. Click **Update Undertow Dashboard** in the left list
3. Click **Run workflow** (dropdown on the right) → **Run workflow**
4. Wait 2–4 minutes, refresh the page — you should see a green checkmark
5. Visit your Pages URL from step 8 — your dashboard should now be live

From here, it re-runs automatically every day on the schedule in
`.github/workflows/update-dashboard.yml` (12:30 UTC by default — see below
to change it). You never need to run anything yourself again.

## Changing your tracked tickers later

Edit `watchlist` and `flagship_tickers` in `config.json` directly on GitHub
(click the file → pencil icon → edit → commit) — no need to re-upload
anything else, the next scheduled run picks up your changes automatically.
Right now they're the same 15 tickers on purpose (see `PRODUCT.md`); if you
add to `watchlist` without adding to `flagship_tickers`, that ticker gets
sentiment/price/charts but not the AI analysis section.

## Changing the daily run time

Open `.github/workflows/update-dashboard.yml` and edit this line:

```yaml
- cron: '30 12 * * *'
```

The format is `minute hour * * *` **in UTC**, not your local time. For
example, for 7:00am Eastern Daylight Time, use `'0 11 * * *'`. A quick way
to convert: search "UTC to Eastern Time" for the current offset (it shifts
with daylight saving).

## Privacy note

A GitHub Pages site on the free plan is publicly accessible to anyone with
the URL — it won't appear in Google unless you link it somewhere, but it
isn't private. Your dashboard doesn't contain anything sensitive (just
public sentiment/price data and your watchlist tickers), but if you'd rather
keep it fully private, that requires either a GitHub Pro/Team plan (which
supports private-repo Pages) or a different host — let me know if you want
that route instead.

## Running it locally too (optional)

Everything still works locally exactly as before, if you want to test
changes before they go live:

```bash
pip install -r requirements.txt
python test_connection.py   # confirms StockTwits is reachable
python main.py               # writes docs/dashboard.html
```

Then open `docs/dashboard.html` directly in your browser (or `docs/index.html`
for the marketing homepage — that one's static and doesn't need a run).

To get Reddit data on local runs too, set the same three credentials as
environment variables before running (PowerShell shown; use `export` on
macOS/Linux):

```powershell
$env:REDDIT_CLIENT_ID = "your-client-id"
$env:REDDIT_CLIENT_SECRET = "your-secret"
$env:REDDIT_USER_AGENT = "stock-pulse-yourname/1.0"
$env:GEMINI_API_KEY = "your-gemini-key"
python main.py
```

To make `GEMINI_API_KEY` persist across terminal sessions (so you don't
have to re-set it every time) instead of the temporary `$env:` line
above, run this once from your own terminal — not something to paste
into a shared chat, since it's a real credential:

```powershell
setx GEMINI_API_KEY "your-gemini-key"
```

Then open a fresh terminal for it to take effect.

Without them, Undertow just logs a notice and falls back to StockTwits
only — nothing breaks.

## What's on the dashboard

Right now the whole site is deliberately narrow: it covers exactly the
tickers in `flagship_tickers` (config.json) — nothing else. No trending
discovery, no broad market view. Market Pulse and Sector Heatmap were
part of an earlier, broader version and are shelved for now (the code's
still in `market_data.py`), not deleted — see `PRODUCT.md` for why.

- **AI Analysis** — click any ticker's chart to see a synthesized read
  from an LLM (Gemini): a 0-100 score, a verdict, and real bullish
  factors, bearish factors, risks, and catalysts — reasoned from that
  ticker's live fundamentals, retail sentiment, recent price action, and
  matched news, not a fixed formula. See `analyst.py`.
- **Signals** — auto-generated callouts:
  - **Bullish dip**: price fell but chatter stayed bullish
  - **Bearish rally**: price rose but chatter stayed bearish
  - **Volume spike**: today's StockTwits chatter is running well above a
    ticker's recent baseline
  - **Reddit spike**: today's Reddit mentions (via ApeWisdom) are running
    well above yesterday's — an independent second read on attention,
    since it's a different source than StockTwits
  - **Media divergence**: news coverage and retail chatter are pulling in
    opposite directions on the same ticker

  The StockTwits-based ones sharpen over the first several days as
  `data/history.json` builds up a real baseline.
- **Bullish / Bearish Leaders** — ranked by sentiment score, each with its
  bull/bear split, price, day change, and day-over-day sentiment shift.
  Hover the mention count for a source breakdown (StockTwits / Reddit /
  ApeWisdom).
- **Most Discussed** — pure volume ranking, kept separate from sentiment so
  "loud" and "bullish" aren't conflated
- **Your Watchlist** — every tracked ticker, with filters (All / Active only
  / Bullish / Bearish)
- **Market News** — headlines from your configured RSS feeds, each scored
  for sentiment so you can see when the press leans bullish or bearish on
  a story, not just read it

Click any ticker anywhere to open a self-hosted chart — a ~3-month price
history with hover crosshair, built entirely from data already fetched for
this run, no external chart embed. Yahoo Finance is still one click away
inside that chart, for anyone who wants the full real-time view.

## How it works under the hood

- **StockTwits**: public, unauthenticated read API — trending symbols plus
  a message stream per watchlist ticker. No login required. Paginated up
  to `messages_per_symbol` (default 60) instead of a flat 30.
- **Reddit** (`reddit.py`): official read-only API (`praw`) — hot posts from
  `reddit_subreddits` in `config.json` (default: r/wallstreetbets,
  r/stocks, r/investing, r/StockMarket), plus top-level comments on posts
  that mention a watchlist ticker. Requires the approval process in setup
  step 4 above. Additive — skipped cleanly if no credentials are set.
- **ApeWisdom** (`apewisdom.py`): free, keyless third-party aggregator
  (apewisdom.io) tracking ticker mention volume across Reddit stock
  subreddits. This is attention data only — mentions and upvotes, no
  bullish/bearish direction — used to cross-check StockTwits' own volume
  reading with an independent source, and to power the Reddit-spike
  signal (which needs no Reddit approval to work). Being a third-party
  service rather than Reddit itself, it could change or go down without
  notice; failures are logged and skipped, same as every other source.
- **News sentiment**: headlines from your RSS feeds are scored with the
  same VADER pipeline as chatter, and matched to your flagship tickers by
  symbol mention — giving a media-sentiment read distinct from retail
  sentiment, which is what the media-divergence signal compares.
- **Sentiment**: StockTwits users' own Bullish/Bearish tags are weighted
  heavily; untagged posts (all of Reddit, plus untagged StockTwits posts)
  fall back to VADER (offline lexicon-based sentiment), extended with
  retail trading slang.
- **Prices**: `yfinance` pulls current price, day change, and 3-month
  history for every flagship ticker.
- **AI analysis**: `analyst.py` sends each flagship ticker's fundamentals,
  sentiment, price trend, and matched news to Gemini, which reasons about
  them together — growth in context of company size, known company
  situations, genuinely balanced bullish/bearish factors — rather than
  scoring off a fixed formula.
- **Signals**: computed by comparing sentiment direction against same-day
  price direction, today's message volume against a 7-day rolling average
  from history, day-over-day Reddit mention growth from ApeWisdom, and
  media sentiment against retail sentiment.
- **History**: `data/history.json` accumulates a daily snapshot per ticker —
  this is what powers day-over-day deltas and volume-spike detection, and
  it's committed back to the repo automatically by the Action each run.

## Notes and limits

- Sentiment scoring is retail mood, not financial analysis. Signals
  highlight *disagreement* between chatter and price — observations, not
  trade recommendations.
- Prices may be delayed depending on Yahoo Finance's feed; this isn't a
  real-time trading terminal.
- ApeWisdom mention data is attention/volume only, not sentiment
  direction — it tells you something is being talked about more, not
  whether that talk is bullish or bearish. True Reddit sentiment
  direction requires the official API (setup step 4), which is currently
  gated behind Reddit's approval process.
- News-to-ticker matching is symbol-based, so most general market
  headlines won't match a specific watchlist ticker — media sentiment
  coverage will be sparser than retail chatter coverage. That's expected,
  not a bug.
- GitHub Actions' free tier gives public repos unlimited minutes for
  scheduled workflows like this one, so there's no cost at this usage level.
- This tool is for personal, non-commercial use only. Both Reddit's and
  ApeWisdom's terms would need a fresh look before any commercial use.
