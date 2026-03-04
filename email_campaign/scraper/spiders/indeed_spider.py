"""
══════════════════════════════════════════════════════════════
  Indeed Spider — JobSpy-powered job scraper for Morocco
══════════════════════════════════════════════════════════════

  Uses the python-jobspy library to scrape Indeed job listings,
  then extracts company emails by visiting company websites.

  Pipeline:
    1. Search Indeed via JobSpy for each keyword
    2. Deduplicate jobs by (company + title)
    3. Visit company websites → extract emails
    4. Fallback: guess website from company name
    5. Return standardized contact dicts

  Usage:
    from email_campaign.scraper.spiders.indeed_spider import run_indeed_spider
    contacts = run_indeed_spider(keywords=["full stack developer"])
"""

import json
import logging
import os
import re
import requests
import warnings
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from ..helpers import (
    make_contact_dict,
    find_relevant_emails,
    extract_emails_from_text,
    extract_domain,
    all_website_guesses,
    CONTACT_PATHS,
    SKIP_DOMAINS,
    SOCIAL_DOMAINS,
)

logger = logging.getLogger(__name__)

# Suppress pandas FutureWarning noise from JobSpy internals
warnings.filterwarnings("ignore", category=FutureWarning, module="jobspy")

# ═══════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════

RESULTS_PER_KEYWORD = 25          # Indeed results per search term
HOURS_OLD = 168                   # Jobs posted in last 7 days
COUNTRY = "Morocco"
LOCATION = "Morocco"

# Max website visits (avoid hammering)
MAX_WEBSITE_VISITS = 80

# Output directory for partial saves
SCRAPER_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scraper_output"
)

# HTTP headers for website visits
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    ),
}


# ═══════════════════════════════════════════════════════════
#  Email Extraction from Company Websites
# ═══════════════════════════════════════════════════════════

def _fetch_emails_from_url(url, domain=''):
    """Fetch a URL and extract emails from response text."""
    try:
        resp = requests.get(
            url, headers=HEADERS, timeout=10,
            verify=False, allow_redirects=True
        )
        if resp.status_code >= 400:
            return []
        return find_relevant_emails(resp.text, domain)
    except Exception as e:
        logger.debug(f"Failed to fetch {url}: {e}")
        return []


def extract_emails_from_website(website_url):
    """
    Visit a company website to find email addresses.
    Checks homepage first, then /contact, /careers pages.
    """
    domain = extract_domain(website_url)
    if not domain:
        return []

    # Skip social / job-board domains
    if any(d in domain for d in SOCIAL_DOMAINS):
        return []

    # Homepage
    emails = _fetch_emails_from_url(website_url, domain)
    if emails:
        return emails

    # Contact pages
    base = website_url.rstrip('/')
    for path in CONTACT_PATHS:
        emails = _fetch_emails_from_url(base + path, domain)
        if emails:
            return emails

    return []


def _find_emails_for_job(company, company_url, description):
    """
    Try multiple strategies to find an email for a job listing:
      1. Emails in the job description text
      2. Visit company_url (if provided by Indeed)
      3. Guess company website (.ma / .com) and visit
    Returns list of emails found (may be empty).
    """
    emails = []

    # Strategy 1: emails in the description
    if description:
        emails = extract_emails_from_text(description)
        if emails:
            return emails[:3]

    # Strategy 2: visit the company URL from Indeed
    if company_url and company_url.startswith('http'):
        emails = extract_emails_from_website(company_url)
        if emails:
            return emails

    # Strategy 3: guess website from company name
    if company:
        guesses = all_website_guesses(company)
        for url in guesses:
            emails = extract_emails_from_website(url)
            if emails:
                return emails

    return []


# ═══════════════════════════════════════════════════════════
#  Incremental Save (crash recovery)
# ═══════════════════════════════════════════════════════════

