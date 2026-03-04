"""
══════════════════════════════════════════════════════════════
  LinkedIn Spider — Feed-Scrolling "Hiring" Post Scraper
══════════════════════════════════════════════════════════════

  Strategy (anti-detection focused):
    1. Login with saved session (cookies + localStorage)
    2. Search LinkedIn with profile-related keywords
    3. Scroll through results / feed looking for "hiring" posts
    4. Click "…see more" to expand full post content
    5. Extract company name, job info, emails from post
    6. Visit company website → extract emails from /contact pages
    7. Keep scrolling with human-like delays & random pauses

  Anti-Bot Measures:
    • Random delays between every action (1-6s)
    • Human-like scrolling (variable speed, occasional pauses)
    • Random mouse movements before clicks
    • Viewport jitter (small scroll-backs)
    • Session persistence (avoids repeated logins)
    • navigator.webdriver removed
    • Realistic user-agent + viewport

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
import warnings
from pathlib import Path
from urllib.parse import quote_plus

# Suppress noisy SSL warnings from requests (we use verify=False)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

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

MOROCCO_GEO_ID = "102787409"

LINKEDIN_SKIP_DOMAINS = SOCIAL_DOMAINS | {
    'linkedin.com', 'licdn.com',
}

# ── Keywords derived from sender's profile ──
# Grouped by strategy:
#   1. Profile skills + "Maroc/Morocco" → local companies hiring your stack
#   2. Generic tech roles → catches multinationals posting in English
#   3. French job titles → Moroccan & francophone companies
#   4. Internship/stage → entry-level opportunities
PROFILE_KEYWORDS = [
    # ── Stack-specific (Morocco-targeted) ──
    "développeur full stack Maroc",
    "développeur react Maroc",
    "développeur node.js Maroc",
    "développeur laravel Maroc",
    "développeur vue.js Maroc",
    "développeur javascript Maroc",
    "développeur php Maroc",
    "développeur NestJS",
    "développeur typescript",
    # ── English roles (multinationals in Morocco) ──
    "full stack developer Morocco",
    "react developer Morocco",
    "node.js developer Morocco",
    "frontend developer Morocco",
    "backend developer Morocco",
    "javascript developer Morocco hiring",
    "MERN stack developer hiring",
    # ── Generic French titles ──
    "recrutement développeur web Maroc",
    "recrutement développeur Casablanca",
    "recrutement développeur Rabat",
    "offre développeur full stack",
    # ── Internship / Stage ──
    "stage développement web Maroc",
    "stage pfe informatique Maroc",
    "stage développeur full stack",
    # ── Broader (multinationals, remote, nearshore) ──
    "hiring developer Morocco",
    "remote developer Morocco",
    "nearshore developer Morocco",
    "IT company Morocco hiring",
    "devops Morocco",
    "docker developer Morocco",
]

# ── Hiring indicators (FR + EN) ──
HIRING_KEYWORDS_FR = [
    "on recrute", "nous recrutons", "recrutement", "on embauche",
    "nous embauchons", "rejoignez-nous", "rejoignez notre équipe",
    "offre d'emploi", "offre de stage", "cherche un", "cherchons un",
    "recherche un", "recherchons un", "poste à pourvoir",
    "opportunité", "stagiaire", "stage disponible",
    "nous cherchons", "cherche développeur", "recrute un",
    "candidature", "postulez", "postuler",
]

HIRING_KEYWORDS_EN = [
    "we're hiring", "we are hiring", "hiring", "join our team",
    "join us", "job opening", "open position", "looking for",
    "we need", "applying", "apply now", "opportunity",
    "vacant position", "internship", "we're looking for",
    "come work with us", "career opportunity", "hiring alert",
    "job alert", "#hiring", "#wearehiring", "#openposition",
    "#jobalert", "#recrutement",
]

ALL_HIRING_PATTERNS = HIRING_KEYWORDS_FR + HIRING_KEYWORDS_EN

HIRING_REGEX = re.compile(
    '|'.join(re.escape(k) for k in ALL_HIRING_PATTERNS),
    re.IGNORECASE
)

# JavaScript function that extracts text with proper spacing
# (textContent concatenates without spaces, causing email parsing issues)
CLEAN_TEXT_JS = """
(el) => {
    const blocks = new Set(['DIV','P','BR','LI','UL','OL','H1','H2','H3','H4','H5','H6',
                            'SECTION','ARTICLE','HEADER','FOOTER','TD','TR','BLOCKQUOTE',
                            'PRE','NAV','SPAN','A']);
    let result = '';
    function walk(node) {
        if (node.nodeType === 3) {
            result += node.textContent;
        } else if (node.nodeType === 1) {
            if (blocks.has(node.tagName)) result += ' ';
            for (const child of node.childNodes) walk(child);
            if (blocks.has(node.tagName)) result += ' ';
        }
    }
    walk(el);
    return result.replace(/\\s+/g, ' ').trim();
}
"""

# Tech keywords to detect relevance in posts
TECH_KEYWORDS = [
    'react', 'node.js', 'nodejs', 'javascript', 'typescript',
    'laravel', 'php', 'vue.js', 'vuejs', 'next.js', 'nextjs',
    'nestjs', 'express', 'full stack', 'fullstack', 'full-stack',
    'frontend', 'front-end', 'backend', 'back-end',
    'développeur', 'developer', 'devops', 'docker',
    'mongodb', 'postgresql', 'mysql', 'rest api', 'graphql',
    'html', 'css', 'tailwind', 'git', 'ci/cd',
    'spring boot', 'java', 'python', 'angular', 'flutter',
    'react native', 'mobile',
]


# ═══════════════════════════════════════════════════════════
#  Session Management
# ═══════════════════════════════════════════════════════════

async def save_session(context):
    """Save browser session (cookies + localStorage) to file."""
    try:
        cookies = await context.cookies()
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
    """Load saved session into browser context."""
    if not SESSION_FILE.exists():
        return False

    try:
        data = json.loads(SESSION_FILE.read_text(encoding='utf-8'))
        cookies = data.get('cookies', [])
        local_storage = data.get('localStorage', {})

        if cookies:
            await context.add_cookies(cookies)
            logger.info(f"Loaded {len(cookies)} cookies from session")

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
        # Logged-in pages include feed, search, messaging, company pages, etc.
        logged_in_paths = [
            '/feed', '/mynetwork', '/messaging', '/search/',
            '/notifications', '/jobs', '/in/', '/company/',
        ]
        if any(p in url for p in logged_in_paths):
            return True

        # Check for global nav (only present when logged in)
        global_nav = await page.query_selector(
            '#global-nav, .global-nav, nav.global-nav__content'
        )
        if global_nav:
            return True

        # Check for feed link in nav
        feed_link = await page.query_selector('a[href*="/feed"]')
        if feed_link:
            return True

        # If login form is visible, definitely not logged in
        login_form = await page.query_selector('#session_key, #username')
        if login_form:
            return False

        # Check for profile icon (logged-in indicator)
        profile_pic = await page.query_selector(
            'img.global-nav__me-photo, .feed-identity-module'
        )
        if profile_pic:
            return True

        return False
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════
#  Human-Like Behaviour (Anti-Detection)
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


async def random_mouse_move(page):
    """Move mouse to a random position on screen."""
    try:
        x = random.randint(100, 1200)
        y = random.randint(100, 600)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.1, 0.3))
    except Exception:
        pass


async def human_scroll(page, direction='down', amount=None):
    """
    Scroll with human-like behaviour:
    - Variable speed
    - Occasional small scroll-backs (jitter)
    - Random pauses
    """
    if amount is None:
        amount = random.randint(300, 700)

    if direction == 'down':
        await page.evaluate(f'window.scrollBy(0, {amount})')
    else:
        await page.evaluate(f'window.scrollBy(0, -{amount})')

    await asyncio.sleep(random.uniform(0.3, 0.8))

    # 20% chance of a small scroll-back (jitter)
    if random.random() < 0.20:
        jitter = random.randint(30, 80)
        await page.evaluate(f'window.scrollBy(0, -{jitter})')
        await asyncio.sleep(random.uniform(0.2, 0.5))


async def slow_scroll_feed(page, scrolls=5):
    """Scroll through feed slowly, like a human browsing."""
    for i in range(scrolls):
        await human_scroll(page, 'down')
        await asyncio.sleep(random.uniform(1.0, 2.5))

        if i % 3 == 0:
            await random_mouse_move(page)

        if i % 5 == 0 and i > 0:
            await asyncio.sleep(random.uniform(2.0, 4.0))


# ═══════════════════════════════════════════════════════════
#  Login Flow
# ═══════════════════════════════════════════════════════════

async def login(page, email, password):
    """
    Login to LinkedIn with credentials.
    Handles the verification PIN step if triggered.
    """
    logger.info("Attempting LinkedIn login...")
    try:
        await page.goto('https://www.linkedin.com/login', wait_until='domcontentloaded',
                        timeout=30000)
    except Exception as e:
        logger.warning(f"Failed to load login page: {e}")
        # Retry once
        try:
            await asyncio.sleep(3)
            await page.goto('https://www.linkedin.com/login', wait_until='load',
                            timeout=30000)
        except Exception:
            logger.error("Cannot reach LinkedIn login page")
            return False
    await human_delay(2, 4)

    # Try multiple selectors for the email field
    email_selectors = ['#username', '#session_key', 'input[name="session_key"]',
                        'input[autocomplete="username"]']
    email_el = None
    for sel in email_selectors:
        try:
            email_el = await page.wait_for_selector(sel, timeout=5000)
            if email_el:
                break
        except Exception:
            continue

    if not email_el:
        logger.error("Could not find email input on login page")
        # Save screenshot for debugging
        try:
            ss_path = Path(__file__).resolve().parent.parent / "logs" / "linkedin_login_debug.png"
            ss_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(ss_path))
            print(f"  📸 Debug screenshot: {ss_path}")
        except Exception:
            pass
        return False

    # Type email
    await email_el.click()
    await asyncio.sleep(0.3)
    for char in email:
        await email_el.type(char, delay=random.randint(50, 150))
    await human_delay(0.5, 1.0)

    # Type password
    pw_selectors = ['#password', 'input[name="session_password"]',
                     'input[type="password"]']
    pw_el = None
    for sel in pw_selectors:
        try:
            pw_el = await page.wait_for_selector(sel, timeout=5000)
            if pw_el:
                break
        except Exception:
            continue

    if not pw_el:
        logger.error("Could not find password input")
        return False

    await pw_el.click()
    await asyncio.sleep(0.3)
    for char in password:
        await pw_el.type(char, delay=random.randint(50, 150))
    await human_delay(0.5, 1.5)

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

    logged_in = await is_logged_in(page)
    if logged_in:
        logger.info("LinkedIn login successful")
    else:
        logger.error("LinkedIn login failed")
    return logged_in


# ═══════════════════════════════════════════════════════════
#  Post Detection & Extraction
# ═══════════════════════════════════════════════════════════

def is_hiring_post(text):
    """Check if post text contains hiring indicators."""
    return bool(HIRING_REGEX.search(text))


def extract_tech_from_text(text):
    """Extract tech keywords mentioned in a post."""
    text_lower = text.lower()
    return [t for t in TECH_KEYWORDS if t.lower() in text_lower]


def extract_contact_info_from_post(text):
    """Extract emails from post text (people sometimes paste emails)."""
    return extract_emails_from_text(text)


def _clean_author_name(name):
    """
    Clean up author name extracted from LinkedIn post header.
    Removes follower counts, timestamps, and connection degrees
    that get concatenated from the DOM.
    """
    if not name:
        return name
    # Remove "• Xe et +..." (personal profile degree + headline)
    name = re.split(r'\s*•\s*\d+e\s', name)[0]
    # Remove follower count: "Name690 abonnés..." or "Name7 656 abonnés..."
    name = re.sub(r'\d[\d\s,.]*(?:abonnés?|followers?|abonné).*$', '', name, flags=re.IGNORECASE)
    # Remove trailing timestamp: "41 min •" or "1 h •"
    name = re.sub(r'\d+\s*(?:min|h|j|d|sem|mo)\s*•?.*$', '', name)
    # Remove trailing bullets, dots, whitespace
    name = name.rstrip('•. \t\n')
    return name.strip()


async def expand_post(page, post_element):
    """
    Click "…see more" / "…plus" on a post to expand full content.
    Uses text-based matching since LinkedIn obfuscates class names.
    """
    try:
        # Find any clickable element containing "see more" / "voir plus" text
        see_more_btn = await post_element.evaluate_handle("""
            el => {
                const buttons = el.querySelectorAll('button, span, a');
                for (const btn of buttons) {
                    const text = (btn.textContent || '').trim().toLowerCase();
                    if (text.includes('see more') || text.includes('voir plus')
                        || text.includes('…plus') || text.includes('...more')
                        || text === 'plus' || text === 'more') {
                        return btn;
                    }
                }
                return null;
            }
        """)

        if see_more_btn:
            try:
                box = await see_more_btn.as_element().bounding_box()
                if box:
                    await page.mouse.move(
                        box['x'] + random.randint(2, 10),
                        box['y'] + random.randint(2, 5)
                    )
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                await see_more_btn.as_element().click()
                await asyncio.sleep(random.uniform(0.5, 1.5))
            except Exception:
                pass

        # Get full text content with proper spacing between elements
        try:
            full_text = await post_element.evaluate(CLEAN_TEXT_JS)
            return full_text
        except Exception:
            return ''

    except (Exception, asyncio.CancelledError) as e:
        logger.debug(f"Error expanding post: {e}")
        return ''


async def extract_post_data(page, post_element):
    """
    Extract all data from a LinkedIn post element.
    Uses content-based extraction since class names are obfuscated.
    """
    data = {
        'author_name': '',
        'author_url': '',
        'author_headline': '',
        'post_text': '',
        'is_hiring': False,
        'emails_in_post': [],
        'tech_mentioned': [],
    }

    try:
        # ── Extract all info via JavaScript (one evaluate call) ──
        info = await post_element.evaluate("""
            el => {
                const result = {
                    authorName: '',
                    authorUrl: '',
                    authorHeadline: '',
                    fullText: '',
                    links: [],
                };

                // Author: first <a> with /in/ or /company/ in href
                const allLinks = el.querySelectorAll('a[href*="/in/"], a[href*="/company/"]');
                for (const link of allLinks) {
                    const text = (link.textContent || '').trim();
                    if (text && text.length > 2 && text.length < 100) {
                        result.authorName = text.split('\\n')[0].trim();
                        result.authorUrl = link.href.split('?')[0];
                        break;
                    }
                }

                // Headline: text right after the author name
                // LinkedIn puts it in a sibling or parent span
                if (result.authorName) {
                    const fullText = el.textContent || '';
                    const nameIdx = fullText.indexOf(result.authorName);
                    if (nameIdx >= 0) {
                        const afterName = fullText.substring(nameIdx + result.authorName.length, nameIdx + result.authorName.length + 200);
                        // First meaningful line after the name
                        const lines = afterName.split('\\n').map(l => l.trim()).filter(l => l.length > 5);
                        if (lines.length > 0) {
                            result.authorHeadline = lines[0].substring(0, 100);
                        }
                    }
                }

                // Full text content with spacing between elements
                const blocks = new Set(['DIV','P','BR','LI','SPAN','A','H1','H2','H3','H4','H5','H6','SECTION','ARTICLE']);
                let fullText = '';
                function walkText(node) {
                    if (node.nodeType === 3) { fullText += node.textContent; }
                    else if (node.nodeType === 1) {
                        if (blocks.has(node.tagName)) fullText += ' ';
                        for (const child of node.childNodes) walkText(child);
                        if (blocks.has(node.tagName)) fullText += ' ';
                    }
                }
                walkText(el);
                result.fullText = fullText.replace(/\\s+/g, ' ').trim();

                // All external links
                el.querySelectorAll('a[href]').forEach(a => {
                    const href = a.href;
                    if (href && !href.includes('linkedin.com')) {
                        result.links.push(href);
                    }
                });

                return result;
            }
        """)

        data['author_name'] = _clean_author_name(info.get('authorName', ''))
        data['author_url'] = info.get('authorUrl', '')
        data['author_headline'] = info.get('authorHeadline', '')
        data['post_text'] = ' '.join((info.get('fullText', '')).split())  # normalize ws

        # ── Expand post if possible ──
        expanded = await expand_post(page, post_element)
        if len(expanded) > len(data['post_text']):
            data['post_text'] = expanded

        # ── Detect hiring & extract info ──
        data['is_hiring'] = is_hiring_post(data['post_text'])

        if data['post_text']:
            data['emails_in_post'] = extract_contact_info_from_post(data['post_text'])
            data['tech_mentioned'] = extract_tech_from_text(data['post_text'])

    except (Exception, asyncio.CancelledError) as e:
        logger.debug(f"Error extracting post data: {e}")

    return data


# ═══════════════════════════════════════════════════════════
#  Company Website → Email Extraction
# ═══════════════════════════════════════════════════════════

async def extract_emails_from_website(website_url, company_info):
    """
    Visit a company's website to find email addresses.
    Checks homepage first, then /contact, /careers, etc.
    """
    import requests as _requests

    emails_found = set()
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        ),
    }

    domain = extract_domain(website_url)
    if not domain:
        return list(emails_found)

    # Homepage
    try:
        resp = _requests.get(website_url, headers=headers, timeout=10,
                             verify=False, allow_redirects=True)
        emails = find_relevant_emails(resp.text, domain)
        emails_found.update(emails)
    except Exception as e:
        logger.debug(f"Failed to fetch homepage {website_url}: {e}")

    # Contact pages if no emails on homepage
    if not emails_found:
        base_url = website_url.rstrip('/')
        for path in CONTACT_PATHS:
            try:
                resp = _requests.get(base_url + path, headers=headers,
                                     timeout=10, verify=False,
                                     allow_redirects=True)
                if resp.status_code >= 400:
                    continue
                emails = find_relevant_emails(resp.text, domain)
                emails_found.update(emails)
                if emails_found:
                    break
            except Exception:
                continue

    return list(emails_found)


async def get_company_website_from_linkedin(page, company_url):
    """
    Visit a company's LinkedIn /about/ page to find their website.
    Returns the website URL or None.
    """
    try:
        about_url = company_url.rstrip('/') + '/about/'
        await page.goto(about_url, wait_until='domcontentloaded', timeout=20000)
        await human_delay(2, 4)
        await slow_scroll_feed(page, scrolls=2)

        # Method 1: Website link in about section
        website_selectors = [
            '.link-without-visited-state[href]',
            'dd a[href]',
            'a[data-test-id="about-us__website"]',
        ]

        for sel in website_selectors:
            try:
                links = await page.query_selector_all(sel)
                for link_el in links:
                    href = await link_el.get_attribute('href')
                    if (href and href.startswith('http')
                            and 'linkedin.com' not in href
                            and not any(d in href.lower() for d in LINKEDIN_SKIP_DOMAINS)):
                        return href
            except Exception:
                continue

        # Method 2: Extract URLs from page text
        text = await page.inner_text('body')
        url_pattern = re.compile(
            r'https?://(?:www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?'
        )
        for match in url_pattern.finditer(text):
            url = match.group()
            if ('linkedin.com' not in url
                    and not any(d in url.lower() for d in LINKEDIN_SKIP_DOMAINS)):
                return url

    except Exception as e:
        logger.debug(f"Failed to get website from {company_url}: {e}")

    return None


# ═══════════════════════════════════════════════════════════
#  Feed / Search Scrolling Strategy
# ═══════════════════════════════════════════════════════════

async def search_and_scroll_posts(page, keyword, max_scrolls=15):
    """
    Search LinkedIn for a keyword, then scroll through results
    looking for hiring posts.

    Strategy:
      1. Search with keyword in "Posts" filter (sort by recent)
      2. Scroll down slowly (human-like)
      3. For each visible post → quick-check for hiring keywords
      4. If hiring → expand "see more", extract full data
      5. Keep scrolling until max_scrolls reached

    Returns list of dicts for posts that matched hiring criteria.
    """
    hiring_posts = []
    seen_posts = set()

    # LinkedIn content search sorted by recent
    # If keyword already contains a location (Maroc/Morocco/city), search globally
    # Otherwise, add Morocco geo-filter to focus on local + multinational companies
    has_location = any(loc in keyword.lower() for loc in [
        'maroc', 'morocco', 'casablanca', 'rabat', 'tanger', 'marrakech',
        'fes', 'agadir', 'oujda', 'kenitra', 'mohammedia',
    ])
    search_url = (
        f"https://www.linkedin.com/search/results/content/"
        f"?keywords={quote_plus(keyword)}"
        f"&origin=GLOBAL_SEARCH_HEADER"
        f"&sortBy=%22date_posted%22"
    )
    # Add Morocco geo-filter only when keyword has no location qualifier
    if not has_location:
        search_url += f"&geoUrn=%5B%22{MOROCCO_GEO_ID}%22%5D"

    logger.info(f"[LinkedIn] Searching posts: '{keyword}'")
    try:
        await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
    except Exception as e:
        logger.warning(f"Failed to load search page: {e}")
        return hiring_posts

    await human_delay(3, 5)

    # Check if we got redirected to login/authwall
    current_url = page.url
    if 'login' in current_url or 'authwall' in current_url or 'checkpoint' in current_url:
        logger.warning(f"Redirected to auth page: {current_url}")
        print(f"    ⚠️  LinkedIn redirected to login/auth wall")
        print(f"    URL: {current_url}")
        # Save screenshot for diagnostics
        try:
            ss_path = Path(__file__).resolve().parent.parent / "logs" / "linkedin_debug.png"
            ss_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(ss_path))
            print(f"    📸 Screenshot saved: {ss_path}")
        except Exception:
            pass
        return hiring_posts

    # Wait for search results to load
    await human_delay(2, 4)

    # Debug: log current URL and page title
    page_title = await page.title()
    logger.info(f"[LinkedIn] Page: {current_url[:80]} — '{page_title}'")
    print(f"    📄 Page loaded: {page_title[:60]}")

    # ── Main scroll loop ──
    no_new_posts_count = 0

    # Initial scroll to load content
    await slow_scroll_feed(page, scrolls=3)
    await human_delay(2, 3)

    for scroll_num in range(max_scrolls):
        # Locate post containers using stable semantic selectors
        # LinkedIn uses obfuscated class names, so we use data-* and role attributes
        post_selectors = [
            '[data-view-name="feed-full-update"]',   # Main post wrapper (2025+)
            '[role="listitem"]',                      # Semantic list items
            '.feed-shared-update-v2',                 # Legacy class
            'div[data-urn*="activity"]',
            'div[data-urn*="ugcPost"]',
        ]

        posts = []
        for sel in post_selectors:
            candidates = await page.query_selector_all(sel)
            # Filter: only keep elements that have substantial text content
            for c in candidates:
                try:
                    text_len = await c.evaluate('el => (el.textContent || "").trim().length')
                    if text_len > 50:
                        posts.append(c)
                except Exception:
                    continue
            if posts:
                logger.info(f"[LinkedIn] Found {len(posts)} posts with '{sel}'")
                break

        if not posts:
            # Only log debug on first scroll if no posts found at all
            if scroll_num == 0:
                logger.warning("[LinkedIn] No post elements found on page")
                try:
                    ss_path = Path(__file__).resolve().parent.parent / "logs" / "linkedin_search_debug.png"
                    ss_path.parent.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path=str(ss_path), full_page=True)
                    logger.info(f"Debug screenshot saved: {ss_path}")
                except Exception:
                    pass

            logger.info(f"[LinkedIn] No posts visible on scroll {scroll_num + 1}")
            await slow_scroll_feed(page, scrolls=2)
            await human_delay(2, 3)
            no_new_posts_count += 1
            if no_new_posts_count >= 3:
                logger.info(f"[LinkedIn] No new posts after 3 scrolls, moving on")
                break
            continue

        new_found = 0
        if scroll_num == 0:
            print(f"    📊 Found {len(posts)} post elements on page")

        for idx, post_el in enumerate(posts):
            try:
                preview = ''
                try:
                    # Use clean text extraction with proper spacing between elements
                    preview = await post_el.evaluate(CLEAN_TEXT_JS)
                    preview = preview[:500]  # limit length
                except Exception as ex:
                    logger.debug(f"Text extraction error: {ex}")
                    continue

                if not preview:
                    continue

                dedup_key = hash(preview[:200])
                if dedup_key in seen_posts:
                    continue
                seen_posts.add(dedup_key)

                if not is_hiring_post(preview):
                    continue

                # ─── Found hiring post → expand & extract ───
                logger.info(f"[LinkedIn] 🎯 Hiring post (scroll {scroll_num + 1})")

                await random_mouse_move(page)
                await human_delay(0.5, 1.5)

                post_data = await extract_post_data(page, post_el)

                if post_data['is_hiring'] and post_data['author_name']:
                    hiring_posts.append(post_data)
                    new_found += 1
                    tech_str = ', '.join(post_data['tech_mentioned'][:5]) or 'general'
                    print(
                        f"    🎯 [{len(hiring_posts)}] "
                        f"{post_data['author_name']} — {tech_str}"
                    )
                    if post_data['emails_in_post']:
                        print(f"       📧 Email in post: {', '.join(post_data['emails_in_post'])}")

            except (Exception, asyncio.CancelledError) as e:
                logger.debug(f"Error processing post: {e}")
                continue

        if new_found > 0:
            no_new_posts_count = 0
        else:
            no_new_posts_count += 1
            if no_new_posts_count >= 3:
                break

        # ── Scroll for more ──
        await slow_scroll_feed(page, scrolls=random.randint(2, 4))
        await human_delay(1.5, 3.5)

        # Every 5 scrolls, take a "reading break"
        if scroll_num > 0 and scroll_num % 5 == 0:
            pause = random.uniform(4, 8)
            logger.info(f"[LinkedIn] Reading break — {pause:.1f}s")
            await asyncio.sleep(pause)

        # Occasional small scroll-up (human jitter)
        if random.random() < 0.15:
            await human_scroll(page, 'up', amount=random.randint(50, 150))
            await asyncio.sleep(random.uniform(0.5, 1.0))

    return hiring_posts


# ═══════════════════════════════════════════════════════════
#  Main Orchestrator
# ═══════════════════════════════════════════════════════════

async def run_linkedin_spider(keywords=None, max_scrolls=15):
    """
    Run the LinkedIn feed-scrolling spider:
      1. Login / restore session
      2. For each keyword → search LinkedIn Posts, scroll & detect hiring posts
      3. For each hiring post → find company, get website
      4. Visit company websites → extract emails
      5. Return list of contact dicts

    Args:
        keywords:    Custom keywords list (None = profile-based defaults)
        max_scrolls: Max scroll iterations per keyword search

    Returns:
        List of contact dicts (same format as other spiders)
    """
    from playwright.async_api import async_playwright

    keywords = keywords or PROFILE_KEYWORDS
    all_contacts = []
    all_hiring_posts = []
    seen_company_keys = set()
    stats = {
        'keywords_searched': 0,
        'hiring_posts_found': 0,
        'companies_with_website': 0,
        'emails_found': 0,
    }

    # ── Partial save path (crash recovery) ──
    partial_dir = Path(__file__).resolve().parent.parent.parent / 'scraper_output'
    partial_dir.mkdir(parents=True, exist_ok=True)
    partial_json = partial_dir / 'linkedin_partial.json'
    partial_md = partial_dir / 'linkedin_partial.md'

    def _save_partial():
        """Save contacts collected so far (crash recovery)."""
        if not all_contacts:
            return
        try:
            partial_json.write_text(
                json.dumps(all_contacts, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            # Also save as markdown for quick review
            lines = [f"# LinkedIn Partial Results ({len(all_contacts)} contacts)\n"]
            lines.append(f"_Saved at {time.strftime('%Y-%m-%d %H:%M:%S')}_\n")
            for c in all_contacts:
                lines.append(f"- **{c.get('company', '?')}** — {c.get('email', '?')}")
                if c.get('position'):
                    lines[-1] += f" ({c['position']})"
            partial_md.write_text('\n'.join(lines), encoding='utf-8')
            logger.debug(f"Partial save: {len(all_contacts)} contacts → {partial_json.name}")
        except Exception as e:
            logger.warning(f"Failed to save partial results: {e}")

    # ── Credentials ──
    li_email = os.getenv('LINKEDIN_EMAIL', '')
    li_password = os.getenv('LINKEDIN_PASSWORD', '')

    if not li_email or not li_password:
        print("\n  ⚠️  LinkedIn credentials not set!")
        print("  Add to your .env file:")
        print("    LINKEDIN_EMAIL=your-linkedin-email")
        print("    LINKEDIN_PASSWORD=your-linkedin-password\n")
        logger.error("LinkedIn credentials missing")
        return []

    async with async_playwright() as p:
        # headless=False so you can see the browser & debug
        # Change to headless=True for production/CI
        headless = os.getenv('LINKEDIN_HEADLESS', 'false').lower() == 'true'
        browser = await p.chromium.launch(
            headless=headless,
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
            locale='fr-FR',
            ignore_https_errors=True,
        )
        page = await context.new_page()

        # Remove webdriver flag + fake plugins/languages
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['fr-FR', 'fr', 'en-US', 'en']
            });
        """)

        try:
            # ── Step 1: Login / Restore session ──
            print("  🔐 Connecting to LinkedIn...")
            session_loaded = await load_session(context)

            if session_loaded:
                await page.goto('https://www.linkedin.com/feed/',
                                wait_until='domcontentloaded', timeout=30000)
                await human_delay(2, 4)

                if await is_logged_in(page):
                    print("  ✅ Session restored")
                else:
                    print("  ⚠️  Session expired, logging in fresh...")
                    if not await login(page, li_email, li_password):
                        print("  ❌ LinkedIn login failed!")
                        return []
                    await save_session(context)
            else:
                print("  📝 No saved session — logging in...")
                if not await login(page, li_email, li_password):
                    print("  ❌ LinkedIn login failed!")
                    return []
                await save_session(context)

            # ── Step 2: Search & scroll for each keyword ──
            session_lost_count = 0
            net_error_count = 0

            for keyword in keywords:
                print(f"\n  🔍 Searching: '{keyword}'...")
                stats['keywords_searched'] += 1

                posts = await search_and_scroll_posts(
                    page, keyword, max_scrolls=max_scrolls
                )

                # If 0 posts and session might be lost, try re-login
                if not posts and session_lost_count < 2:
                    try:
                        # Check if we're still logged in
                        await page.goto('https://www.linkedin.com/feed/',
                                        wait_until='domcontentloaded', timeout=30000)
                        await human_delay(2, 3)
                    except (Exception, asyncio.CancelledError):
                        # Network error (DNS, timeout, etc.) — wait and retry
                        net_error_count += 1
                        if net_error_count >= 3:
                            print(f"  ❌ Network down ({net_error_count} failures) — stopping")
                            break
                        wait = 15 * net_error_count
                        print(f"  🌐 Network error — waiting {wait}s before retry...")
                        await asyncio.sleep(wait)
                        continue

                    if not await is_logged_in(page):
                        session_lost_count += 1
                        print(f"  🔄 Session lost — re-logging in (attempt {session_lost_count})...")
                        if await login(page, li_email, li_password):
                            await save_session(context)
                            print(f"  ✅ Re-logged in, retrying search...")
                            # Retry this keyword
                            posts = await search_and_scroll_posts(
                                page, keyword, max_scrolls=max_scrolls
                            )
                        else:
                            print(f"  ❌ Re-login failed")
                            break

                for post in posts:
                    key = post['author_name'].lower().strip()
                    if key in seen_company_keys:
                        continue
                    seen_company_keys.add(key)
                    all_hiring_posts.append(post)

                stats['hiring_posts_found'] = len(all_hiring_posts)
                print(f"  📋 Unique hiring posts so far: {len(all_hiring_posts)}")

                # Rest between keyword searches
                if keyword != keywords[-1]:
                    rest = random.uniform(5, 10)
                    print(f"  ⏸️  Resting {rest:.0f}s before next search...")
                    await asyncio.sleep(rest)

            await save_session(context)

            if not all_hiring_posts:
                print("\n  ⚠️  No hiring posts found. Try different keywords.")
                return []

            print(f"\n  {'─'*50}")
            print(f"  📊 Found {len(all_hiring_posts)} unique hiring posts")
            print(f"  {'─'*50}")

            # ── Step 3: Find company websites ──
            print(f"\n  🌐 Resolving company websites...")

            companies_to_scrape = []

            for i, post in enumerate(all_hiring_posts, 1):
                company_name = post['author_name']
                author_url = post['author_url']

                print(f"  🏢 [{i}/{len(all_hiring_posts)}] {company_name}...")

                # If post had emails directly → use them
                if post['emails_in_post']:
                    for email in post['emails_in_post']:
                        contact = make_contact_dict(
                            company=company_name,
                            email=email,
                            position=', '.join(post['tech_mentioned'][:3]) or 'Hiring Post',
                            city='',
                            source_url=author_url,
                            source_site='linkedin',
                            description=post['post_text'][:500],
                        )
                        all_contacts.append(contact)
                        stats['emails_found'] += 1
                        print(f"     ✅ Email from post: {email}")
                    _save_partial()
                    continue

                # Try LinkedIn /about/ page for company website
                website = None
                if '/company/' in author_url:
                    website = await get_company_website_from_linkedin(
                        page, author_url
                    )
                    await human_delay(2, 5)

                # Fallback: guess website from company name (only for company profiles)
                if not website and '/company/' in author_url:
                    website = guess_website(company_name)

                if website:
                    stats['companies_with_website'] += 1
                    companies_to_scrape.append({
                        'name': company_name,
                        'website': website,
                        'post': post,
                    })
                    logger.info(f"  ✓ {company_name}: {website}")
                else:
                    logger.info(f"  ✗ {company_name}: no website found")

                await human_delay(2, 5)

        finally:
            try:
                await browser.close()
            except Exception:
                pass  # Browser may already be closing

    # ── Step 4: Extract emails from company websites ──
    if companies_to_scrape:
        print(f"\n  📧 Extracting emails from {len(companies_to_scrape)} websites...")

        for i, entry in enumerate(companies_to_scrape, 1):
            name = entry['name']
            website = entry['website']
            post = entry['post']

            print(f"  📧 [{i}/{len(companies_to_scrape)}] {name} → {website}")

            try:
                emails = await extract_emails_from_website(website, entry)
                if emails:
                    for email in emails:
                        contact = make_contact_dict(
                            company=name,
                            email=email,
                            position=', '.join(post['tech_mentioned'][:3]) or 'Hiring Post',
                            city='',
                            source_url=post.get('author_url', ''),
                            source_site='linkedin',
                            description=post['post_text'][:500],
                        )
                        all_contacts.append(contact)
                        stats['emails_found'] += 1
                    print(f"     ✅ Found {len(emails)} email(s)")
                    _save_partial()
                else:
                    print(f"     ⚠️  No emails found")
            except Exception as e:
                logger.warning(f"Failed to extract emails from {website}: {e}")
                print(f"     ❌ Error: {e}")

    # ── Summary ──
    print(f"\n  {'='*50}")
    print(f"  📊 LINKEDIN FEED SCRAPER RESULTS")
    print(f"  {'='*50}")
    print(f"  Keywords searched:      {stats['keywords_searched']}")
    print(f"  Hiring posts found:     {stats['hiring_posts_found']}")
    print(f"  Companies with website: {stats['companies_with_website']}")
    print(f"  Emails extracted:       {stats['emails_found']}")
    print(f"  Total contacts:         {len(all_contacts)}")
    print(f"  {'='*50}")

    # Clean up partial files on successful completion
    for f in [partial_json, partial_md]:
        if f.exists():
            try:
                f.unlink()
            except Exception:
                pass

    return all_contacts


