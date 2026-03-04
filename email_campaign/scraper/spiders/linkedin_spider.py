"""
══════════════════════════════════════════════════════════════
  LinkedIn Spider — Playwright-Based Company & Job Scraper
══════════════════════════════════════════════════════════════

  Unlike the other spiders (ReKrute, Bayt, etc.) that use
  Scrapling's HTTP sessions, LinkedIn requires:
    1. Real browser login with credentials
    2. Session persistence (cookies + localStorage)
    3. Anti-detection (human-like delays, headless Chromium)

  This spider uses Playwright directly to:
    • Search for companies in Morocco by keyword
    • Scrape company details (name, website, industry, location)
    • Scrape job listings per company
    • Feed discovered company websites into the email extraction
      pipeline (FetcherSession → homepage + /contact pages)

  Session stored in: linkedin_session.json (auto-gitignored)

  CLI:
    python main.py --scrape --site linkedin
    python main.py --scrape --site linkedin --keywords "react,node.js"
"""

import os
import re
import json
import time
import random
import asyncio
import logging
from pathlib import Path
from urllib.parse import quote_plus

from ..helpers import (
    make_contact_dict, find_relevant_emails, extract_emails_from_text,
    find_external_website, guess_website, extract_domain,
    SOCIAL_DOMAINS, CONTACT_PATHS,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════

SESSION_FILE = Path(__file__).resolve().parent.parent / "linkedin_session.json"

# Morocco geoId for LinkedIn searches
MOROCCO_GEO_ID = "102787409"

# LinkedIn domains to skip when looking for external company websites
LINKEDIN_SKIP_DOMAINS = SOCIAL_DOMAINS | {
    'linkedin.com', 'licdn.com',
}

# CSS selectors (LinkedIn's class names change — update if broken)
SELECTORS = {
    # Company search results
    'company_card': '.reusable-search__result-container',
    'company_link': 'a.app-aware-link[href*="/company/"]',
    'company_name': '.entity-result__title-text a span',

    # Company about page
    'company_about_website': 'a[data-test-id="about-us__website"] dd a',
    'company_website_link': '.link-without-visited-state[href]',
    'company_industry': '.org-top-card-summary-info-list__info-item',
    'company_location': '.org-top-card-summary-info-list__info-item',
    'company_description': '.org-page-details__definition-text',

    # Job search
    'job_card': '.job-card-container',
    'job_link': 'a[href*="/jobs/view/"]',
    'job_title': '.job-card-list__title--link',
    'job_company': '.artdeco-entity-lockup__subtitle',
    'job_location': '.artdeco-entity-lockup__caption',

    # Job detail page
    'job_detail_title': '.t-24.t-bold.inline',
    'job_detail_company': '.jobs-unified-top-card__company-name a',
    'job_detail_location': '.jobs-unified-top-card__bullet',
    'job_detail_description': '#job-details',
}

# Default search keywords (same as other spiders)
DEFAULT_KEYWORDS = [
    "développeur full stack",
    "développeur web",
    "full stack developer",
    "frontend developer",
    "backend developer",
    "react developer",
    "node.js developer",
    "devops",
]


# ═══════════════════════════════════════════════════════════
#  Session Management
# ═══════════════════════════════════════════════════════════

async def save_session(context):
    """Save browser session (cookies + localStorage) to file."""
    try:
        cookies = await context.cookies()
        # Get localStorage from the LinkedIn page
        local_storage = {}
        pages = context.pages
        if pages:
            try:
                local_storage = await pages[0].evaluate("""
                    () => {
                        const items = {};
                        for (let i = 0; i < localStorage.length; i++) {
                            const key = localStorage.key(i);
                            items[key] = localStorage.getItem(key);
                        }
                        return items;
                    }
                """)
            except Exception:
                pass

        session_data = {
            'cookies': cookies,
            'localStorage': local_storage,
            'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        SESSION_FILE.write_text(json.dumps(session_data, indent=2), encoding='utf-8')
        logger.info(f"Session saved ({len(cookies)} cookies)")
    except Exception as e:
        logger.warning(f"Failed to save session: {e}")


async def load_session(context):
    """Load saved session (cookies + localStorage) into browser context."""
    if not SESSION_FILE.exists():
        return False

    try:
        data = json.loads(SESSION_FILE.read_text(encoding='utf-8'))
        cookies = data.get('cookies', [])
        local_storage = data.get('localStorage', {})

        if cookies:
            await context.add_cookies(cookies)
            logger.info(f"Loaded {len(cookies)} cookies from session")

        # Navigate to LinkedIn first, then restore localStorage
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto('https://www.linkedin.com', wait_until='domcontentloaded',
                        timeout=30000)
        await asyncio.sleep(2)

        if local_storage:
            await page.evaluate("""
                (items) => {
                    for (const [key, value] of Object.entries(items)) {
                        localStorage.setItem(key, value);
                    }
                }
            """, local_storage)
            logger.info(f"Restored {len(local_storage)} localStorage items")

        return True
    except Exception as e:
        logger.warning(f"Failed to load session: {e}")
        return False


async def is_logged_in(page):
    """Check if the current page is a logged-in LinkedIn session."""
    try:
        url = page.url
        # If we're on the feed or any non-login page, we're logged in
        if '/feed' in url or '/mynetwork' in url or '/messaging' in url:
            return True
        # Check for the feed nav element
        feed_link = await page.query_selector('a[href*="/feed"]')
        if feed_link:
            return True
        # Check for login form (means NOT logged in)
        login_form = await page.query_selector('#session_key')
        if login_form:
            return False
        return False
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════
#  Human-Like Behaviour
# ═══════════════════════════════════════════════════════════

async def human_delay(min_sec=1.5, max_sec=4.0):
    """Wait a random human-like interval."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def human_type(page, selector, text):
    """Type text into an input field with human-like delays."""
    element = await page.wait_for_selector(selector, timeout=10000)
    await element.click()
    await asyncio.sleep(0.3)
    for char in text:
        await element.type(char, delay=random.randint(50, 150))
    await asyncio.sleep(0.5)


async def scroll_page(page, scrolls=3):
    """Scroll the page down to load lazy content."""
    for _ in range(scrolls):
        await page.evaluate('window.scrollBy(0, window.innerHeight * 0.7)')
        await asyncio.sleep(random.uniform(0.8, 1.5))


# ═══════════════════════════════════════════════════════════
#  Login Flow
# ═══════════════════════════════════════════════════════════

async def login(page, email, password):
    """
    Login to LinkedIn with credentials.
    Handles the verification PIN step if triggered.
    Returns True if login was successful.
    """
    logger.info("Attempting LinkedIn login...")
    await page.goto('https://www.linkedin.com/login', wait_until='domcontentloaded',
                    timeout=30000)
    await human_delay(2, 4)

    # Fill email
    await human_type(page, '#username', email)
    await human_delay(0.5, 1.0)

    # Fill password
    await human_type(page, '#password', password)
    await human_delay(0.5, 1.5)

    # Click login button
    await page.click('button[type="submit"]')
    await human_delay(3, 6)

    # Check if PIN verification is required
    pin_input = await page.query_selector('input[name="pin"]')
    if pin_input:
        print("\n  ⚠️  LinkedIn requires PIN verification!")
        print("  Check your email for the verification code.")
        pin = input("  Enter PIN: ").strip()
        if pin:
            await human_type(page, 'input[name="pin"]', pin)
            await human_delay(0.5, 1.0)
            submit_btn = await page.query_selector(
                'button[type="submit"], #email-pin-submit-button'
            )
            if submit_btn:
                await submit_btn.click()
                await human_delay(3, 5)

    # Verify login success
    logged_in = await is_logged_in(page)
    if logged_in:
        logger.info("LinkedIn login successful")
    else:
        logger.error("LinkedIn login failed")
    return logged_in


# ═══════════════════════════════════════════════════════════
#  Company Search & Scraping
# ═══════════════════════════════════════════════════════════

async def search_companies(page, keyword, max_pages=3):
    """
    Search LinkedIn for companies in Morocco matching keyword.
    Returns list of company dicts with name, url, linkedin_id.
    """
    companies = []
    seen_urls = set()

    for page_num in range(1, max_pages + 1):
        url = (
            f"https://www.linkedin.com/search/results/companies/"
            f"?keywords={quote_plus(keyword)}"
            f"&geoUrn=%5B%22{MOROCCO_GEO_ID}%22%5D"
            f"&origin=FACETED_SEARCH"
            f"&page={page_num}"
        )

        logger.info(f"[LinkedIn] Company search: '{keyword}' page {page_num}")
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await human_delay(2, 4)
        await scroll_page(page, scrolls=3)

        # Extract company cards
        cards = await page.query_selector_all(
            '.reusable-search__result-container'
        )
        if not cards:
            # Try alternative selector
            cards = await page.query_selector_all(
                '[data-view-name="search-entity-result-universal-template"]'
            )

        if not cards:
            logger.info(f"[LinkedIn] No more company results on page {page_num}")
            break

        for card in cards:
            try:
                # Get company link
                link_el = await card.query_selector(
                    'a.app-aware-link[href*="/company/"]'
                )
                if not link_el:
                    continue

                href = await link_el.get_attribute('href')
                if not href or '/company/' not in href:
                    continue

                # Extract company slug from URL
                match = re.search(r'/company/([^/?]+)', href)
                if not match:
                    continue
                slug = match.group(1)

                company_url = f"https://www.linkedin.com/company/{slug}/"
                if company_url in seen_urls:
                    continue
                seen_urls.add(company_url)

                # Get company name
                name_el = await card.query_selector(
                    '.entity-result__title-text a span'
                )
                name = ''
                if name_el:
                    name = (await name_el.inner_text()).strip()
                if not name:
                    name = slug.replace('-', ' ').title()

                # Get subtitle (industry/location)
                subtitle_el = await card.query_selector(
                    '.entity-result__primary-subtitle'
                )
                industry = ''
                if subtitle_el:
                    industry = (await subtitle_el.inner_text()).strip()

                companies.append({
                    'name': name,
                    'url': company_url,
                    'slug': slug,
                    'industry': industry,
                })

            except Exception as e:
                logger.debug(f"Error parsing company card: {e}")
                continue

        logger.info(
            f"[LinkedIn] Found {len(companies)} companies so far "
            f"(page {page_num})"
        )
        await human_delay(2, 5)

    return companies


async def scrape_company_about(page, company):
    """
    Visit a company's /about/ page to extract:
      - Company website URL
      - Industry, location, description
    Returns updated company dict or None if failed.
    """
    about_url = company['url'].rstrip('/') + '/about/'
    logger.info(f"[LinkedIn] Scraping company: {company['name']} → {about_url}")

    try:
        await page.goto(about_url, wait_until='domcontentloaded', timeout=30000)
        await human_delay(2, 4)
        await scroll_page(page, scrolls=2)
    except Exception as e:
        logger.warning(f"Failed to load {about_url}: {e}")
        return None

    info = dict(company)  # Copy original data

    # ── Extract website ──
    website = None
    try:
        # Method 1: Look for the website link in the about section
        website_links = await page.query_selector_all(
            '.link-without-visited-state[href]'
        )
        for link_el in website_links:
            href = await link_el.get_attribute('href')
            if href and 'linkedin.com' not in href and href.startswith('http'):
                # Skip social media links
                if not any(d in href.lower() for d in LINKEDIN_SKIP_DOMAINS):
                    website = href
                    break

        # Method 2: Look in dt/dd pairs (About section)
        if not website:
            dds = await page.query_selector_all('dd a[href]')
            for dd in dds:
                href = await dd.get_attribute('href')
                if href and 'linkedin.com' not in href and href.startswith('http'):
                    if not any(d in href.lower() for d in LINKEDIN_SKIP_DOMAINS):
                        website = href
                        break

        # Method 3: Extract from page text using regex
        if not website:
            text = await page.inner_text('body')
            url_pattern = re.compile(
                r'https?://(?:www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?'
            )
            for match in url_pattern.finditer(text):
                url = match.group()
                if 'linkedin.com' not in url and not any(
                    d in url.lower() for d in LINKEDIN_SKIP_DOMAINS
                ):
                    website = url
                    break

    except Exception as e:
        logger.debug(f"Error extracting website: {e}")

    info['website'] = website

    # ── Extract location ──
    try:
        location_items = await page.query_selector_all(
            '.org-top-card-summary-info-list__info-item'
        )
        for item in location_items:
            text = (await item.inner_text()).strip()
            if any(city in text.lower() for city in [
                'casablanca', 'rabat', 'marrakech', 'tanger', 'fes', 'fès',
                'agadir', 'oujda', 'kenitra', 'tetouan', 'morocco', 'maroc',
                'mohammedia', 'sale', 'salé', 'meknes', 'meknès', 'el jadida',
            ]):
                info['location'] = text
                break
    except Exception:
        pass

    # ── Extract description ──
    try:
        desc_el = await page.query_selector(
            '.org-page-details__definition-text, '
            'section.org-about-module__margin-bottom p'
        )
        if desc_el:
            info['description'] = (await desc_el.inner_text()).strip()[:500]
    except Exception:
        pass

    return info


# ═══════════════════════════════════════════════════════════
#  Job Scraping
# ═══════════════════════════════════════════════════════════

def extract_company_linkedin_id(html_content):
    """
    Extract the numeric LinkedIn company ID from page HTML.
    Tries multiple regex patterns (LinkedIn embeds this in various places).
    """
    patterns = [
        r'urn:li:fsd_company:(\d+)',
        r'"companyId":(\d+)',
        r'"objectUrn":"urn:li:company:(\d+)"',
        r'f_C=(\d+)',
        r'/company/(\d+)',
        r'"companyUrn":"urn:li:fs_miniCompany:(\d+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_content)
        if match:
            return match.group(1)
    return None


async def scrape_company_jobs(page, company, max_pages=3):
    """
    Scrape job listings for a specific company on LinkedIn.
    Returns list of job dicts with title, location, description.
    """
    jobs = []
    linkedin_id = None

    # First, get the numeric company ID from the company page
    try:
        await page.goto(company['url'], wait_until='domcontentloaded',
                        timeout=30000)
        await human_delay(2, 3)
        html = await page.content()
        linkedin_id = extract_company_linkedin_id(html)
    except Exception as e:
        logger.warning(f"Failed to get company ID for {company['name']}: {e}")

    if not linkedin_id:
        # Try the slug-based jobs URL instead
        jobs_url = company['url'].rstrip('/') + '/jobs/'
        logger.info(f"[LinkedIn] No company ID, trying slug jobs URL: {jobs_url}")
    else:
        logger.info(
            f"[LinkedIn] Company ID for {company['name']}: {linkedin_id}"
        )

    seen_job_urls = set()

    for page_num in range(max_pages):
        start = page_num * 25

        if linkedin_id:
            url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?f_C={linkedin_id}"
                f"&geoId={MOROCCO_GEO_ID}"
                f"&start={start}"
            )
        else:
            url = company['url'].rstrip('/') + f'/jobs/?start={start}'

        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await human_delay(2, 4)
            await scroll_page(page, scrolls=3)
        except Exception as e:
            logger.warning(f"Failed to load jobs page {page_num}: {e}")
            break

        # Extract job cards
        job_cards = await page.query_selector_all(
            '.job-card-container, '
            '.jobs-search-results__list-item, '
            '[data-view-name="job-card"]'
        )

        if not job_cards:
            logger.info(f"[LinkedIn] No more jobs on page {page_num + 1}")
            break

        for card in job_cards:
            try:
                # Get job link
                link_el = await card.query_selector(
                    'a[href*="/jobs/view/"]'
                )
                if not link_el:
                    continue

                href = await link_el.get_attribute('href')
                if not href:
                    continue

                # Normalize URL
                job_match = re.search(r'/jobs/view/(\d+)', href)
                if not job_match:
                    continue
                job_id = job_match.group(1)
                job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"

                if job_url in seen_job_urls:
                    continue
                seen_job_urls.add(job_url)

                # Get job title
                title_el = await card.query_selector(
                    '.job-card-list__title--link, '
                    '.job-card-container__link, '
                    'a[href*="/jobs/view/"] span'
                )
                title = ''
                if title_el:
                    title = (await title_el.inner_text()).strip()

                # Get location
                location_el = await card.query_selector(
                    '.artdeco-entity-lockup__caption, '
                    '.job-card-container__metadata-wrapper span'
                )
                location = ''
                if location_el:
                    location = (await location_el.inner_text()).strip()

                jobs.append({
                    'url': job_url,
                    'title': title or 'Unknown Position',
                    'location': location,
                    'job_id': job_id,
                })

            except Exception as e:
                logger.debug(f"Error parsing job card: {e}")
                continue

        logger.info(
            f"[LinkedIn] Found {len(jobs)} jobs for "
            f"{company['name']} (page {page_num + 1})"
        )
        await human_delay(2, 5)

    return jobs


async def scrape_job_details(page, job):
    """
    Visit a job detail page to get the full description.
    Returns updated job dict with description added.
    """
    try:
        await page.goto(job['url'], wait_until='domcontentloaded', timeout=30000)
        await human_delay(2, 3)
        await scroll_page(page, scrolls=2)

        info = dict(job)

        # Get full description
        desc_el = await page.query_selector(
            '#job-details, '
            '.jobs-description-content__text, '
            'article[class*="jobs-description"]'
        )
        if desc_el:
            info['description'] = (await desc_el.inner_text()).strip()[:1000]
        else:
            info['description'] = ''

        # Get job title (more accurate from detail page)
        title_el = await page.query_selector(
            '.t-24.t-bold.inline, '
            '.jobs-unified-top-card__job-title, '
            'h1'
        )
        if title_el:
            title = (await title_el.inner_text()).strip()
            if title:
                info['title'] = title

        return info

    except Exception as e:
        logger.warning(f"Failed to scrape job details: {e}")
        return job


# ═══════════════════════════════════════════════════════════
#  Company Website → Email Extraction (reuses existing pipeline)
# ═══════════════════════════════════════════════════════════

async def extract_emails_from_website(website_url, company_info, jobs):
    """
    Visit a company's actual website (not LinkedIn) to find email addresses.
    Uses requests for fast HTTP with a short timeout (avoids Fetcher's slow
    30s timeout × 3 retries per dead site).

    Returns list of contact dicts.
    """
    import requests as _requests

    contacts = []
    seen_emails = set()
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        ),
    }

    domain = extract_domain(website_url)
    if not domain:
        return contacts

    def _add_contacts(emails_found):
        """Helper to create contact dicts from found emails."""
        for email in emails_found:
            if email not in seen_emails:
                seen_emails.add(email)
                if jobs:
                    for job in jobs:
                        contacts.append(make_contact_dict(
                            company=company_info.get('name', ''),
                            email=email,
                            position=job.get('title', ''),
                            city=job.get('location', company_info.get('location', '')),
                            source_url=job.get('url', company_info.get('url', '')),
                            source_site='linkedin',
                            description=job.get('description', ''),
                        ))
                else:
                    contacts.append(make_contact_dict(
                        company=company_info.get('name', ''),
                        email=email,
                        position=company_info.get('industry', ''),
                        city=company_info.get('location', ''),
                        source_url=company_info.get('url', ''),
                        source_site='linkedin',
                        description=company_info.get('description', ''),
                    ))

    # ── Visit homepage ──
    try:
        resp = _requests.get(website_url, headers=headers, timeout=10,
                             verify=False, allow_redirects=True)
        emails = find_relevant_emails(resp.text, domain)
        _add_contacts(emails)
    except Exception as e:
        logger.debug(f"Failed to fetch homepage {website_url}: {e}")

    # ── Visit contact pages if no emails on homepage ──
    if not seen_emails:
        base_url = website_url.rstrip('/')
        for path in CONTACT_PATHS:
            try:
                resp = _requests.get(base_url + path, headers=headers,
                                     timeout=10, verify=False,
                                     allow_redirects=True)
                if resp.status_code >= 400:
                    continue
                emails = find_relevant_emails(resp.text, domain)
                _add_contacts(emails)

                if seen_emails:
                    break  # Found emails, stop checking other contact paths
            except Exception:
                continue

    return contacts


# ═══════════════════════════════════════════════════════════
#  Main Orchestrator
# ═══════════════════════════════════════════════════════════

async def run_linkedin_spider(keywords=None, max_company_pages=3,
                              max_job_pages=2, max_job_details=5):
    """
    Run the full LinkedIn scraping pipeline:
      1. Login / restore session
      2. Search companies by keyword in Morocco
      3. For each company: scrape /about/ for website URL
      4. For each company: scrape job listings
      5. Visit company websites → extract emails
      6. Return list of contact dicts

    Args:
        keywords:          List of keywords (None = defaults)
        max_company_pages: Max pages of company search results per keyword
        max_job_pages:     Max pages of job listings per company
        max_job_details:   Max job detail pages to visit per company

    Returns:
        List of contact dicts (same format as other spiders)
    """
    from playwright.async_api import async_playwright

    keywords = keywords or DEFAULT_KEYWORDS
    all_contacts = []
    stats = {
        'companies_found': 0,
        'companies_with_website': 0,
        'jobs_found': 0,
        'emails_found': 0,
    }

    # ── Get LinkedIn credentials from env ──
    li_email = os.getenv('LINKEDIN_EMAIL', '')
    li_password = os.getenv('LINKEDIN_PASSWORD', '')

    if not li_email or not li_password:
        print("\n  ⚠️  LinkedIn credentials not set!")
        print("  Add to your .env file:")
        print("    LINKEDIN_EMAIL=your-linkedin-email")
        print("    LINKEDIN_PASSWORD=your-linkedin-password")
        print()
        logger.error("LinkedIn credentials missing (LINKEDIN_EMAIL / LINKEDIN_PASSWORD)")
        return []

    async with async_playwright() as p:
        # Launch browser with anti-detection settings
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ],
        )
        context = await browser.new_context(
            viewport={'width': 1366, 'height': 768},
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            ),
            locale='en-US',
        )
        page = await context.new_page()

        # ── Remove webdriver flag ──
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        try:
            # ── Step 1: Login / Restore session ──
            print("  🔐 Connecting to LinkedIn...")
            session_loaded = await load_session(context)

            if session_loaded:
                # Verify session is still valid
                await page.goto('https://www.linkedin.com/feed/',
                                wait_until='domcontentloaded', timeout=30000)
                await human_delay(2, 4)

                if await is_logged_in(page):
                    print("  ✅ Session restored — logged in")
                else:
                    print("  ⚠️  Session expired, logging in fresh...")
                    success = await login(page, li_email, li_password)
                    if not success:
                        print("  ❌ LinkedIn login failed!")
                        return []
                    await save_session(context)
            else:
                print("  📝 No saved session — logging in...")
                success = await login(page, li_email, li_password)
                if not success:
                    print("  ❌ LinkedIn login failed!")
                    return []
                await save_session(context)

            # ── Step 2: Search companies by keyword ──
            all_companies = []
            seen_company_slugs = set()

            for keyword in keywords:
                print(f"  🔍 Searching companies: '{keyword}'...")
                companies = await search_companies(
                    page, keyword, max_pages=max_company_pages
                )
                for company in companies:
                    if company['slug'] not in seen_company_slugs:
                        seen_company_slugs.add(company['slug'])
                        all_companies.append(company)

                await human_delay(3, 6)

            stats['companies_found'] = len(all_companies)
            print(f"  📋 Found {len(all_companies)} unique companies")

            if not all_companies:
                print("  ⚠️  No companies found. Check your keywords or login status.")
                return []

            # ── Step 3 & 4: Scrape company details + jobs ──
            companies_with_data = []

            for i, company in enumerate(all_companies, 1):
                print(
                    f"  🏢 [{i}/{len(all_companies)}] "
                    f"{company['name']}..."
                )

                # Scrape /about/ page for website
                enriched = await scrape_company_about(page, company)
                if not enriched:
                    continue

                await human_delay(2, 4)

                # Scrape job listings
                jobs = await scrape_company_jobs(page, enriched,
                                                 max_pages=max_job_pages)
                stats['jobs_found'] += len(jobs)

                # Optionally get job details for top N jobs
                detailed_jobs = []
                for j, job in enumerate(jobs[:max_job_details]):
                    detail = await scrape_job_details(page, job)
                    detailed_jobs.append(detail)
                    await human_delay(1.5, 3)

                # Use detailed jobs if available, else basic list
                final_jobs = detailed_jobs if detailed_jobs else jobs

                if enriched.get('website'):
                    stats['companies_with_website'] += 1
                    companies_with_data.append({
                        'company': enriched,
                        'jobs': final_jobs,
                    })
                    logger.info(
                        f"  ✓ {enriched['name']}: "
                        f"website={enriched['website']}, "
                        f"{len(final_jobs)} jobs"
                    )
                else:
                    logger.info(
                        f"  ✗ {enriched['name']}: no website found, "
                        f"{len(final_jobs)} jobs"
                    )

                # Rate limiting between companies
                await human_delay(3, 7)

            # Save session after scraping
            await save_session(context)

            print(
                f"\n  📊 Companies with website: "
                f"{stats['companies_with_website']}/{stats['companies_found']}"
            )
            print(f"  📊 Total jobs found: {stats['jobs_found']}")

        finally:
            await browser.close()

    # ── Step 5: Extract emails from company websites ──
    if companies_with_data:
        print(f"\n  🌐 Extracting emails from {len(companies_with_data)} company websites...")

        for i, entry in enumerate(companies_with_data, 1):
            company = entry['company']
            jobs = entry['jobs']
            website = company['website']

            print(
                f"  📧 [{i}/{len(companies_with_data)}] "
                f"{company['name']} → {website}"
            )

            try:
                contacts = await extract_emails_from_website(
                    website, company, jobs
                )
                if contacts:
                    all_contacts.extend(contacts)
                    stats['emails_found'] += len(contacts)
                    print(f"     ✅ Found {len(contacts)} email(s)")
                else:
                    print(f"     ⚠️  No emails found")
            except Exception as e:
                logger.warning(
                    f"Failed to extract emails from {website}: {e}"
                )
                print(f"     ❌ Error: {e}")

    print(f"\n  {'='*50}")
    print(f"  📊 LINKEDIN SCRAPER RESULTS")
    print(f"  {'='*50}")
    print(f"  Companies found:        {stats['companies_found']}")
    print(f"  Companies with website: {stats['companies_with_website']}")
    print(f"  Jobs found:             {stats['jobs_found']}")
    print(f"  Emails extracted:       {stats['emails_found']}")
    print(f"  {'='*50}")

    return all_contacts


# ═══════════════════════════════════════════════════════════
#  Test / Demo Mode — No LinkedIn Login Required
# ═══════════════════════════════════════════════════════════

# Real Moroccan tech companies with websites (for testing the
# website → email extraction pipeline without LinkedIn access)
TEST_COMPANIES = [
    {
        'name': 'Digitancy',
        'url': 'https://www.linkedin.com/company/digitancy/',
        'slug': 'digitancy',
        'industry': 'Digital Marketing',
        'website': 'https://www.digitancy.com',
        'location': 'Rabat, Morocco',
    },
    {
        'name': 'Disway',
        'url': 'https://www.linkedin.com/company/disway/',
        'slug': 'disway',
        'industry': 'IT Distribution',
        'website': 'https://www.disway.com',
        'location': 'Casablanca, Morocco',
    },
    {
        'name': 'Abshore',
        'url': 'https://www.linkedin.com/company/abshore/',
        'slug': 'abshore',
        'industry': 'IT Consulting',
        'website': 'https://www.abshore.com',
        'location': 'Casablanca, Morocco',
    },
    {
        'name': 'Naolink',
        'url': 'https://www.linkedin.com/company/naolink/',
        'slug': 'naolink',
        'industry': 'Web Development',
        'website': 'https://www.naolink.com',
        'location': 'Casablanca, Morocco',
    },
    {
        'name': 'Involys',
        'url': 'https://www.linkedin.com/company/involys/',
        'slug': 'involys',
        'industry': 'Software Development',
        'website': 'http://www.involys.com',
        'location': 'Casablanca, Morocco',
    },
    {
        'name': 'Adria Business & Technology',
        'url': 'https://www.linkedin.com/company/adria-bt/',
        'slug': 'adria-bt',
        'industry': 'IT Services',
        'website': 'https://www.adria-bt.com',
        'location': 'Casablanca, Morocco',
    },
]

# Fake jobs to pair with test companies
TEST_JOBS = [
    {'url': '', 'title': 'Développeur Full Stack', 'location': 'Casablanca', 'description': 'Développement web full stack React/Node.js'},
    {'url': '', 'title': 'Développeur Java/Spring Boot', 'location': 'Rabat', 'description': 'Développement backend Java Spring Boot microservices'},
    {'url': '', 'title': 'DevOps Engineer', 'location': 'Casablanca', 'description': 'CI/CD, Docker, Kubernetes, cloud infrastructure'},
]


async def run_linkedin_test():
    """
    Test the LinkedIn pipeline WITHOUT LinkedIn login.
    Uses mock company data with real websites to test:
      - FetcherSession HTTP requests to company websites
      - Email extraction from homepage + /contact pages
      - make_contact_dict output format
      - Full post-processing pipeline

    Returns list of contact dicts (same format as real run).
    """
    print(f"\n  {'='*55}")
    print(f"  🧪 LINKEDIN TEST MODE — No Login Required")
    print(f"  {'='*55}")
    print(f"  Testing email extraction from {len(TEST_COMPANIES)} company websites")
    print(f"  (Skipping LinkedIn login, using mock company data)\n")

    all_contacts = []
    stats = {
        'companies_tested': len(TEST_COMPANIES),
        'emails_found': 0,
        'websites_with_email': 0,
        'websites_failed': 0,
    }

    for i, company in enumerate(TEST_COMPANIES, 1):
        website = company['website']
        print(f"  📧 [{i}/{len(TEST_COMPANIES)}] {company['name']} → {website}")

        try:
            contacts = await extract_emails_from_website(
                website, company, TEST_JOBS
            )
            if contacts:
                all_contacts.extend(contacts)
                stats['emails_found'] += len(contacts)
                stats['websites_with_email'] += 1
                # Show found emails
                unique_emails = set(c['email'] for c in contacts)
                for email in unique_emails:
                    print(f"     ✅ {email}")
            else:
                print(f"     ⚠️  No emails found")
        except Exception as e:
            stats['websites_failed'] += 1
            print(f"     ❌ Error: {e}")

    print(f"\n  {'='*55}")
    print(f"  📊 LINKEDIN TEST RESULTS")
    print(f"  {'='*55}")
    print(f"  Companies tested:       {stats['companies_tested']}")
    print(f"  Websites with email:    {stats['websites_with_email']}")
    print(f"  Websites failed:        {stats['websites_failed']}")
    print(f"  Total emails extracted:  {stats['emails_found']}")
    print(f"  Total contacts:          {len(all_contacts)}")
    print(f"  {'='*55}")

    return all_contacts
