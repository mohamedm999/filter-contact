# 📧 Email Campaign Tool — Professional Outreach

**Anti-Spam · Rate-Limited · AI-Powered · Scraper-Integrated**

A complete email prospection pipeline: scrape Moroccan job boards for company contacts, generate personalized email bodies with AI, and send them with built-in rate limiting and tracking.

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
  - [AI Email Generation](#ai-email-generation)
  - [Merge & Integration](#merge--integration)
- [Project Structure](#project-structure)
- [How the Scraper Works](#how-the-scraper-works)
- [How AI Email Generation Works](#how-ai-email-generation-works)
- [Contact File Format](#contact-file-format)
- [Environment Variables](#environment-variables)
- [Examples & Recipes](#examples--recipes)
- [Troubleshooting](#troubleshooting)

---

## Features

| Feature | Description |
|---------|-------------|
| **Web Scraping** | Scrape ReKrute.com and MarocAnnonces.com for company emails. Emploi.ma is placeholder (Cloudflare Turnstile) |
| **Multi-Step Email Discovery** | Job board → company profile → company website → contact/career pages → email extraction |
| **AI Email Generation** | Auto-generate personalized French prospection emails via OpenAI GPT or OpenRouter (Gemini) |
| **Smart Sending** | SMTP-based sending with rate limiting, batch pauses, and anti-spam measures |
| **Relevance Scoring** | Contacts scored ⭐ to ⭐⭐⭐ based on job/profile keyword matching |
| **Deduplication** | Automatically skips duplicate emails across scrapes and sends |
| **Send Tracking** | JSON-based tracker remembers what was sent, failed, or pending |
| **Dry Run Mode** | Safe by default — preview everything before actually sending |
| **Centralized Config** | All secrets and settings in a single `.env` file |
| **Retry Failed** | Re-send only previously failed emails |

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌───────────────────┐
│   Web Scraper    │────▶│  AI Email Gen    │────▶│  Email Sender     │
│  (Scrapy)        │     │  (OpenAI/Router) │     │  (SMTP/Gmail)     │
└────────┬────────┘     └────────┬─────────┘     └────────┬──────────┘
         │                       │                         │
    scraped_contacts         emails_prospection.md     sent_tracker.json
    _latest.md / .json       (unified contacts file)   (send history)
```

**Data flow:**
1. **Scrape** → finds companies + emails from job boards + company websites
2. **Merge** → adds new contacts into the main `emails_prospection.md` file
3. **Generate** → AI writes personalized email body for each contact
4. **Send** → delivers emails via Gmail SMTP with rate limiting

---

## Prerequisites

- **Python 3.10+** (tested on 3.14)
- **Gmail account** with [App Password](https://myaccount.google.com/apppasswords) (2FA required)
- **OpenAI API key** or **OpenRouter API key** (for AI email generation)

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

### Step 6: Handle failures

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
| `--scrape` | Scrape all job boards (ReKrute, Emploi.ma, MarocAnnonces) |
| `--scrape --site rekrute` | Scrape only ReKrute |
| `--scrape --site rekrute emploi_ma` | Scrape multiple specific sites |
| `--scrape --keywords "react,laravel"` | Override default search keywords |
| `--dry-scrape` | Preview scraper plan without making requests |

**Supported sites:** `rekrute`, `emploi_ma` (placeholder — needs CF bypass), `maroc_annonces`

### AI Email Generation

| Command | Description |
|---------|-------------|
| `--generate-emails` | Generate AI emails for contacts missing a body |
| `--generate-emails --min-stars 3` | Only generate for ⭐⭐⭐ contacts |
| `--generate-emails --limit 5` | Generate max 5 emails |
| `--generate-emails --ai-model gpt-4o` | Use a specific OpenAI model |

### Merge & Integration

| Command | Description |
|---------|-------------|
| `--merge-scraped` | Merge latest scraped contacts into `emails_prospection.md` + auto-generate AI emails |
| `--merge-scraped --no-generate` | Merge contacts only, skip AI email generation |
| `--merge-scraped --min-stars 2` | Only merge contacts with ≥ 2 stars |

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
│   ├── email_sender.py           # SMTP sender with rate limiting
│   ├── tracker.py                # Track sent/failed emails (JSON)
│   ├── requirements.txt          # pip dependencies
│   │
│   ├── scraper/                  # Scrapy-based web scraper
│   │   ├── __init__.py
│   │   ├── settings.py           # Scrapy settings (delays, pipelines)
│   │   ├── items.py              # JobContactItem data model
│   │   ├── pipelines.py          # Validation → Scoring → Dedup → Export
│   │   ├── runner.py             # Programmatic spider launcher + merge
│   │   ├── email_generator.py    # AI email body generation (OpenAI/OpenRouter)
│   │   │
│   │   └── spiders/              # One spider per job board
│   │       ├── base.py           # Base spider (email extraction, shared logic)
│   │       ├── rekrute_spider.py # ReKrute.com spider ✅ working
│   │       ├── emploi_ma_spider.py       # Emploi.ma spider ⏳ placeholder (CF bypass needed)
│   │       └── maroc_annonces_spider.py  # MarocAnnonces.com spider ✅ working
│   │
│   ├── scraper_output/           # Scraper output files
│   │   ├── scraped_contacts_latest.md    # Latest scrape (markdown)
│   │   └── scraped_contacts_latest.json  # Latest scrape (JSON)
│   │
│   └── logs/                     # Runtime logs
│       ├── sent_tracker.json     # Which emails were sent
│       └── campaign_YYYYMMDD.log # Daily log files
│
├── app.js                        # Frontend app (contact filter UI)
├── index.html                    # Frontend HTML
└── style.css                     # Frontend styles
```

---

## How the Scraper Works

The scraper uses a **multi-step email discovery** strategy because Moroccan job boards don't expose recruiter emails directly:

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
| `rekrute_spider` | ReKrute.com | ✅ Working | ~12+ contacts per run. Multi-step: job list → detail → company profile → website → contact page |
| `maroc_annonces_spider` | MarocAnnonces.com | ✅ Working | ~3 contacts per run. JSON-LD parsing, person name filtering, multi-TLD website guessing |
| `emploi_ma_spider` | Emploi.ma | ⏳ Placeholder | Cloudflare Turnstile blocks all automation. Parse methods are ready — needs custom CF bypass in `start_requests()` |

### Relevance Scoring

Contacts are automatically scored based on keyword matching:

| Score | Meaning | Keywords |
|-------|---------|----------|
| ⭐⭐⭐ | Very relevant | react, node.js, javascript, full stack, laravel, php |
| ⭐⭐ | Relevant | java, spring boot, angular, python, devops |
| ⭐ | Less relevant | Everything else |

### Pipeline Chain

Scraped items pass through 5 pipelines in order:

1. **ValidationPipeline** — Drop items with missing/invalid email
2. **RelevanceScoringPipeline** — Score 1-3 stars
3. **DeduplicationPipeline** — Remove duplicate emails
4. **MarkdownExportPipeline** — Write `.md` file (same format as `emails_prospection.md`)
5. **JsonExportPipeline** — Write `.json` for programmatic access

---

## How AI Email Generation Works

Email bodies are generated by AI (OpenAI GPT or OpenRouter as fallback):

1. **Few-shot learning** — The AI receives 3 example emails showing the expected style
2. **Context** — Each prompt includes the company name, position, city, and your profile
3. **French output** — Emails are generated in professional French
4. **Fallback chain** — If OpenAI returns a quota error (429), it automatically switches to OpenRouter

The generated email follows this structure:
- Professional greeting
- Mention of the specific position/company
- Your profile summary (Full Stack JS/PHP, YouCode-UM6P)
- Call to action
- Signature with contact info

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

---

## Examples & Recipes

### Full pipeline from zero

```bash
# 1. Scrape ReKrute for web developer jobs
python -m email_campaign.main --scrape --site rekrute --keywords "développeur web,full stack,react"

# 2. Merge into master file + generate AI emails
python -m email_campaign.main --merge-scraped

# 3. Check what we have
python -m email_campaign.main --status

# 4. Preview the best contacts
python -m email_campaign.main --preview 5 --min-stars 3

# 5. Test SMTP first
python -m email_campaign.main --test

# 6. Send to 3-star contacts
python -m email_campaign.main --send --min-stars 3

# 7. Send remaining in batches of 10
python -m email_campaign.main --send --limit 10
```

### Quick daily routine

```bash
# Check progress
python -m email_campaign.main --status

# Scrape for new contacts
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
| `Emploi.ma returns 403` | Cloudflare Turnstile blocks all automated requests. The spider is a placeholder — plug in your own bypass script |
| `DNS lookup failed` | The guessed company URL doesn't exist — this is expected, the scraper tries multiple variants |
| `Pydantic V1 warning` | Harmless warning on Python 3.14 — can be ignored |
| `Gmail "Less secure apps"` | Use App Passwords instead — enable 2FA first at [myaccount.google.com](https://myaccount.google.com/apppasswords) |
| `Duplicate email skipped` | The deduplication pipeline prevents sending the same email twice |

---

## License

Private project — not for redistribution.