# ═══════════════════════════════════════════════════════════
#  Test / Demo Mode
# ═══════════════════════════════════════════════════════════

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

TEST_JOBS = [
    {'url': '', 'title': 'Développeur Full Stack',
     'location': 'Casablanca',
     'description': 'Développement web full stack React/Node.js'},
    {'url': '', 'title': 'Développeur Java/Spring Boot',
     'location': 'Rabat',
     'description': 'Développement backend Java Spring Boot microservices'},
    {'url': '', 'title': 'DevOps Engineer',
     'location': 'Casablanca',
     'description': 'CI/CD, Docker, Kubernetes, cloud infrastructure'},
]


async def run_linkedin_test():
    """
    Test mode — no LinkedIn login needed.
    Uses mock company data + real websites to test email extraction.
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
            emails = await extract_emails_from_website(website, company)
            if emails:
                for email in emails:
                    for job in TEST_JOBS:
                        all_contacts.append(make_contact_dict(
                            company=company['name'],
                            email=email,
                            position=job['title'],
                            city=job.get('location', company.get('location', '')),
                            source_url=company.get('url', ''),
                            source_site='linkedin',
                            description=job.get('description', ''),
                        ))
                stats['emails_found'] += len(emails)
                stats['websites_with_email'] += 1
                for email in emails:
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
