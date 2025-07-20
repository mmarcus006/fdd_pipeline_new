# Franchise FDD Scrapers – **Combined Claude-Code Spec**

> **Bootstrapping**  Run `qnew` at the start of every session so Claude loads the @CLAUDE.md guidelines and shortcuts automatically.

***

## 0. Environment & Configuration

| Key | Description | Default |
| :--- | :--- | :--- |
| `HEADLESS` | Run Playwright in headless mode (`true`) or headed (`false`) for debugging. | `true` |
| `DOWNLOAD_DIR` | Root folder for all PDF downloads. | `./downloads` |
| `THROTTLE_SEC` | Base delay between page or PDF actions (seconds). | `0.5` |
| `PDF_RETRY_MAX` | Maximum attempts per PDF download. | `3` |
| `PDF_RETRY_BACKOFF` | Comma-separated seconds for exponential back-off. | `1,2,4` |
| `MAX_WORKERS` | Concurrent tasks when async or thread pool is enabled. | `4` |

Load these with `python-dotenv` inside `config.py` so every module reads a single `settings` object.

***

## 1. Reusable Browser Factory

```python
# franchise_scrapers/browser.py
from playwright.async_api import async_playwright, Browser
from .config import settings

async def get_browser() -> Browser:
    playwright = await async_playwright().start()
    return await playwright.chromium.launch(headless=settings.HEADLESS)
```

*   **Choice of headless or headed** is driven solely by `settings.HEADLESS`.
*   Context creation (viewport, download path, user-agent) belongs in `get_context()` which all scrapers call.

***

## 2. Pydantic Models

> Located in `franchise_scrapers/models.py`. Every field carries a docstring-style `description` for automated schema docs.

```python
from pydantic import BaseModel, HttpUrl, Field
from datetime import datetime

class CleanFDDRow(BaseModel):
    """Single record from the Minnesota Commerce *Clean FDD* table."""

    document_id: str = Field(..., description="Unique filing identifier parsed from the PDF URL query param `documentId`.")
    legal_name: str = Field(..., description="Legal franchisor name as shown in column 2.")
    pdf_url: HttpUrl = Field(..., description="Absolute URL to the FDD PDF.")
    scraped_at: datetime = Field(..., description="UTC timestamp when the table row was captured.")

class WIActiveRow(BaseModel):
    """Row from Wisconsin *Active Filings* list."""

    legal_name: str = Field(..., description="Legal franchisor name.")
    filing_number: str = Field(..., description="Numeric filing # column.")

class WIRegisteredRow(BaseModel):
    """Row produced after the WI search step – only *Registered* rows are kept."""

    filing_number: str = Field(..., description="Same as Active → used to join.")
    legal_name: str = Field(..., description="Name from search results table.")
    details_url: HttpUrl = Field(..., description="Absolute Details page link.")

class WIDetailsRow(BaseModel):
    """Full details of a WI filing plus PDF path."""

    filing_number: str = Field(..., description="Primary key across CSVs.")
    status: str = Field(..., description="Filing status label – expected 'Registered'.")
    legal_name: str = Field(..., description="Legal name from Details page.")
    trade_name: str | None = Field(None, description="DBA / trade name if present.")
    contact_email: str | None = Field(None, description="Contact e-mail extracted from Details page.")
    pdf_path: str | None = Field(None, description="Filesystem path of the downloaded PDF relative to `DOWNLOAD_DIR`.")
    pdf_status: str = Field(..., description="'ok' | 'failed' | 'skipped'.")
    scraped_at: datetime = Field(..., description="UTC timestamp for this Details scrape.")
```

***

## 3. High-Level Flows

### 3.1 Minnesota – *Clean FDD* Scraper

1.  Obtain a browser context from `browser.get_context()`.
2.  Navigate to the entry URL and wait for `#results` table.
3.  **Pagination loop** – click `#pagination button.btn.btn-primary` while present; wait for new rows or two 3-s polls with no growth.
4.  Build a `CleanFDDRow` list, convert to DataFrame, append `pdf_url`.
5.  Write `mn_clean_fdd.csv`.
6.  If `--download` flag is set, download each PDF employing retry policy:
    *   Attempt ≤ `PDF_RETRY_MAX` times.
    *   Delay pattern defined by `PDF_RETRY_BACKOFF`.
    *   Set status per-row.

### 3.2 Wisconsin – Active → Registered → Details

1.  **Active list** → create `WIActiveRow` CSV.
2.  **Search loop** (optionally **`--max-workers`**):
    *   Fill `#txtName` with each active name.
    *   Keep only *Registered* rows; write `WIRegisteredRow` CSV.
3.  **Details extraction** (flag `--details`):
    *   GET each Details URL; parse fields into `WIDetailsRow`.
    *   Click *Download*; retry as above; name files `<filing#_>_<legal-snake>.pdf`.

***

## 4. Retry & Back-off Logic (shared)

```python
from asyncio import sleep
from franchise_scrapers.config import settings

async def with_retry(coro):
    delays = [float(x) for x in settings.PDF_RETRY_BACKOFF.split(',')]
    for attempt, delay in enumerate(delays, start=1):
        try:
            return await coro()
        except Exception as exc:
            if attempt >= settings.PDF_RETRY_MAX:
                raise
            await sleep(delay)
```

*   Every network or `page.expect_download()` call is wrapped with `with_retry`.

***

## 5. Combined Package Layout

```shell
franchise_scrapers/
├── __init__.py
├── config.py          # dotenv → settings
├── browser.py         # reusable factory (↑ §1)
├── models.py          # pydantic schemas (↑ §2)
├── cli.py             # Typer root; sub-commands: mn, wi
├── mn/                # Minnesota Clean FDD implementation
│   ├── __init__.py
│   ├── scraper.py     # main flow
│   └── parsers.py     # row helpers
├── wi/                # Wisconsin implementation
│   ├── __init__.py
│   ├── active.py
│   ├── search.py
│   └── details.py
└── tests/
    ├── unit/
    │   ├── test_parsers_mn.py
    │   ├── test_models.py
    │   └── test_details_parser_wi.py
    └── integration/
        ├── test_mn_flow.py
        ├── test_active_wi.py
        └── test_details_wi.py
```

***

## 6. Testing Matrix (Unified)

| Layer | Target | Tooling |
| :--- | :--- | :--- |
| **Unit** | `parse_row()` functions, `models.py` validators | `pytest`, HTML fixtures |
| **Integration** | Live pagination & PDF download for MN / WI | `pytest-playwright` with `--live` marker |
| **Error-path** | Force `expect_download` timeout to assert retries + status=failed | monkey-patch |
| **CI** | Run unit on PR; nightly GitHub cron executes `pytest -m live` in headless & headed modes | GA matrix |

***

## 7. Commit & Security Reminders

*   Adopt **Conventional Commits** `feat:`, `fix:`, `test:`.
*   Never mention Claude or Anthropic in commit messages.
*   Validate all outbound URLs start with the expected domain (MN or WI).
*   Sanitize filenames: ASCII, lower-case, replace spaces with `_`.

***