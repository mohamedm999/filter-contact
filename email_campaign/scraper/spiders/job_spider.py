"""
══════════════════════════════════════════════════════════════
  Job Board Spider — Scrapling Multi-Session Crawler
══════════════════════════════════════════════════════════════

  A unified Scrapling spider that crawls Moroccan (+ MENA)
  job boards using multi-session routing:

  Sessions:
    • "fast"    — HTTP requests via FetcherSession (ReKrute, MarocAnnonces, Bayt, company sites)
    • "stealth" — AsyncStealthySession with CF bypass (Emploi.ma)

  Pipeline:
    1. Search job board for keywords → get job listings
    2. Visit job detail page → extract company name
    3. Follow company profile → find company website
    4. Visit company website → extract emails from homepage + contact pages
    5. Yield contact dicts → post-processed by runner.py

  API notes (Scrapling v0.4.1):
    • Callbacks are async generators — use `yield` for items/requests
    • response.meta  — carries request.meta through
    • response.html_content — full HTML source (str)
    • response.css('sel::text').get() → str | None
    • response.css('sel::attr(href)').getall() → list[str]
"""

import re
import json
import logging
from urllib.parse import quote_plus

from scrapling.spiders import Spider, Request, Response
from scrapling.fetchers import FetcherSession, AsyncStealthySession