def _save_partial(contacts):
    """Save contacts to partial file for crash recovery."""
    partial_path = Path(SCRAPER_OUTPUT_DIR) / 'indeed_partial.json'
    try:
        os.makedirs(SCRAPER_OUTPUT_DIR, exist_ok=True)
        partial_path.write_text(
            json.dumps(contacts, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
    except Exception as e:
        logger.debug(f"Failed to save partial: {e}")


# ═══════════════════════════════════════════════════════════
#  Main Spider
# ═══════════════════════════════════════════════════════════

def run_indeed_spider(keywords=None):
    """
    Scrape Indeed Morocco via JobSpy and extract company emails.

    Args:
        keywords: List of search terms. If None, uses runner SEARCH_KEYWORDS.

    Returns:
        List of contact dicts (same format as other spiders).
    """
    from jobspy import scrape_jobs

    if not keywords:
        from ..runner import SEARCH_KEYWORDS
        keywords = SEARCH_KEYWORDS

    all_jobs = {}          # Dedupe key: (company_lower, title_lower)
    contacts = []
    website_visits = 0

    print(f"  🔍 Indeed: searching {len(keywords)} keywords in {COUNTRY}...")

    # ── Phase 1: Collect jobs from all keywords ──
    for i, kw in enumerate(keywords, 1):
        print(f"     [{i}/{len(keywords)}] \"{kw}\"", end="", flush=True)
        try:
            df = scrape_jobs(
                site_name=["indeed"],
                search_term=kw,
                location=LOCATION,
                country_indeed=COUNTRY,
                results_wanted=RESULTS_PER_KEYWORD,
                hours_old=HOURS_OLD,
                is_remote=False,
            )

            new_count = 0
            for _, row in df.iterrows():
                company = str(row.get('company', '') or '').strip()
                title = str(row.get('title', '') or '').strip()
                if not company or not title:
                    continue

                key = (company.lower(), title.lower())
                if key in all_jobs:
                    continue

                all_jobs[key] = {
                    'company': company,
                    'title': title,
                    'location': str(row.get('location', '') or '').strip(),
                    'company_url': str(row.get('company_url', '') or '').strip(),
                    'job_url': str(row.get('job_url', '') or '').strip(),
                    'description': str(row.get('description', '') or '').strip(),
                    'emails': str(row.get('emails', '') or '').strip(),
                }
                new_count += 1

            print(f" → {len(df)} results, {new_count} new")

        except Exception as e:
            err_msg = str(e)
            # Truncate long error messages
            if len(err_msg) > 120:
                err_msg = err_msg[:120] + "..."
            print(f" → ⚠️  {err_msg}")
            continue

    total_jobs = len(all_jobs)
    if total_jobs == 0:
        print(f"  ⚠️  No jobs found on Indeed for {COUNTRY}")
        return []

    print(f"\n  📋 Total unique jobs: {total_jobs}")
    print(f"  🌐 Extracting emails from company websites...\n")

    # ── Phase 2: Extract emails for each job ──
    for idx, ((_, _), job) in enumerate(all_jobs.items(), 1):
        company = job['company']
        title = job['title']
        location = job['location']
        company_url = job['company_url']
        description = job['description']
        job_url = job['job_url']
        jobspy_emails = job['emails']

        # Check if JobSpy already found emails
        emails = []
        if jobspy_emails:
            raw = extract_emails_from_text(jobspy_emails)
            if raw:
                emails = raw[:3]

        # If no emails from JobSpy, try website extraction
        if not emails and website_visits < MAX_WEBSITE_VISITS:
            emails = _find_emails_for_job(company, company_url, description)
            website_visits += 1

        if not emails:
            logger.debug(f"No email found for {company} — {title}")
            continue

        # Create a contact for each email found
        for email in emails:
            contact = make_contact_dict(
                company=company,
                email=email,
                position=title,
                city=location,
                source_url=job_url or company_url,
                source_site='indeed',
                description=description[:500] if description else '',
            )
            contacts.append(contact)
            _save_partial(contacts)

        print(f"     ✅ [{idx}/{total_jobs}] {company} — {emails[0]}")

    # Clean up partial file on success
    partial_path = Path(SCRAPER_OUTPUT_DIR) / 'indeed_partial.json'
    if partial_path.exists():
        try:
            partial_path.unlink()
        except Exception:
            pass

    print(f"\n  📊 Indeed: {len(contacts)} contacts from {total_jobs} jobs")
    return contacts
