"""
══════════════════════════════════════════════════════════════
  Company Researcher — Auto-scrape company websites
  Enriches AI email generation with real company context
══════════════════════════════════════════════════════════════

  Before generating an email, this module scrapes the company's
  website (homepage / about page) to extract:
    - Company description & domain of activity
    - Tech stack / technologies mentioned
    - Recent news or projects
    - Company values / culture keywords

  This context is fed to the AI to generate truly personalized
  emails — no more placeholders or guesses.

  Usage:
    researcher = CompanyResearcher()
    context = researcher.research("contact@company.ma")
    # → {"description": "...", "technologies": [...], ...}
"""

import re
import logging
import time
from typing import Dict, Optional, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class CompanyResearcher:
    """
    Scrapes company websites to extract relevant context
    for email personalization.

    Uses simple HTTP requests + HTML parsing (no browser needed).
    Falls back gracefully if site is unreachable.
    """

    # Pages to try scraping (in order of value)
    ABOUT_PATHS = [
        '/about', '/about-us', '/a-propos', '/qui-sommes-nous',
        '/notre-entreprise', '/company', '/about.html',
        '/en/about', '/fr/a-propos',
    ]

    # Max chars to extract from a page
    MAX_TEXT_LENGTH = 3000

    # Cache to avoid re-scraping the same domain
    _cache: Dict[str, Dict] = {}

    def __init__(self, timeout: int = 10, max_retries: int = 1):
        self.timeout = timeout
        self.max_retries = max_retries

    def research(self, email: str, company_name: str = "") -> Dict:
        """
        Research a company based on their email domain.

        Args:
            email:        Contact email (domain is extracted)
            company_name: Optional company name for context

        Returns:
            Dict with keys: description, technologies, culture,
                           domain_activity, raw_text, source_url
        """
        if not email or '@' not in email:
            return self._empty_result()

        domain = email.split('@')[1].lower()

        # Skip generic email providers
        generic = {
            'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
            'live.com', 'aol.com', 'icloud.com', 'protonmail.com',
            'yandex.com', 'zoho.com', 'gmx.com', 'mail.com',
        }
        if domain in generic:
            logger.debug(f"Skipping generic domain: {domain}")
            return self._empty_result()

        # Check cache
        if domain in self._cache:
            logger.debug(f"Cache hit for {domain}")
            return self._cache[domain]

        # Try to scrape the company website
        result = self._scrape_company(domain, company_name)
        self._cache[domain] = result
        return result

    def _scrape_company(self, domain: str, company_name: str) -> Dict:
        """Scrape homepage and about page of a company."""
        import urllib.request
        import urllib.error
        from html.parser import HTMLParser

        base_url = f"https://{domain}"
        result = self._empty_result()
        result['domain'] = domain

        # ── 1. Try homepage ──
        homepage_text = self._fetch_page_text(base_url)
        if homepage_text:
            result['source_url'] = base_url
            result['raw_text'] = homepage_text[:self.MAX_TEXT_LENGTH]

        # ── 2. Try about pages ──
        about_text = ""
        for path in self.ABOUT_PATHS:
            about_url = base_url + path
            text = self._fetch_page_text(about_url)
            if text and len(text) > 100:
                about_text = text
                result['about_url'] = about_url
                break

        # ── 3. Extract structured info ──
        combined_text = (homepage_text or "") + "\n" + (about_text or "")
        if combined_text.strip():
            result['description'] = self._extract_description(combined_text, company_name)
            result['technologies'] = self._extract_technologies(combined_text)
            result['culture'] = self._extract_culture_keywords(combined_text)
            result['domain_activity'] = self._guess_domain_activity(combined_text)
            result['found'] = True

        return result

    def _fetch_page_text(self, url: str) -> Optional[str]:
        """Fetch a URL and extract visible text from HTML."""
        import urllib.request
        import urllib.error

        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; EmailCampaignBot/1.0)',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'fr,en;q=0.9',
        }

        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status != 200:
                        return None
                    content_type = resp.headers.get('Content-Type', '')
                    if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                        return None
                    html_bytes = resp.read(200_000)  # Max 200KB
                    # Detect encoding
                    encoding = 'utf-8'
                    if 'charset=' in content_type:
                        encoding = content_type.split('charset=')[-1].strip()
                    html_text = html_bytes.decode(encoding, errors='replace')
                    return self._html_to_text(html_text)

            except Exception as e:
                logger.debug(f"Failed to fetch {url} (attempt {attempt+1}): {e}")
                if attempt < self.max_retries:
                    time.sleep(1)

        return None

    def _html_to_text(self, html: str) -> str:
        """Extract visible text from HTML, removing scripts/styles/tags."""
        # Remove scripts and styles
        html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<!--.*?-->', ' ', html, flags=re.DOTALL)
        # Remove tags
        html = re.sub(r'<[^>]+>', ' ', html)
        # Decode HTML entities
        import html as html_module
        text = html_module.unescape(html)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _extract_description(self, text: str, company_name: str) -> str:
        """Extract a company description (first meaningful paragraph)."""
        # Look for sentences mentioning the company name or common patterns
        sentences = re.split(r'[.!?]+', text)
        description_parts = []
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 20 or len(sent) > 300:
                continue
            # Prioritize sentences about the company
            if company_name and company_name.lower() in sent.lower():
                description_parts.append(sent)
                if len(description_parts) >= 3:
                    break
            elif any(kw in sent.lower() for kw in [
                'nous sommes', 'we are', 'notre mission', 'our mission',
                'spécialisé', 'specialized', 'leader', 'expert',
                'fondé', 'founded', 'créé', 'created',
                'solutions', 'services', 'accompagn',
            ]):
                description_parts.append(sent)
                if len(description_parts) >= 3:
                    break

        return '. '.join(description_parts)[:500] if description_parts else ""

    # Common tech keywords to look for
    _TECH_KEYWORDS = {
        'react', 'angular', 'vue', 'vue.js', 'next.js', 'nuxt',
        'node.js', 'express', 'django', 'flask', 'laravel', 'symfony',
        'spring', 'java', 'kotlin', 'swift', 'python', 'php', 'ruby',
        'javascript', 'typescript', 'go', 'golang', 'rust', 'c#', '.net',
        'aws', 'azure', 'google cloud', 'gcp', 'docker', 'kubernetes',
        'terraform', 'jenkins', 'ci/cd', 'devops',
        'mongodb', 'postgresql', 'mysql', 'redis', 'elasticsearch',
        'react native', 'flutter', 'ionic', 'android', 'ios',
        'machine learning', 'ai', 'deep learning', 'data science',
        'blockchain', 'web3', 'saas', 'erp', 'crm',
        'wordpress', 'shopify', 'magento', 'prestashop',
        'figma', 'sketch', 'adobe', 'ui/ux',
        'agile', 'scrum', 'kanban', 'microservices', 'api',
        'graphql', 'rest', 'grpc', 'websocket',
    }

    def _extract_technologies(self, text: str) -> List[str]:
        """Extract mentioned technologies from page text."""
        text_lower = text.lower()
        found = []
        for tech in self._TECH_KEYWORDS:
            # Use word boundary for short keywords to avoid false positives
            if len(tech) <= 3:
                if re.search(rf'\b{re.escape(tech)}\b', text_lower):
                    found.append(tech)
            else:
                if tech in text_lower:
                    found.append(tech)
        return sorted(set(found))

    _CULTURE_KEYWORDS = {
        'innovation', 'innovant', 'innovative',
        'agile', 'agilité',
        'collaboration', 'collaboratif', 'teamwork',
        'digital', 'numérique', 'transformation digitale',
        'startup', 'scale-up',
        'responsable', 'rse', 'sustainability', 'durable',
        'excellence', 'qualité', 'quality',
        'diversité', 'diversity', 'inclusion',
        'remote', 'télétravail', 'hybride', 'flexible',
        'international', 'multiculturel',
        'croissance', 'growth', 'expanding',
    }

    def _extract_culture_keywords(self, text: str) -> List[str]:
        """Extract company culture keywords."""
        text_lower = text.lower()
        found = [kw for kw in self._CULTURE_KEYWORDS if kw in text_lower]
        return sorted(set(found))

    _DOMAIN_PATTERNS = {
        'fintech': ['banque', 'bank', 'finance', 'paiement', 'payment', 'assurance', 'insurance', 'fintech'],
        'e-commerce': ['e-commerce', 'ecommerce', 'boutique', 'shop', 'vente', 'marketplace'],
        'santé / health': ['santé', 'health', 'médical', 'medical', 'pharma', 'clinique', 'hôpital'],
        'éducation / edtech': ['éducation', 'education', 'formation', 'training', 'cours', 'e-learning'],
        'immobilier': ['immobilier', 'real estate', 'property', 'logement'],
        'transport / logistique': ['transport', 'logistique', 'logistics', 'livraison', 'delivery', 'fleet'],
        'télécommunications': ['télécom', 'telecom', 'réseau', 'network', 'mobile', 'fibre'],
        'consulting / IT services': ['consulting', 'conseil', 'ssii', 'esn', 'intégration', 'infogérance'],
        'marketing / communication': ['marketing', 'communication', 'publicité', 'advertising', 'seo', 'digital marketing'],
        'industrie / manufacturing': ['industrie', 'manufacturing', 'production', 'usine', 'factory'],
        'agritech': ['agriculture', 'agritech', 'farming', 'agronomie'],
        'tourisme / hospitality': ['tourisme', 'tourism', 'hôtel', 'hotel', 'voyage', 'travel'],
    }

    def _guess_domain_activity(self, text: str) -> str:
        """Guess the company's domain of activity."""
        text_lower = text.lower()
        scores = {}
        for domain, keywords in self._DOMAIN_PATTERNS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[domain] = score

        if scores:
            best = max(scores, key=scores.get)
            return best
        return ""

    def format_for_ai(self, research: Dict) -> str:
        """
        Format research results as context for the AI prompt.
        Returns empty string if no useful data was found.
        """
        if not research.get('found'):
            return ""

        parts = []
        if research.get('description'):
            parts.append(f"Company description: {research['description']}")
        if research.get('domain_activity'):
            parts.append(f"Domain of activity: {research['domain_activity']}")
        if research.get('technologies'):
            parts.append(f"Technologies used: {', '.join(research['technologies'])}")
        if research.get('culture'):
            parts.append(f"Company values: {', '.join(research['culture'])}")

        if not parts:
            return ""

        return "COMPANY RESEARCH (verified from their website):\n" + "\n".join(f"  - {p}" for p in parts)

    @staticmethod
    def _empty_result() -> Dict:
        """Return an empty research result."""
        return {
            'found': False,
            'domain': '',
            'description': '',
            'technologies': [],
            'culture': [],
            'domain_activity': '',
            'raw_text': '',
            'source_url': '',
            'about_url': '',
        }
