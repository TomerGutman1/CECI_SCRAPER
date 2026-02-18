# Anti-Block Strategy for gov.il Scraping

## Background

On January 31, 2026, the production server (CECI, IP 178.62.39.248) was blocked by Cloudflare WAF while scraping gov.il. Analysis of `daily_sync.log` showed:

- **First 2 runs:** Catalog API worked fine, no new decisions to process
- **Third run:** Successfully scraped 31 decisions, then got blocked mid-run at decision #57 when URL recovery triggered a second catalog API call
- **All subsequent runs:** Blocked immediately ("Sorry, you have been blocked")

**Root cause:** Rate limiting triggered by ~57 rapid successive requests without delays, plus multiple Chrome sessions being created (one per decision = suspicious fingerprint).

---

## Implemented Mitigations (February 2026)

### 1. Session Reuse

**Before:** Every scrape request created a new Chrome browser instance (50+ instances for 50 decisions).

**After:** A single `SeleniumWebDriver` session is opened at the start of the sync and reused for all catalog API calls and decision page scrapes.

**Files:** `bin/sync.py`, `catalog.py`, `decision.py` — all functions accept optional `swd` parameter.

**Impact:** 50+ Chrome sessions reduced to 1. Consistent browser fingerprint throughout the sync.

### 2. Rate Limiting

Every page navigation includes a random delay of **2-5 seconds** before the request.

| Parameter | Value | Location |
|-----------|-------|----------|
| `REQUEST_DELAY_MIN` | 2.0s | `selenium.py` |
| `REQUEST_DELAY_MAX` | 5.0s | `selenium.py` |

This is implemented in the `navigate_to()` method of `SeleniumWebDriver`, which is used for all sequential page loads within a reused session.

### 3. Batch Cooldowns

Every 10 decisions, the sync takes a longer break of **15-30 seconds**.

| Parameter | Value | Location |
|-----------|-------|----------|
| `BATCH_SIZE` | 10 | `sync.py` |
| `BATCH_DELAY_MIN` | 15.0s | `sync.py` |
| `BATCH_DELAY_MAX` | 30.0s | `sync.py` |

### 4. Graceful Degradation

If 3 consecutive scrape attempts fail, the sync assumes it has been blocked and **stops scraping immediately** instead of hammering the server. The decisions already scraped are still processed through AI and inserted into the database.

| Parameter | Value | Location |
|-----------|-------|----------|
| `MAX_CONSECUTIVE_BLOCKS` | 3 | `sync.py` |

