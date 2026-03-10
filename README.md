# 📧 Email Campaign Tool — Professional Outreach

**Anti-Spam · Rate-Limited · AI-Powered · Scraper-Integrated · Multi-Language · Auto Follow-Up · Apollo.io Enriched**

A complete email prospection pipeline: scrape Moroccan & MENA job boards for company contacts, auto-detect language per contact, enrich with company research, generate personalized emails with AI in French or English, auto-attach the right CV version, send with rate limiting, monitor replies via IMAP, and automatically follow up.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Workflow — Step by Step](#workflow--step-by-step)
- [CLI Commands Reference](#cli-commands-reference)
  - [Campaign Commands](#campaign-commands)
  - [Scraper Commands](#scraper-commands)
  - [Apollo.io Enrichment](#apolloio-enrichment)
  - [AI Email Generation](#ai-email-generation)
  - [Merge & Integration](#merge--integration)
  - [Follow-Up & Reply Monitoring](#follow-up--reply-monitoring)
- [Project Structure](#project-structure)
- [How the Scraper Works](#how-the-scraper-works)
- [How AI Email Generation Works](#how-ai-email-generation-works)
- [New Features](#new-features)
  - [Apollo.io Integration](#apolloio-integration)
  - [Multi-Language Detection](#multi-language-detection)
  - [Company Research & Enrichment](#company-research--enrichment)
  - [CV Auto-Attachment](#cv-auto-attachment)
  - [Inbox Reply Detection](#inbox-reply-detection)
  - [Auto Follow-Up System](#auto-follow-up-system)
- [Contact File Format](#contact-file-format)
- [Environment Variables](#environment-variables)
- [Examples & Recipes](#examples--recipes)
- [Troubleshooting](#troubleshooting)

---

## Features

| Feature | Description |
|---------|-------------|
| **Apollo.io Integration** | Enrich companies with website, phone, LinkedIn & tech stack (free plan); full HR/CTO contact search (paid plan) |
| **Web Scraping** | Scrape ReKrute, MarocAnnonces, Emploi.ma (Cloudflare bypass), Bayt.com via Scrapling, Indeed Morocco via JobSpy, and LinkedIn |
| **Multi-Step Email Discovery** | Job board → company profile → company website → contact/career pages → email extraction |
| **AI Email Generation** | Auto-generate personalized prospection emails via OpenAI GPT or OpenRouter (Gemini) |
| **Multi-Language Detection** | Auto-detect French or English per contact (TLD, keywords, company name, city analysis) |
| **Company Research** | Auto-scrape company websites for context — technologies, industry, culture — fed to AI for personalization |
| **CV Auto-Attachment** | Drop `cv_fr.pdf` / `cv_en.pdf` in `email_campaign/cv/` — auto-attached per detected language |
| **Smart Sending** | SMTP-based sending with rate limiting, batch pauses, and anti-spam measures |
| **Inbox Reply Detection** | IMAP monitoring — auto-detects replies and marks contacts as "replied" in tracker |
| **Auto Follow-Up** | AI-generated follow-up emails after N days, with max follow-ups per contact |
| **Relevance Scoring** | Contacts scored ⭐ to ⭐⭐⭐ based on job/profile keyword matching |
| **Deduplication** | Automatically skips duplicate emails across scrapes and sends |
| **Send Tracking** | JSON-based tracker remembers what was sent, failed, replied, or pending |
| **Dry Run Mode** | Safe by default — preview everything before actually sending |
| **Centralized Config** | All secrets and settings in a single `.env` file |
| **Retry Failed** | Re-send only previously failed emails |

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌───────────────────┐
│   Web Scraper    │────▶│  AI Email Gen    │────▶│  Email Sender     │
│  (Scrapling +   │     │  (OpenAI/Router) │     │  (SMTP/Gmail)     │
│  JobSpy + PW)   │     └────────┬─────────┘     └────────┬──────────┘
└────────┬────────┘              │                         │
         │                ┌──────┴──────┐           sent_tracker.json
    scraped_contacts      │ Enrichment  │           (send history)
    _latest.md / .json    ├─────────────┤
                          │ Language     │     ┌───────────────────┐
                          │ Detector     │     │  Inbox Monitor    │
                          │ Company      │     │  (IMAP/Gmail)     │
                          │ Researcher   │     └────────┬──────────┘
                          └─────────────┘              │
                                                 reply detection
                          ┌─────────────┐              │
                          │ Follow-Up   │◀─────────────┘
                          │ Generator   │
                          └─────────────┘
```

**Data flow:**
1. **Scrape** → finds companies + emails from job boards + company websites
2. **Merge** → adds new contacts into the main `emails_prospection.md` file
3. **Enrich** → detects language (FR/EN), researches company website for context
4. **Generate** → AI writes personalized email body per contact (in detected language)
5. **Send** → delivers emails via Gmail SMTP with rate limiting + auto-attaches correct CV
6. **Monitor** → checks inbox for replies via IMAP, marks responded contacts
7. **Follow-up** → auto-generates and sends follow-ups to non-responders

---

## Prerequisites

- **Python 3.10+** (tested on 3.14)
- **Gmail account** with [App Password](https://myaccount.google.com/apppasswords) (2FA required)
- **OpenAI API key** or **OpenRouter API key** (for AI email generation)
- **Gmail IMAP enabled** (for reply detection — Settings → Forwarding and POP/IMAP → Enable IMAP)

---

## Installation

```bash
# 1. Clone the project
cd "c:\laragon\www\filter contact"

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 3. Install dependencies
pip install -r email_campaign/requirements.txt

# 4. Set up environment variables
copy .env.example .env
# Edit .env with your actual credentials
```

---

## Configuration

Copy `.env.example` to `.env` at the project root and fill in your values:

```dotenv
# ── SMTP / Gmail ──
EMAIL_USERNAME=your.email@gmail.com
EMAIL_PASSWORD=xxxx xxxx xxxx xxxx       # Gmail App Password (16 chars)

# ── Sender Profile ──
SENDER_NAME=Your Full Name
SENDER_EMAIL=your.email@gmail.com
SENDER_PHONE=+212 600 000 000

# ── AI Providers ──
OPENAI_API_KEY=sk-your-key-here          # Primary AI provider
OPENAI_MODEL=gpt-4o-mini
OPENROUTER_API_KEY=sk-or-v1-your-key     # Fallback AI provider
OPENROUTER_MODEL=google/gemini-2.0-flash-001

# ── Campaign Settings ──
DRY_RUN=true                             # Safe by default
MIN_RELEVANCE_STARS=1                    # 1-3
MAX_EMAILS_PER_DAY=40
MAX_EMAILS_PER_HOUR=15
BATCH_SIZE=10
BATCH_PAUSE_MINUTES=15

# ── CV Paths (optional — see CV Auto-Attachment section) ──
# CV_PATH_FR=email_campaign/cv/cv_fr.pdf
# CV_PATH_EN=email_campaign/cv/cv_en.pdf
```

> ⚠️ **Never commit `.env` to Git!** It's already in `.gitignore`.

---

## Workflow — Step by Step

Here's the full workflow from scratch:

### Step 1: Scrape job boards for contacts

```bash
# Preview what will be scraped (safe, no requests)
python -m email_campaign.main --dry-scrape

# Scrape all supported job boards
python -m email_campaign.main --scrape

# Or scrape a specific site with custom keywords
python -m email_campaign.main --scrape --site rekrute --keywords "react,node.js,full stack"
```

### Step 2: Merge scraped contacts into master file

```bash
# Merge + auto-generate AI email bodies
python -m email_campaign.main --merge-scraped

# Merge only (skip AI generation)
python -m email_campaign.main --merge-scraped --no-generate
```

### Step 3: Generate AI emails (if needed)

```bash
# Generate emails for ALL contacts missing one
python -m email_campaign.main --generate-emails

# Only for high-relevance contacts
python -m email_campaign.main --generate-emails --min-stars 3

# Limit how many to generate
python -m email_campaign.main --generate-emails --limit 10
```

### Step 4: Preview and verify

```bash
# Check campaign status
python -m email_campaign.main --status

# Preview first 5 emails
python -m email_campaign.main --preview 5

# Preview only 3-star contacts
python -m email_campaign.main --preview 10 --min-stars 3
```

### Step 5: Send emails

```bash
# Test your SMTP setup first
python -m email_campaign.main --test

# Dry run (no emails sent, just simulation)
python -m email_campaign.main --limit 5

# Send for real — start with best contacts
python -m email_campaign.main --send --min-stars 3

# Send all remaining contacts
python -m email_campaign.main --send

# Send a limited batch
python -m email_campaign.main --send --limit 20

# Auto-confirm (skip prompts)
python -m email_campaign.main --send --limit 10 -y
```

> **CV auto-attachment:** If `cv_fr.pdf` and/or `cv_en.pdf` exist in `email_campaign/cv/`, they are automatically attached to each email based on detected language. No flag needed.

### Step 6: Monitor replies

```bash
# Check inbox for replies (IMAP)
python -m email_campaign.main --check-replies

# Check last 30 days
python -m email_campaign.main --check-replies --days 30
```

### Step 7: Follow up

```bash
# Follow up with contacts who haven't replied after 5 days (default)
python -m email_campaign.main --follow-up

# Follow up after 7 days, max 1 follow-up per contact
python -m email_campaign.main --follow-up --days 7 --max-followups 1

# Limit to 10 follow-ups per session
python -m email_campaign.main --follow-up --limit 10
```

### Step 8: Handle failures

```bash
# Retry previously failed emails
python -m email_campaign.main --retry-failed
```

---

## CLI Commands Reference

All commands are run with:
```bash
python -m email_campaign.main [OPTIONS]
```

### Campaign Commands

| Command | Description |
|---------|-------------|
| *(no flags)* | **Dry run** — simulates sending, no emails are delivered |
| `--send` | **Send emails** for real |
| `--test` | Send a **test email to yourself** to verify SMTP setup |
| `--status` | Show campaign stats: total, sent, failed, remaining |
| `--preview N` | Preview first N email templates (default: 5) |
| `--retry-failed` | Re-send only previously failed emails |
| `--min-stars N` | Filter contacts by minimum relevance (1, 2, or 3) |
| `--limit N` | Max emails to send in this session |
| `--verbose` | Show detailed output |
| `-y` / `--yes` | Skip confirmation prompt |

### Scraper Commands

| Command | Description |
|---------|-------------|
| `--scrape` | Scrape all job boards (ReKrute, Emploi.ma, MarocAnnonces, Bayt, Indeed, LinkedIn) |
| `--scrape --site rekrute` | Scrape only ReKrute |
| `--scrape --site rekrute emploi_ma` | Scrape multiple specific sites |
| `--scrape --site indeed` | Scrape Indeed Morocco via JobSpy |
| `--scrape --site linkedin` | Scrape LinkedIn hiring posts (Playwright) |
| `--scrape --site indeed,linkedin` | Scrape Indeed + LinkedIn only |
| `--scrape --keywords "react,laravel"` | Override default search keywords |
| `--dry-scrape` | Preview scraper plan without making requests |

**Supported sites:** `rekrute`, `emploi_ma`, `maroc_annonces`, `bayt`, `linkedin`, `indeed`, `apollo`

### Apollo.io Enrichment

> Requires `APOLLO_API_KEY` in `.env`. Free plan unlocks company enrichment; paid plan (Basic $49/mo) unlocks full HR contact search.

| Command | Description |
|---------|-------------|
| `--apollo-enrich` | Enrich contacts with company website, phone, LinkedIn & tech stack (free) |
| `--apollo-enrich --limit 20` | Enrich max 20 contacts per session |
| `--apollo-enrich --min-stars 2` | Only enrich ⭐⭐+ contacts |
| `--apollo-merge` | Scrape Apollo-found websites for email contacts → merge into main file |
| `--apollo-merge --min-stars 2` | Only merge ⭐⭐+ results |
| `--scrape --site apollo` | Full HR/CTO contact search across Morocco (paid plan only) |

**Apollo free plan gives you:**
- 🌐 Company website URL (more accurate than guessing)
- 📞 Phone number (alternative contact channel)
- 💼 LinkedIn company page
- 🏭 Industry + technology stack (richer AI email personalisation)

**Typical Apollo workflow:**
```bash
python main.py --apollo-enrich          # Step 1: enrich company data
python main.py --apollo-merge           # Step 2: scrape websites → new contacts
python main.py --generate-emails        # Step 3: AI email generation
python main.py --send --min-stars 2    # Step 4: send
```

### AI Email Generation

| Command | Description |
|---------|-------------|
| `--generate-emails` | Generate AI emails for contacts missing a body |
| `--generate-emails --min-stars 3` | Only generate for ⭐⭐⭐ contacts |
| `--generate-emails --limit 5` | Generate max 5 emails |
| `--generate-emails --ai-model gpt-4o` | Use a specific OpenAI model |
| `--generate-emails --no-research` | Skip company website research |

### Merge & Integration

| Command | Description |
|---------|-------------|
| `--merge-scraped` | Merge latest scraped contacts into `emails_prospection.md` + auto-generate AI emails |
| `--merge-scraped --no-generate` | Merge contacts only, skip AI email generation |
| `--merge-scraped --min-stars 2` | Only merge contacts with ≥ 2 stars |

### Follow-Up & Reply Monitoring

| Command | Description |
|---------|-------------|
| `--follow-up` | Send follow-up emails to contacts who haven't replied (default: 5 days) |
| `--follow-up --days 7` | Follow up after 7 days instead of 5 |
| `--follow-up --max-followups 1` | Max 1 follow-up per contact (default: 2) |
| `--follow-up --limit 10` | Send max 10 follow-ups per session |
| `--check-replies` | Check inbox (IMAP) for replies to sent emails |
| `--check-replies --days 30` | Check last 30 days of inbox |

---

## Project Structure

```
filter contact/
├── .env                          # Your secrets (not in Git)
├── .env.example                  # Template — copy to .env
├── .gitignore                    # Ignores .env, .venv, logs, etc.
├── emails_prospection.md         # Master contacts + email templates file
├── README.md                     # This file
│
├── email_campaign/               # Python package
│   ├── __init__.py
│   ├── main.py                   # CLI entry point (all commands)
│   ├── config.py                 # Configuration (dataclasses, .env loading)
│   ├── parse_contacts.py         # Parse emails_prospection.md
│   ├── email_sender.py           # SMTP sender with rate limiting + CV attachment
│   ├── tracker.py                # Track sent/failed/replied emails (JSON)
│   ├── language_detector.py      # Auto-detect FR/EN per contact
│   ├── company_researcher.py     # Scrape company websites for AI context
│   ├── inbox_monitor.py          # IMAP inbox monitoring for reply detection
│   ├── followup.py               # Auto follow-up system (AI-generated)
│   ├── requirements.txt          # pip dependencies
│   ├── test_email_preview.py     # Email preview test
│   │
│   ├── cv/                       # CV auto-attachment folder
│   │   ├── README.md             # Instructions
│   │   ├── cv_fr.pdf             # French CV (auto-attached to FR contacts)
│   │   └── cv_en.pdf             # English CV (auto-attached to EN contacts)
│   │
│   ├── scraper/                  # Scrapling-based web scraper
│   │   ├── __init__.py
│   │   ├── runner.py             # Programmatic spider launcher + merge
│   │   ├── email_generator.py    # AI email body generation (OpenAI/OpenRouter)
│   │   ├── helpers.py            # Email extraction, URL guessing, utilities
│   │   ├── post_processing.py    # Deduplication, validation, scoring
│   │   ├── sender_profile.txt    # Your profile for AI prompt context
│   │   │
│   │   └── spiders/              # Scrapling spiders
│   │       ├── job_spider.py     # Unified multi-site spider (ReKrute, Emploi.ma, MarocAnnonces, Bayt)
│   │       ├── indeed_spider.py  # Indeed Morocco spider (powered by JobSpy)
│   │       └── linkedin_spider.py # LinkedIn hiring post spider (Playwright)
│   │
│   ├── scraper_output/           # Scraper output files
│   │   ├── scraped_contacts_latest.md    # Latest scrape (markdown)
│   │   └── scraped_contacts_latest.json  # Latest scrape (JSON)
│   │
│   └── logs/                     # Runtime logs
│       ├── sent_tracker.json     # Which emails were sent/replied
│       └── followup_tracker.json # Follow-up history per contact
│
├── app.js                        # Frontend app (contact filter UI)
├── index.html                    # Frontend HTML
└── style.css                     # Frontend styles
```

---

## How the Scraper Works

The scraper uses **Scrapling** (not Scrapy) with a multi-session architecture for different anti-bot requirements:

- **FetcherSession** (fast HTTP) — ReKrute, MarocAnnonces, Bayt, company websites
- **AsyncStealthySession** (stealth browser with CF bypass) — Emploi.ma
- **JobSpy** (python-jobspy library) — Indeed Morocco (no browser needed)
- **Playwright** (stealth browser with LinkedIn login) — LinkedIn hiring posts

**Multi-step email discovery** strategy:

```
Step 1: Search job board for keywords
         ↓
Step 2: Extract job cards (title, company name, city from URL)
         ↓
Step 3: Follow job detail page → look for emails (rarely found)
         ↓
Step 4: Follow company profile link → find company website URL
         ↓
Step 5: Visit company website homepage → look for emails
         ↓
Step 6: Visit /contact, /careers, /recrutement pages → extract emails
         ↓
Step 7: Yield contact with best email found (rh@, recrutement@, contact@)
```

### Spider Status

| Spider | Site | Status | Notes |
|--------|------|--------|-------|
| `job_spider` (rekrute) | ReKrute.com | ✅ Working | ~12+ contacts per run. Multi-step: job list → detail → company profile → website → contact page |
| `job_spider` (maroc_annonces) | MarocAnnonces.com | ✅ Working | JSON-LD parsing, person name filtering, multi-TLD website guessing |
| `job_spider` (emploi_ma) | Emploi.ma | ✅ Working | Cloudflare Turnstile bypass via Scrapling's stealth browser session |
| `job_spider` (bayt) | Bayt.com | ✅ Working | MENA job board, company profile → website → email extraction |
| `indeed_spider` | Indeed | ✅ Working | Indeed Morocco via JobSpy — multi-keyword search, company website email extraction |
| `linkedin_spider` | LinkedIn | ✅ Working | LinkedIn hiring post detection, feed-scrolling, company website email extraction |

### Relevance Scoring

Contacts are automatically scored based on keyword matching:

| Score | Meaning | Keywords |
|-------|---------|----------|
| ⭐⭐⭐ | Very relevant | react, node.js, javascript, full stack, laravel, php |
| ⭐⭐ | Relevant | java, spring boot, angular, python, devops |
| ⭐ | Less relevant | Everything else |

### Pipeline Chain

Scraped items pass through post-processing in `runner.py` and `post_processing.py`:

1. **Validation** — Drop items with missing/invalid email
2. **Relevance Scoring** — Score 1-3 stars based on keyword matching
3. **Deduplication** — Remove duplicate emails (in-run + cross-merge)
4. **Markdown Export** — Write `.md` file (same format as `emails_prospection.md`)
5. **JSON Export** — Write `.json` for programmatic access

---

## How AI Email Generation Works

Email bodies are generated by AI (OpenAI GPT or OpenRouter as fallback):

1. **Language detection** — Each contact is auto-classified as French or English (see [Multi-Language Detection](#multi-language-detection))
2. **Company research** — The company's website is scraped for context: technologies, industry, culture (see [Company Research](#company-research--enrichment))
3. **Few-shot learning** — The AI receives 3 example emails showing the expected style
4. **Context-rich prompt** — Each prompt includes the company name, position, city, your profile, detected language, and company research
5. **Bilingual output** — Emails are generated in French or English based on auto-detected language
6. **Fallback chain** — If OpenAI returns a quota error (429), it automatically switches to OpenRouter

The generated email follows this structure:
- Professional greeting (adapted to language)
- Mention of the specific position/company
- Your profile summary (Full Stack JS/PHP, YouCode-UM6P)
- Personalized detail from company research (technologies, industry)
- Call to action
- Signature with contact info + icons

---

## New Features

### Apollo.io Integration

The `apollo_spider.py` module connects to the [Apollo.io](https://apollo.io) API to enrich company data and (on paid plans) search for HR & decision-maker contacts directly.

**Free plan — Company Enrichment (`organizations/enrich` + `organizations/search`):**

```bash
python main.py --apollo-enrich     # Enrich all contacts
python main.py --apollo-merge      # Scrape found websites → merge new contacts
```

Saves an `apollo_enrichment.json` sidecar file per contact with:

| Field | Description |
|-------|-------------|
| `apollo_website` | Verified company website URL |
| `apollo_phone` | Company phone number |
| `apollo_linkedin` | LinkedIn company page |
| `apollo_industry` | Industry classification |
| `apollo_employees` | Estimated employee count |
| `apollo_tech` | Technology stack (top 5) |
| `apollo_desc` | Short company description for AI context |

**Paid plan — HR Contact Search (`mixed_people/search`):**

```bash
python main.py --scrape --site apollo   # Search for HR/CTO contacts in Morocco
```

Searches for: HR Managers, DRH, Responsable RH, Talent Acquisition, CTO, CEO, Fondateur — in Casablanca, Rabat, Marrakech, Tanger, Agadir.

**Setup:**
```dotenv
# .env
APOLLO_API_KEY=your_key_here   # Get from app.apollo.io → Settings → API
```

---

### Multi-Language Detection

The `LanguageDetector` class (`language_detector.py`) auto-detects French or English per contact using a weighted scoring system:

| Signal | French indicators | English indicators |
|--------|------------------|--------------------|
| **TLD** | `.ma`, `.fr`, `.tn`, `.dz` | `.io`, `.ai`, `.us`, `.uk` |
| **Keywords** | développeur, stage, recrutement | developer, engineer, internship |
| **Job board** | rekrute.com, emploi.ma | bayt.com, linkedin.com |
| **Company name** | SARL, SA, Groupe | Ltd, Inc, LLC, Corp |
| **City** | Casablanca, Rabat, Marrakech | (Moroccan cities lean French) |

- Default fallback: **French** (Moroccan market)
- Result: `'fr'` or `'en'` — used for email generation, CV selection, and follow-ups

### Company Research & Enrichment

The `CompanyResearcher` class (`company_researcher.py`) auto-scrapes company websites before generating emails:

1. Extracts domain from contact email
2. Fetches homepage + about/contact pages (`/about`, `/a-propos`, `/qui-sommes-nous`, etc.)
3. Extracts: description, technologies used (~50 tech keywords), culture keywords, industry/domain
4. Formats as context block passed to AI prompt → **more personalized emails**

- Uses Python stdlib (`urllib.request`) — no extra dependencies
- Per-domain cache to avoid duplicate requests
- Skips generic email providers (gmail, yahoo, etc.)
- Disable with `--no-research` flag

### CV Auto-Attachment

**Zero config** — just drop your CV PDFs in `email_campaign/cv/`:

```
email_campaign/cv/
├── cv_fr.pdf    ← French version
└── cv_en.pdf    ← English version
```

- **Auto-detected**: If files exist, they're attached. If not, emails send normally.
- **Language-matched**: French contacts get `cv_fr.pdf`, English contacts get `cv_en.pdf`
- **Fallback**: If only one version exists, it's used for all contacts
- **No flag needed**: No `--attach-cv`, no env vars required
- Supports any file type (PDF recommended)
- Can also set paths via `.env`: `CV_PATH_FR=...` and `CV_PATH_EN=...`

### Inbox Reply Detection

The `InboxMonitor` class (`inbox_monitor.py`) connects to Gmail IMAP to detect replies:

```bash
python -m email_campaign.main --check-replies
```

- Connects to Gmail IMAP SSL (`imap.gmail.com:993`)
- Uses same credentials as SMTP (`EMAIL_USERNAME` / `EMAIL_PASSWORD`)
- Searches inbox for emails from contacts you've sent to
- Marks contacts as "replied" in the tracker
- Shows reply stats: `📊 Reply Stats: 5/100 (5.0% reply rate)`
- `--days N` controls how far back to search (default: 30)
- Status command (`--status`) also shows reply count and rate

> **Setup:** Enable IMAP in Gmail: Settings → Forwarding and POP/IMAP → Enable IMAP

### Auto Follow-Up System

The `FollowUpGenerator` and `FollowUpTracker` (`followup.py`) handle automated follow-ups:

```bash
python -m email_campaign.main --follow-up --days 7
```

- **Eligibility**: Contacts who were sent an email > N days ago, haven't replied, and haven't reached max follow-ups
- **AI-generated**: Follow-up emails are shorter and reference the initial email
- **Bilingual**: Uses detected language (FR/EN) for follow-up content
- **Template fallback**: If AI API is unavailable, uses built-in professional templates
- **Rate limited**: Same rate limiting as initial sends
- **Tracked**: Follow-up history stored in `logs/followup_tracker.json`
- **Configurable**: `--days` (default 5), `--max-followups` (default 2), `--limit`

---

## Contact File Format

The `emails_prospection.md` file uses a specific markdown format:

```markdown
### 123. Company Name

- **Email:** contact@company.com
- **Poste:** Full Stack Developer
- **Ville:** Casablanca
- **Pertinence:** ⭐⭐⭐

**Objet:** Candidature spontanée — Développeur Full Stack JS

Bonjour,

Je me permets de vous contacter...

---
```

Each `### N. Company` section is one contact. The parser extracts all fields and the email body (everything after the metadata).

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EMAIL_USERNAME` | For sending | Gmail address |
| `EMAIL_PASSWORD` | For sending | Gmail App Password (16 chars) |
| `SENDER_NAME` | Yes | Your full name |
| `SENDER_EMAIL` | Yes | Your email (used in From header) |
| `SENDER_PHONE` | No | Phone number in email signature |
| `APOLLO_API_KEY` | For Apollo | Apollo.io API key — get at app.apollo.io → Settings → API |
| `OPENAI_API_KEY` | For AI | OpenAI API key |
| `OPENAI_MODEL` | No | Model name (default: `gpt-4o-mini`) |
| `OPENROUTER_API_KEY` | Fallback | OpenRouter API key |
| `OPENROUTER_MODEL` | No | Model name (default: `google/gemini-2.0-flash-001`) |
| `DRY_RUN` | No | `true`/`false` (default: `true`) |
| `MIN_RELEVANCE_STARS` | No | 1-3 (default: `1`) |
| `MAX_EMAILS_PER_DAY` | No | Daily send limit (default: `40`) |
| `MAX_EMAILS_PER_HOUR` | No | Hourly send limit (default: `15`) |
| `BATCH_SIZE` | No | Emails per batch (default: `10`) |
| `BATCH_PAUSE_MINUTES` | No | Pause between batches (default: `15`) |
| `CV_PATH_FR` | No | Path to French CV (default: auto-detect `cv/cv_fr.pdf`) |
| `CV_PATH_EN` | No | Path to English CV (default: auto-detect `cv/cv_en.pdf`) |
| `IMAP_HOST` | No | IMAP server (default: `imap.gmail.com`) |
| `IMAP_PORT` | No | IMAP port (default: `993`) |

---

## Examples & Recipes

### Full pipeline from zero

```bash
# 1. Scrape ReKrute + Indeed for web developer jobs
python -m email_campaign.main --scrape --site rekrute,indeed --keywords "développeur web,full stack,react"

# 2. Merge into master file + generate AI emails (with language detection + company research)
python -m email_campaign.main --merge-scraped

# 3. Check what we have
python -m email_campaign.main --status

# 4. Preview the best contacts
python -m email_campaign.main --preview 5 --min-stars 3

# 5. Test SMTP first
python -m email_campaign.main --test

# 6. Send to 3-star contacts (CV auto-attached if found in cv/)
python -m email_campaign.main --send --min-stars 3

# 7. Send remaining in batches of 10
python -m email_campaign.main --send --limit 10

# 8. Check for replies after a few days
python -m email_campaign.main --check-replies

# 9. Follow up with non-responders
python -m email_campaign.main --follow-up --days 5
```

### Quick daily routine

```bash
# Check progress + reply stats
python -m email_campaign.main --status

# Check inbox for new replies
python -m email_campaign.main --check-replies

# Send follow-ups to non-responders
python -m email_campaign.main --follow-up

# Scrape for new contacts (all sites incl. Indeed & LinkedIn)
python -m email_campaign.main --scrape

# Merge + AI generate
python -m email_campaign.main --merge-scraped

# Send a batch
python -m email_campaign.main --send --limit 15
```

### Generate emails for only high-value contacts

```bash
python -m email_campaign.main --generate-emails --min-stars 3 --limit 10 --ai-model gpt-4o
```

### Retry failed emails

```bash
python -m email_campaign.main --retry-failed --send
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `SMTP credentials not configured` | Set `EMAIL_USERNAME` and `EMAIL_PASSWORD` in `.env` |
| `OpenAI 429 RateLimitError` | Your OpenAI account has no credits. Add an `OPENROUTER_API_KEY` as fallback |
| `Scraper finds 0 contacts` | Normal — many company websites block bots (403). The scraper tries multiple TLDs (.ma, .com, .fr) |
| `Emploi.ma returns 403` | Make sure Scrapling stealth browser dependencies are installed (`scrapling[all]`) |
| `DNS lookup failed` | The guessed company URL doesn't exist — this is expected, the scraper tries multiple variants |
| `Gmail "Less secure apps"` | Use App Passwords instead — enable 2FA first at [myaccount.google.com](https://myaccount.google.com/apppasswords) |
| `Duplicate email skipped` | The deduplication system prevents sending the same email twice |
| `IMAP login failed` | Enable IMAP in Gmail: Settings → Forwarding and POP/IMAP → Enable IMAP. Use App Password. |
| `CV not attached` | Place `cv_fr.pdf` / `cv_en.pdf` in `email_campaign/cv/`. No other config needed. |
| `Follow-up finds 0 eligible` | Contacts must be sent > N days ago, not replied, and under max follow-ups |

---

## License

Private project — not for redistribution.
