# Stock Pulse

A retail-sentiment + market analytics dashboard: StockTwits chatter
cross-checked against real price action, a sector heatmap, market pulse, and
auto-generated signals — now running as a real website, updated automatically
once a day, with nothing to run yourself.

**How it works:** GitHub runs the Python script on a daily timer (free,
via GitHub Actions), the script writes an updated dashboard page, and GitHub
Pages serves that page as a website you can open from any browser or your
phone — even when your computer is off. No server to maintain, no hosting
bill.

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

### 4. Let Actions write back to your repo

1. Go to your repo's **Settings** tab → **Actions** → **General**
2. Scroll to **Workflow permissions**
3. Select **Read and write permissions**
4. Click **Save**

   (This lets the daily job commit the updated dashboard back into your repo.)

### 5. Turn on GitHub Pages

1. Still in **Settings**, click **Pages** in the left sidebar
2. Under **Build and deployment** → **Source**, choose **Deploy from a branch**
3. Under **Branch**, select `main` and folder `/docs`, then **Save**
4. GitHub will show you your site's URL — something like
   `https://yourusername.github.io/stock-pulse/`. That's your website.

### 6. Run it for the first time

Don't wait for the schedule — trigger it manually once to confirm everything works:

1. Go to the **Actions** tab on your repo
2. Click **Update Stock Pulse Dashboard** in the left list
3. Click **Run workflow** (dropdown on the right) → **Run workflow**
4. Wait 2–4 minutes, refresh the page — you should see a green checkmark
5. Visit your Pages URL from step 5 — your dashboard should now be live

From here, it re-runs automatically every day on the schedule in
`.github/workflows/update-dashboard.yml` (12:30 UTC by default — see below
to change it). You never need to run anything yourself again.

## Changing your watchlist later

Edit `config.json` directly on GitHub (click the file → pencil icon → edit →
commit). No need to re-upload anything else — the next scheduled run picks
up your changes automatically.

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
python main.py               # writes docs/index.html
```

Then open `docs/index.html` directly in your browser.

## What's on the dashboard

- **Market Pulse** — SPY, QQQ, Dow, VIX at a glance
- **Sector Heatmap** — day performance across all 11 S&P sectors
- **Signals** — auto-generated callouts:
  - **Bullish dip**: price fell but chatter stayed bullish
  - **Bearish rally**: price rose but chatter stayed bearish
  - **Volume spike**: today's chatter is running well above a ticker's
    recent baseline

  These sharpen over the first several days as `data/history.json` builds
  up a real baseline.
- **Bullish / Bearish Leaders** — ranked by sentiment score, each with its
  bull/bear split, price, day change, and day-over-day sentiment shift
- **Most Discussed** — pure volume ranking, kept separate from sentiment so
  "loud" and "bullish" aren't conflated
- **Your Watchlist** — every tracked ticker, with filters (All / Active only
  / Bullish / Bearish)
- **Market News** — headlines from your configured RSS feeds

Click any ticker anywhere to open its live price and chart on Yahoo Finance.

## How it works under the hood

- **StockTwits**: public, unauthenticated read API — trending symbols plus
  a message stream per watchlist ticker. No login required.
- **Sentiment**: StockTwits users' own Bullish/Bearish tags are weighted
  heavily; untagged posts fall back to VADER (offline lexicon-based
  sentiment), extended with retail trading slang.
- **Prices**: `yfinance` pulls current price and day change for every ticker
  in play, plus market-pulse indices and sector ETFs.
- **Signals**: computed by comparing sentiment direction against same-day
  price direction, and today's message volume against a 7-day rolling
  average from history.
- **News**: RSS feeds configured in `config.json`.
- **History**: `data/history.json` accumulates a daily snapshot per ticker —
  this is what powers day-over-day deltas and volume-spike detection, and
  it's committed back to the repo automatically by the Action each run.

## Notes and limits

- Sentiment scoring is retail mood, not financial analysis. Signals
  highlight *disagreement* between chatter and price — observations, not
  trade recommendations.
- Prices may be delayed depending on Yahoo Finance's feed; this isn't a
  real-time trading terminal.
- GitHub Actions' free tier gives public repos unlimited minutes for
  scheduled workflows like this one, so there's no cost at this usage level.
- This tool is for personal, non-commercial use only.