The remaining decisions will be picked up in the next daily sync run (they'll show up as "new entries not in database").

### 5. Undetected ChromeDriver

The scraper uses `undetected-chromedriver` instead of standard Selenium ChromeDriver. This library patches the ChromeDriver binary to avoid bot detection by:
- Removing `navigator.webdriver` flag
- Patching `cdc_` variables in the ChromeDriver binary
- Using a realistic browser fingerprint

Auto-detection of the installed Chrome version avoids version mismatches in the Docker container.

### 6. Explicit Cloudflare Detection (February 2026)

Dedicated `detect_cloudflare_block()` function in `selenium.py` with comprehensive pattern matching:
- **JS challenges:** "just a moment", "checking your browser", "cf-browser-verification", "cf-challenge"
- **Block pages:** "sorry you have been blocked", "access denied", "attention required"
- **Verification:** "verify you are human", "enable javascript and cookies"
- **Rate limits:** "ray id:", "too many requests", "rate limit"
- **Title patterns:** "Just a moment", "Attention Required", "Access denied"
- **Short non-Hebrew pages** with Cloudflare reference in HTML

Raises `CloudflareBlockedError` from `navigate_to()`, allowing callers to handle blocks differently from other errors. In `sync.py`, Cloudflare blocks trigger a **30-60s cooldown** before the next attempt (vs. no cooldown for regular failures).

Also used by `validate_scraped_content()` in `qa.py` as a single source of truth for Cloudflare detection.

### 7. Browser Fingerprint Randomization (February 2026)

Each Chrome session uses a **randomized fingerprint** (per session, consistent within a sync run):

- **Window size:** Random from 6 common resolutions (1920x1080, 1366x768, 1536x864, 1440x900, 1280x720, 2560x1440)
- **Accept-Language:** Random Hebrew variant (he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7 etc.)
- **Anti-automation:** `--disable-blink-features=AutomationControlled`

Prevents Cloudflare from fingerprinting the scraper across sessions.

### 8. Dynamic Exponential Backoff (February 2026)

The `navigate_to()` method uses a **dynamic delay multiplier** that adapts to server behavior:

| Parameter | Value | Location |
|-----------|-------|----------|
| `BACKOFF_INCREASE` | 2.0x | `selenium.py` |
| `BACKOFF_DECAY` | 0.9x | `selenium.py` |
| `BACKOFF_MAX` | 4.0x | `selenium.py` |

**Behavior:**
- Normal: delay = 2-5s (multiplier = 1.0x)
- After 1st Cloudflare detection: delay = 4-10s (multiplier = 2.0x)
- After 2nd consecutive: delay = 8-20s (multiplier = 4.0x, capped)
- Each success decays the multiplier by 0.9x back toward 1.0

---

## Runtime Impact

| Metric | Before | After |
|--------|--------|-------|
| 50-decision sync time | ~12.5 min | ~18 min |
| Chrome sessions created | 50+ | 1 |
| Avg delay between requests | 0s | 3.5s (adapts up to 14s if throttled) |
| Batch cooldowns | 0 | 4 (at 10, 20, 30, 40) |
| Recovery from block | None (keeps hammering) | Stops after 3 failures |
| Cloudflare-specific cooldown | N/A | 30-60s per detection |
| Fingerprint variation | None (identical every run) | Random per session |

The extra ~5 minutes is negligible for a cron job running at 02:00 AM.

---

## Tuning Guide

### If still getting blocked — increase delays:

```python
# In selenium.py
REQUEST_DELAY_MIN = 4.0   # was 2.0
REQUEST_DELAY_MAX = 8.0   # was 5.0
BACKOFF_MAX = 6.0          # was 4.0 (allow multiplier up to 6x → max 48s delay)

# In sync.py
BATCH_SIZE = 5             # was 10 (more frequent cooldowns)
BATCH_DELAY_MIN = 30.0     # was 15.0
BATCH_DELAY_MAX = 60.0     # was 30.0
```

### If sync is too slow — decrease delays:

```python
# In selenium.py
REQUEST_DELAY_MIN = 1.0
REQUEST_DELAY_MAX = 3.0
BACKOFF_DECAY = 0.8        # was 0.9 (faster recovery after block)

# In sync.py
BATCH_SIZE = 20
BATCH_DELAY_MIN = 10.0
BATCH_DELAY_MAX = 20.0
```

### For one-time large batches — consider splitting:

Instead of processing 100 decisions in one run, use `--max-decisions 25` and run 4 times with gaps:
```bash
python bin/sync.py --max-decisions 25 --no-approval
sleep 300  # 5 minute break
python bin/sync.py --max-decisions 25 --no-approval
# ... repeat
```

---

## If Blocked Again

1. **Wait 24-48 hours** — rate-limit blocks are usually temporary
2. **Check if unblocked:** `ssh ceci "docker exec gov2db-scraper python3 bin/sync.py --max-decisions 1 --no-approval --verbose"`
3. **If still blocked after 48h** — the IP range may be permanently blocked. Options:
   - Run sync from a local machine (works — tested)
   - Use a residential proxy (BrightData, SmartProxy: $15-50/mo)
   - Add a VPN client (WireGuard) to the Docker container ($5-10/mo)
   - Move to a different VPS provider (AWS, Hetzner)
4. **Increase delays** — see Tuning Guide above

---

## Monitoring

Check for block-related log entries:
```bash
# On server
ssh ceci "docker exec gov2db-scraper grep -E '(consecutive|Cloudflare|blocked|Rate limit|Batch cooldown|Backoff|multiplier)' /app/logs/scraper.log | tail -20"

# Or from daily sync log
ssh ceci "grep -E '(consecutive|Cloudflare|blocked|Batch cooldown|Backoff|multiplier)' /root/ceci-ai-production/ceci-ai/GOV2DB/logs/daily_sync.log | tail -20"
```