from ..helpers import (
    extract_emails_from_text, find_relevant_emails, extract_domain,
    guess_website, all_website_guesses, find_external_website,
    looks_like_company, make_contact_dict, normalize_city,
    SOCIAL_DOMAINS, CONTACT_PATHS, KNOWN_CITIES,
    SKIP_COMPANY_NAMES, COMMON_FIRST_NAMES, GENERIC_SKIP_DOMAINS,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  Search Keywords (defaults — overridden by settings)
# ═══════════════════════════════════════════════════════════

DEFAULT_KEYWORDS = [
    "développeur full stack",
    "développeur web",
    "développeur react",
    "développeur node.js",
    "développeur javascript",
    "développeur php",
    "développeur laravel",
    "développeur spring boot",
    "développeur java",
    "full stack developer",
    "frontend developer",
    "backend developer",
    "stage développement web",
    "stage informatique",
    "stage pfe",
    "flutter developer",
    "react native developer",
    "devops",
]


class JobBoardSpider(Spider):
    """
    Unified multi-session spider for all Moroccan job boards.
    Uses fast HTTP for ReKrute/MarocAnnonces and stealth browser for Emploi.ma.
    """
    name = "job_boards"
    start_urls = ["https://www.rekrute.com"]  # Placeholder; real URLs from start_requests
    concurrent_requests = 4
    concurrent_requests_per_domain = 1  # Throttle per domain to avoid 403s
    download_delay = 2

    def __init__(self, sites=None, keywords=None, **kwargs):
        self._target_sites = sites or ['rekrute', 'maroc_annonces', 'emploi_ma', 'bayt']
        if keywords:
            self._search_keywords = [k.strip() for k in keywords.split(',')]
        else:
            self._search_keywords = DEFAULT_KEYWORDS
        self._seen_companies = set()
        self._seen_emails = set()
        self._visited_domains = set()  # Avoid re-crawling same base domain
        super().__init__(**kwargs)

    def configure_sessions(self, manager):
        """Configure multi-session: fast HTTP + stealth browser."""
        manager.add(
            "fast",
            FetcherSession(
                impersonate='chrome',
                stealthy_headers=True,
                timeout=30,
            ),
        )
        if 'emploi_ma' in self._target_sites:
            manager.add(
                "stealth",
                AsyncStealthySession(
                    headless=True,
                ),
                lazy=True,
            )

    async def start_requests(self):
        """Generate initial search requests for each target site."""
        count = 0
        for site in self._target_sites:
            for keyword in self._search_keywords:
                if site == 'rekrute':
                    url = (
                        "https://www.rekrute.com/offres.html"
                        f"?s=2&p=1&o=1&keyword={quote_plus(keyword)}&c=&m="
                    )
                    yield Request(
                        url, callback=self.parse_rekrute_search,
                        sid="fast",
                        meta={'keyword': keyword, 'page': 1},
                    )
                    count += 1
                elif site == 'maroc_annonces':
                    url = (
                        "https://www.marocannonces.com/categorie/309/"
                        f"Offres-emploi/{quote_plus(keyword)}.html"
                    )
                    yield Request(
                        url, callback=self.parse_marocannonces_search,
                        sid="fast",
                        meta={'keyword': keyword, 'page': 1},
                    )
                    count += 1
                elif site == 'emploi_ma':
                    url = (
                        "https://www.emploi.ma/recherche-jobs-maroc"
                        f"?keywords={quote_plus(keyword)}&page=0"
                    )
                    yield Request(
                        url, callback=self.parse_emploi_search,
                        sid="stealth",
                        meta={'keyword': keyword, 'page': 0},
                    )
                    count += 1
                elif site == 'bayt':
                    url = (
                        "https://www.bayt.com/en/morocco/jobs/"
                        f"?q={quote_plus(keyword)}&page=1"
                    )
                    yield Request(
                        url, callback=self.parse_bayt_search,
                        sid="fast",
                        meta={'keyword': keyword, 'page': 1},
                    )
                    count += 1

        self.logger.info(
            f"Starting crawl: {len(self._target_sites)} sites, "
            f"{len(self._search_keywords)} keywords, "
            f"{count} initial requests"
        )

    async def parse(self, response):
        """Default callback (unused — start_requests routes to specific parsers)."""
        yield None

    # ═══════════════════════════════════════════════════════
    #  ReKrute.com
    # ═══════════════════════════════════════════════════════

    async def parse_rekrute_search(self, response):
        """Parse ReKrute search results page."""
        keyword = response.meta.get('keyword', '')
        page = response.meta.get('page', 1)
        html = str(response.html_content)

        job_cards = response.css('li.post-id')
        self.logger.info(
            f"[ReKrute] Found {len(job_cards)} jobs "
            f"for '{keyword}' (page {page})"
        )

        for card in job_cards:
            job_link = card.css('a.titreJob::attr(href)').get()
            job_title = card.css('a.titreJob::text').get()
            if job_title:
                job_title = str(job_title).strip()
            else:
                job_title = ''

            # Extract company name from logo alt
            raw_company = card.css('img.photo::attr(alt)').get()
            if not raw_company:
                raw_company = card.css('img::attr(alt)').get()
            raw_company = str(raw_company or '').strip()

            company = raw_company
            if ' - ' in company:
                company = company.split(' - ', 1)[-1].strip()
            # Remove duplicated first word
            words = company.split()
            if len(words) >= 2 and words[0].lower() == words[1].lower():
                company = ' '.join(words[1:])

            # Extract city from URL pattern
            city = ''
            company_slug = ''
            if job_link:
                job_link = str(job_link)
                recr_match = re.search(
                    r'recrutement-(.+?)-(\d+)\.html$', job_link
                )
                if recr_match:
                    slug_city_part = recr_match.group(1)
                    parts = slug_city_part.split('-')
                    city_parts = []
                    for i in range(len(parts) - 1, -1, -1):
                        candidate = '-'.join(parts[i:])
                        if candidate.lower() in KNOWN_CITIES:
                            city_parts = parts[i:]
                            break
                    if not city_parts and len(parts) >= 1:
                        city_parts = [parts[-1]]
                    city = ' '.join(city_parts).replace('-', ' ').title()
                    slug_end = len(parts) - len(city_parts)
                    company_slug = (
                        '-'.join(parts[:slug_end]) if slug_end > 0 else parts[0]
                    )
                    if not company:
                        company = company_slug.replace('-', ' ').title()

            if not job_title or not job_link:
                continue

            full_url = response.urljoin(str(job_link))
            yield Request(
                str(full_url), callback=self.parse_rekrute_detail,
                sid="fast",
                meta={
                    'company': company, 'company_slug': company_slug,
                    'position': job_title, 'city': city, 'keyword': keyword,
                },
            )

        # Pagination (max 3 pages)
        next_link = response.css('a.next::attr(href)').get()
        if not next_link:
            next_link = response.css('li.next a::attr(href)').get()
        if next_link and page < 3:
            yield Request(
                str(response.urljoin(str(next_link))),
                callback=self.parse_rekrute_search,
                sid="fast",
                meta={'keyword': keyword, 'page': page + 1},
            )

    async def parse_rekrute_detail(self, response):
        """Parse ReKrute job detail page."""
        meta = response.meta
        company = meta.get('company', '')
        company_slug = meta.get('company_slug', '')
        position = meta.get('position', '')
        city = meta.get('city', '')
        html = str(response.html_content)

        # Better title from detail page
        page_title = response.css('h1::text').get()
        if page_title and str(page_title).strip():
            position = str(page_title).strip()

        # Check for emails on page
        emails = extract_emails_from_text(html)
        emails = [e for e in emails if 'exemple' not in e and 'example' not in e]

        desc_parts = response.css('div.blc-body p::text').getall()
        if not desc_parts:
            desc_parts = response.css('div[class*="content"] p::text').getall()
        description = ' '.join(str(d) for d in desc_parts[:5]).strip()

        if emails:
            for email in emails:
                if email not in self._seen_emails:
                    self._seen_emails.add(email)
                    yield make_contact_dict(
                        company=company, email=email, position=position,
                        city=city, source_url=str(response.url),
                        source_site='rekrute', description=description,
                    )
            return

        # Find company profile link
        company_link = None
        for link in response.css('a::attr(href)').getall():
            link_str = str(link)
            if 'emploi-recrutement' in link_str and 'offre-emploi' not in link_str:
                company_link = link_str
                break

        if company_link:
            yield Request(
                str(response.urljoin(company_link)),
                callback=self.parse_rekrute_company,
                sid="fast",
                meta={
                    'company': company, 'company_slug': company_slug,
                    'position': position, 'city': city,
                    'description': description, 'job_url': str(response.url),
                },
            )
        elif company_slug and len(company_slug) > 2:
            slug_clean = company_slug.split('-')[0]
            for tld in ['.ma', '.com']:
                domain = f'{slug_clean}{tld}'
                if domain in GENERIC_SKIP_DOMAINS:
                    continue
                yield Request(
                    f'https://www.{domain}',
                    callback=self.parse_company_website,
                    sid="fast",
                    meta={
                        'company': company, 'position': position,
                        'city': city, 'description': description,
                        'job_url': str(response.url), 'source_site': 'rekrute',
                        'company_domain': domain,
                    },
                )

    async def parse_rekrute_company(self, response):
        """Parse ReKrute company profile → find website."""
        meta = response.meta
        company = meta.get('company', '')
        html = str(response.html_content)

        # Check for emails on profile page
        emails = extract_emails_from_text(html)
        emails = [e for e in emails if 'exemple' not in e and 'example' not in e]
        if emails:
            for email in emails:
                if email not in self._seen_emails:
                    self._seen_emails.add(email)
                    yield make_contact_dict(
                        company=company, email=email,
                        position=meta.get('position', ''),
                        city=meta.get('city', ''),
                        source_url=meta.get('job_url', ''),
                        source_site='rekrute',
                        description=meta.get('description', ''),
                    )
            return

        # Find company website
        all_links = [str(l) for l in response.css('a::attr(href)').getall()]
        website_url = find_external_website(all_links)

        if website_url:
            self.logger.info(f"[{company}] Found website: {website_url}")
            yield Request(
                website_url, callback=self.parse_company_website,
                sid="fast",
                meta={
                    **meta, 'source_site': 'rekrute',
                    'company_domain': extract_domain(website_url),
                },
            )
        elif meta.get('company_slug'):
            slug_clean = meta['company_slug'].split('-')[0]
            for tld in ['.ma', '.com']:
                domain = f'{slug_clean}{tld}'
                if domain in GENERIC_SKIP_DOMAINS:
                    continue
                yield Request(
                    f'https://www.{domain}',
                    callback=self.parse_company_website,
                    sid="fast",
                    meta={
                        **meta, 'source_site': 'rekrute',
                        'company_domain': domain,
                    },
                )

    # ═══════════════════════════════════════════════════════
    #  MarocAnnonces.com
    # ═══════════════════════════════════════════════════════

    async def parse_marocannonces_search(self, response):
        """Parse MarocAnnonces search results."""
        keyword = response.meta.get('keyword', '')
        page = response.meta.get('page', 1)

        listings = response.css('ul.cars-list li')
        if not listings:
            listings = response.css('div.listing li')

        self.logger.info(
            f"[MarocAnnonces] Found {len(listings)} listings "
            f"for '{keyword}' (page {page})"
        )

        for item in listings:
            link = item.css('a::attr(href)').get()
            title = item.css('a::text').get()
            if not title:
                title = item.css('a::attr(title)').get()
            title = str(title or '').strip()
            if link:
                link_str = str(link)
                # Fix relative links: ensure root-relative
                if link_str and not link_str.startswith(('http', '/')):
                    link_str = '/' + link_str
                yield Request(
                    str(response.urljoin(link_str)),
                    callback=self.parse_marocannonces_detail,
                    sid="fast",
                    meta={'keyword': keyword, 'fallback_title': title},
                )

        # Pagination (max 3 pages)
        next_link = (
            response.css('a[rel="next"]::attr(href)').get()
            or response.css('li.next a::attr(href)').get()
            or response.css('a.next-page::attr(href)').get()
        )
        if next_link and page < 3:
            yield Request(
                str(response.urljoin(str(next_link))),
                callback=self.parse_marocannonces_search,
                sid="fast",
                meta={'keyword': keyword, 'page': page + 1},
            )

    async def parse_marocannonces_detail(self, response):
        """Parse MarocAnnonces job detail page."""
        fallback_title = response.meta.get('fallback_title', '')
        html = str(response.html_content)

        position = (
            response.css('h1::text').get()
            or response.css('h2.title::text').get()
            or fallback_title
        )
        position = str(position or '').strip()

        # ── JSON-LD parsing (most reliable) ──
        json_ld_company = ''
        json_ld_city = ''
        json_ld_desc = ''
        for script in response.css(
            'script[type="application/ld+json"]::text'
        ).getall():
            try:
                clean_script = re.sub(r'[\x00-\x1f]', ' ', str(script))
                data = json.loads(clean_script)
                if not isinstance(data, dict):
                    continue
                org = data.get('hiringOrganization', {})
                if isinstance(org, dict):
                    json_ld_company = org.get('name', '').strip()
                loc = data.get('jobLocation', {})
                if isinstance(loc, dict):
                    addr = loc.get('address', {})
                    if isinstance(addr, dict):
                        json_ld_city = (
                            addr.get('addressLocality', '')
                            or addr.get('addressRegion', '')
                        ).strip()
                json_ld_desc = data.get('description', '').strip()
                if not position:
                    position = data.get('title', '').strip()
            except (json.JSONDecodeError, AttributeError):
                continue

        # ── Company from HTML ──
        company = ''
        annonceur_dd = response.css(
            'div.infoannonce dt:contains("Annonceur") + dd::text'
        ).get()
        if annonceur_dd:
            company = str(annonceur_dd).strip()

        if not company:
            info_block = response.css('div.infoannonce').get()
            info_html = str(info_block) if info_block else ''
            match = re.search(
                r'Annonceur\s*:?\s*</dt>\s*<dd>\s*(.*?)\s*</dd>',
                info_html, re.IGNORECASE,
            )
            if match:
                company = match.group(1).strip()
            if not company:
                match2 = re.search(
                    r'Annonceur\s*[:\-]\s*([^<\n]+)', info_html,
                )
                if match2:
                    company = match2.group(1).strip()

        # Prefer JSON-LD company if HTML is person name
        if json_ld_company:
            if not company or not looks_like_company(company):
                company = json_ld_company
            elif len(json_ld_company) > len(company):
                company = json_ld_company

        # City
        city = json_ld_city
        if not city:
            ville_dd = response.css(
                'div.infoannonce dt:contains("Ville") + dd::text'
            ).get()
            if ville_dd:
                city = str(ville_dd).strip()

        # Description
        description = ''
        if json_ld_desc:
            clean_desc = re.sub(r'<[^>]+>', ' ', json_ld_desc)
            clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
            description = clean_desc[:500]
        if not description:
            desc_parts = response.css('div.content-text ::text').getall()
            if not desc_parts:
                desc_parts = response.css(
                    'div[class*="description"] ::text'
                ).getall()
            description = ' '.join(
                str(d).strip() for d in desc_parts[:8] if str(d).strip()
            )

        # Check for emails on the page
        emails = extract_emails_from_text(html)
        emails = [
            e for e in emails
            if 'exemple' not in e and 'example' not in e
            and 'marocannonces' not in e
        ]

        if emails:
            for email in emails:
                if email not in self._seen_emails:
                    self._seen_emails.add(email)
                    yield make_contact_dict(
                        company=company, email=email, position=position,
                        city=city, source_url=str(response.url),
                        source_site='maroc_annonces', description=description,
                    )
            return

        # ── Company website discovery ──
        if not company:
            return
        if company.lower().strip() in SKIP_COMPANY_NAMES:
            return
        if not looks_like_company(company):
            return

        self.logger.info(f"[MarocAnnonces] Company: '{company}' — searching website")

        # External link on page
        all_links = [str(l) for l in response.css('a::attr(href)').getall()]
        website_url = find_external_website(all_links)

        # URL in description text
        if not website_url:
            url_match = re.search(
                r'https?://(?:www\.)?[a-zA-Z0-9.-]+\.[a-z]{2,}',
                description + ' ' + html[:5000],
            )
            if url_match:
                found = url_match.group(0)
                if not any(d in found.lower() for d in SOCIAL_DOMAINS):
                    website_url = found

        if not website_url:
            website_url = guess_website(company)

        if website_url:
            domain = extract_domain(website_url)
            yield Request(
                website_url, callback=self.parse_company_website,
                sid="fast",
                meta={
                    'company': company, 'position': position,
                    'city': city, 'description': description,
                    'job_url': str(response.url), 'source_site': 'maroc_annonces',
                    'company_domain': domain,
                    'tried_tlds': [website_url],
                },
            )

    # ═══════════════════════════════════════════════════════
    #  Emploi.ma (Cloudflare Turnstile — stealth session)
    # ═══════════════════════════════════════════════════════

    async def parse_emploi_search(self, response):
        """Parse Emploi.ma search results (behind Cloudflare)."""
        keyword = response.meta.get('keyword', '')
        page = response.meta.get('page', 0)
        html = str(response.html_content)

        # Check if we got blocked
        if response.status == 403 or 'Vérification' in html[:500]:
            self.logger.warning(
                f"[Emploi.ma] Cloudflare challenge detected for '{keyword}' "
                f"(page {page})"
            )
            return

        # Job cards: div.card.card-job with links in h3 > a
        job_cards = response.css('div.card-job')
        job_links = []
        for card in job_cards:
            link = card.css('h3 a::attr(href)').get()
            if link:
                link_str = str(link)
                if '/offre-emploi' in link_str:
                    # Extract company name from card directly (saves a stealth request)
                    card_company = str(
                        card.css('a.card-job-company::text').get()
                        or card.css('a.company-name::text').get()
                        or ''
                    ).strip()
                    card_title = str(card.css('h3 a::text').get() or '').strip()
                    # Company profile link
                    card_company_link = str(
                        card.css('a[href*="/recruteur/"]::attr(href)').get() or ''
                    )
                    job_links.append({
                        'url': link_str,
                        'company': card_company,
                        'title': card_title,
                        'company_link': card_company_link,
                    })

        # Fallback selectors
        if not job_links:
            for l in response.css('a[href*="/offre-emploi-maroc/"]::attr(href)').getall():
                job_links.append({'url': str(l), 'company': '', 'title': '', 'company_link': ''})

        self.logger.info(
            f"[Emploi.ma] Found {len(job_links)} jobs "
            f"for '{keyword}' (page {page})"
        )

        for job in job_links:
            yield Request(
                str(response.urljoin(job['url'])),
                callback=self.parse_emploi_detail,
                sid="stealth",
                meta={
                    'keyword': keyword,
                    'card_company': job['company'],
                    'card_title': job['title'],
                    'card_company_link': job['company_link'],
                },
            )

        # Pagination
        next_link = (
            response.css('li.pager-next a::attr(href)').get()
            or response.css('a[rel="next"]::attr(href)').get()
        )
        if next_link and page < 4:
            yield Request(
                str(response.urljoin(str(next_link))),
                callback=self.parse_emploi_search,
                sid="stealth",
                meta={'keyword': keyword, 'page': page + 1},
            )

    async def parse_emploi_detail(self, response):
        """Parse Emploi.ma job detail page."""
        html = str(response.html_content)

        # Skip blocked responses
        if response.status == 403 or 'Vérification' in html[:500]:
            self.logger.warning(f"[Emploi.ma] Blocked on detail page: {response.url}")
            return

        # Use card data from search results (pre-extracted to save requests)
        card_company = response.meta.get('card_company', '')
        card_title = response.meta.get('card_title', '')
        card_company_link = response.meta.get('card_company_link', '')

        # Try to extract from detail page
        company = str(
            response.css('a.card-job-company::text').get()
            or response.css('a.company-name::text').get()
            or response.css('a[href*="/recruteur/"] ::text').get()
            or ''
        ).strip() or card_company

        position = str(
            response.css('h1::text').get()
            or ''
        ).strip() or card_title

        # Location:  <li><strong>Ville</strong> : <span>Casablanca</span></li>
        city = ''
        # Try Ville first (more specific), then Région
        ville_match = re.search(
            r'<strong>Ville</strong>\s*:\s*<span>([^<]+)</span>',
            html, re.I,
        )
        if ville_match:
            city = ville_match.group(1).strip()
        else:
            region_match = re.search(
                r'<strong>R.gion</strong>\s*:\s*<span>([^<]+)</span>',
                html, re.I,
            )
            if region_match:
                city = region_match.group(1).strip()
        # Fallback: extract city from title after last dash
        if not city and ' - ' in position:
            city = position.rsplit(' - ', 1)[-1].strip()

        desc_parts = response.css('div.card-job-description p::text').getall()
        if not desc_parts:
            desc_parts = response.css('div.field-item p::text').getall()
        if not desc_parts:
            desc_parts = response.css('div[class*="description"] ::text').getall()
        description = ' '.join(str(d).strip() for d in desc_parts[:8] if str(d).strip())

        contact_name = str(
            response.css('div.recruiter-name ::text').get() or ''
        ).strip()

        # Check for emails
        emails = extract_emails_from_text(html)
        emails = [
            e for e in emails
            if 'emploi.ma' not in e and 'example' not in e
        ]

        if emails:
            for email in emails:
                if email not in self._seen_emails:
                    self._seen_emails.add(email)
                    yield make_contact_dict(
                        company=company, email=email, position=position,
                        city=city, source_url=str(response.url),
                        source_site='emploi_ma', description=description,
                        contact_name=contact_name,
                    )
            return

        # Shortcut: extract company website from "Site Internet" field
        site_match = re.search(
            r'<strong>Site Internet</strong>\s*:\s*<span>\s*<a\s+href="([^"]+)"',
            html, re.I,
        )
        if site_match:
            website_url = site_match.group(1).strip()
            if not any(d in website_url.lower() for d in SOCIAL_DOMAINS):
                domain = extract_domain(website_url)
                yield Request(
                    website_url, callback=self.parse_company_website,
                    sid="fast",
                    meta={
                        'company': company, 'position': position,
                        'city': city, 'description': description,
                        'contact_name': contact_name, 'job_url': str(response.url),
                        'source_site': 'emploi_ma',
                        'company_domain': domain,
                    },
                )
                return

        # Fallback: follow company profile (prefer card data, then page selectors)
        company_link = card_company_link or (
            response.css('a[href*="/recruteur/"]::attr(href)').get()
            or response.css('a.card-job-company::attr(href)').get()
            or response.css('a.company-name::attr(href)').get()
            or ''
        )

        if company_link:
            yield Request(
                str(response.urljoin(str(company_link))),
                callback=self.parse_emploi_company,
                sid="stealth",
                meta={
                    'company': company, 'position': position,
                    'city': city, 'description': description,
                    'contact_name': contact_name, 'job_url': str(response.url),
                },
            )
        elif company:
            website_url = guess_website(company)
            if website_url:
                domain = extract_domain(website_url)
                yield Request(
                    website_url, callback=self.parse_company_website,
                    sid="fast",  # Company websites don't need stealth
                    meta={
                        'company': company, 'position': position,
                        'city': city, 'description': description,
                        'contact_name': contact_name, 'job_url': str(response.url),
                        'source_site': 'emploi_ma',
                        'company_domain': domain,
                    },
                )

    async def parse_emploi_company(self, response):
        """Parse Emploi.ma company profile → find website."""
        meta = response.meta
        html = str(response.html_content)

        all_links = [str(l) for l in response.css('a::attr(href)').getall()]
        website_url = find_external_website(
            all_links,
            skip_domains=SOCIAL_DOMAINS | {'emploi.ma'},
        )

        if not website_url:
            url_match = re.search(
                r'https?://(?:www\.)?[a-zA-Z0-9.-]+\.[a-z]{2,}',
                html[:10000],
            )
            if url_match:
                found = url_match.group(0)
                if not any(d in found.lower() for d in SOCIAL_DOMAINS):
                    website_url = found

        if not website_url and meta.get('company'):
            website_url = guess_website(meta['company'])

        if website_url:
            domain = extract_domain(website_url)
            yield Request(
                website_url, callback=self.parse_company_website,
                sid="fast",
                meta={
                    **meta, 'source_site': 'emploi_ma',
                    'company_domain': domain,
                },
            )

    # ═══════════════════════════════════════════════════════
    #  Bayt.com (MENA job board — Morocco section)
    # ═══════════════════════════════════════════════════════

    async def parse_bayt_search(self, response):
        """Parse Bayt.com search results page (Morocco jobs)."""
        keyword = response.meta.get('keyword', '')
        page = response.meta.get('page', 1)
        html = str(response.html_content)

        # ── JSON-LD ItemList (most reliable — 30 job URLs per page) ──
        job_urls = []
        for script in response.css(
            'script[type="application/ld+json"]::text'
        ).getall():
            try:
                data = json.loads(str(script))
                if isinstance(data, dict) and data.get('@type') == 'ItemList':
                    for item in data.get('itemListElement', []):
                        url = item.get('url', '')
                        if url and '/jobs/' in url:
                            job_urls.append(url)
            except (json.JSONDecodeError, AttributeError):
                continue

        # ── Fallback: h2 a links ──
        if not job_urls:
            for a in response.css('h2 a[href]'):
                href = str(a.attrib.get('href', ''))
                if '/jobs/' in href and re.search(r'-\d+/$', href):
                    job_urls.append(response.urljoin(href))

        self.logger.info(
            f"[Bayt] Found {len(job_urls)} jobs "
            f"for '{keyword}' (page {page})"
        )

        # ── Extract company + city from job cards for pre-population ──
        # Card structure:
        #   <div class="job-company-location-wrapper">
        #     <a href="/en/company/slug/">Company Name</a>
        #     <div class="t-mute t-small">
        #       <a href="..."><span>City</span></a> · <a><span>Morocco</span></a>
        #     </div>
        #   </div>
        card_data = {}
        for card in response.css('div[class*="job-company-location-wrapper"]'):
            company_els = card.css('a[href*="/company/"]')
            if company_els:
                company_el = company_els[0]
                company_name = str(company_el.css('::text').get() or '').strip()
                company_href = str(company_el.attrib.get('href', ''))
                city_spans = card.css('div.t-small a span::text').getall()
                city = str(city_spans[0] if city_spans else '').strip()
                # The city is the first span (Marrakech), second is country (Morocco)
                if city.lower() == 'morocco':
                    city = str(city_spans[1] if len(city_spans) > 1 else '').strip()
                    if city.lower() == 'morocco':
                        city = ''
                # Associate with the next job URL by position
                card_data[len(card_data)] = {
                    'company': company_name,
                    'company_link': company_href,
                    'city': city,
                }

        for idx, url in enumerate(job_urls):
            pre = card_data.get(idx, {})
            yield Request(
                str(url), callback=self.parse_bayt_detail,
                sid="fast",
                meta={
                    'keyword': keyword,
                    'card_company': pre.get('company', ''),
                    'card_city': pre.get('city', ''),
                    'card_company_link': pre.get('company_link', ''),
                },
            )

        # ── Pagination (max 5 pages per keyword) ──
        if page < 5:
            next_link = response.css('ul.pagination a[href*="page="]')
            for a in next_link:
                href = str(a.attrib.get('href', ''))
                text = str(a.css('::text').get() or '').strip()
                if text == str(page + 1):
                    yield Request(
                        str(response.urljoin(href)),
                        callback=self.parse_bayt_search,
                        sid="fast",
                        meta={'keyword': keyword, 'page': page + 1},
                    )
                    break

    async def parse_bayt_detail(self, response):
        """Parse Bayt.com job detail page — extract data from JSON-LD."""
        html = str(response.html_content)
        card_company = response.meta.get('card_company', '')
        card_city = response.meta.get('card_city', '')
        card_company_link = response.meta.get('card_company_link', '')

        # ── JSON-LD JobPosting (has all structured data) ──
        company = ''
        city = ''
        position = ''
        description = ''
        company_logo = ''

        for script in response.css(
            'script[type="application/ld+json"]::text'
        ).getall():
            try:
                data = json.loads(str(script))
                if not isinstance(data, dict):
                    continue
                if data.get('@type') != 'JobPosting':
                    continue

                position = data.get('title', '').strip()

                org = data.get('hiringOrganization', {})
                if isinstance(org, dict):
                    company = org.get('name', '').strip()
                    company_logo = org.get('logo', '')

                loc = data.get('jobLocation', {})
                if isinstance(loc, dict):
                    addr = loc.get('address', {})
                    if isinstance(addr, dict):
                        city = (
                            addr.get('addressLocality', '')
                            or addr.get('addressRegion', '')
                        ).strip()

                raw_desc = data.get('description', '')
                if raw_desc:
                    clean = re.sub(r'<[^>]+>', ' ', raw_desc)
                    description = re.sub(r'\s+', ' ', clean).strip()[:500]
                break
            except (json.JSONDecodeError, AttributeError):
                continue

        # ── Fallback to card data ──
        if not company:
            company = card_company
        if not city:
            city = card_city
        if not position:
            h1 = response.css('h1::text').get()
            position = str(h1 or '').strip()

        # ── Skip non-companies ──
        if not company:
            return
        if company.lower().strip() in SKIP_COMPANY_NAMES:
            return

        # Dedup by company
        company_key = company.lower().strip()
        if company_key in self._seen_companies:
            return
        self._seen_companies.add(company_key)

        # ── Check for emails on the detail page ──
        emails = extract_emails_from_text(html)
        emails = [
            e for e in emails
            if 'bayt.com' not in e and 'example' not in e
        ]

        if emails:
            for email in emails:
                if email not in self._seen_emails:
                    self._seen_emails.add(email)
                    yield make_contact_dict(
                        company=company, email=email, position=position,
                        city=city, source_url=str(response.url),
                        source_site='bayt', description=description,
                    )
            return

        # ── Email in description text ──
        desc_emails = extract_emails_from_text(description)
        desc_emails = [e for e in desc_emails if 'bayt' not in e.lower()]
        if desc_emails:
            for email in desc_emails:
                if email not in self._seen_emails:
                    self._seen_emails.add(email)
                    yield make_contact_dict(
                        company=company, email=email, position=position,
                        city=city, source_url=str(response.url),
                        source_site='bayt', description=description,
                    )
            return

        # ── URL in description → follow company website ──
        url_match = re.search(
            r'https?://(?:www\.)?[a-zA-Z0-9.-]+\.[a-z]{2,}',
            description,
        )
        website_url = None
        if url_match:
            found = url_match.group(0)
            if not any(d in found.lower() for d in SOCIAL_DOMAINS):
                website_url = found

        # ── Guess website from company name ──
        if not website_url:
            website_url = guess_website(company)

        if website_url:
            domain = extract_domain(website_url)
            if domain not in GENERIC_SKIP_DOMAINS and domain not in self._visited_domains:
                yield Request(
                    website_url, callback=self.parse_company_website,
                    sid="fast",
                    meta={
                        'company': company, 'position': position,
                        'city': city, 'description': description,
                        'job_url': str(response.url),
                        'source_site': 'bayt',
                        'company_domain': domain,
                    },
                )

    # ═══════════════════════════════════════════════════════
    #  Shared — Company Website Parsing
    # ═══════════════════════════════════════════════════════

    async def parse_company_website(self, response):
        """Parse company website homepage for emails."""
        meta = response.meta
        domain = meta.get('company_domain', '')
        source_site = meta.get('source_site', 'unknown')
        html = str(response.html_content)

        # Track visited base domains to avoid re-crawling
        base_domain = extract_domain(str(response.url))
        if base_domain in self._visited_domains:
            return
        self._visited_domains.add(base_domain)

        emails = find_relevant_emails(html, domain)

        if emails:
            for email in emails:
                if email not in self._seen_emails:
                    self._seen_emails.add(email)
                    yield make_contact_dict(
                        company=meta.get('company', ''),
                        email=email,
                        position=meta.get('position', ''),
                        city=meta.get('city', ''),
                        source_url=meta.get('job_url', ''),
                        source_site=source_site,
                        description=meta.get('description', ''),
                        contact_name=meta.get('contact_name', ''),
                    )
            return

        # Try contact pages
        base_url = str(response.url).rstrip('/')
        for path in CONTACT_PATHS:
            yield Request(
                base_url + path,
                callback=self.parse_contact_page,
                sid="fast",
                meta=meta,
            )

    async def parse_contact_page(self, response):
        """Parse contact/career page for emails."""
        meta = response.meta
        domain = meta.get('company_domain', '')
        source_site = meta.get('source_site', 'unknown')
        html = str(response.html_content)

        emails = find_relevant_emails(html, domain)

        for email in emails:
            if email not in self._seen_emails:
                self._seen_emails.add(email)
                yield make_contact_dict(
                    company=meta.get('company', ''),
                    email=email,
                    position=meta.get('position', ''),
                    city=meta.get('city', ''),
                    source_url=meta.get('job_url', ''),
                    source_site=source_site,
                    description=meta.get('description', ''),
                    contact_name=meta.get('contact_name', ''),
                )
