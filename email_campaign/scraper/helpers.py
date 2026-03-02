"""
══════════════════════════════════════════════════════════════
  Shared helpers for all spiders
══════════════════════════════════════════════════════════════

  Email extraction, validation, relevance scoring, domain
  guessing, and company name filtering utilities.
"""

import re
from datetime import datetime
from urllib.parse import unquote

# ═══════════════════════════════════════════════════════════
#  Email Extraction
# ═══════════════════════════════════════════════════════════

EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
)

# Prefixes to skip (noreply/system addresses)
# NOTE: 'contact' and 'info' are intentionally NOT skipped
SKIP_EMAILS = {
    'noreply', 'no-reply', 'no_reply', 'mailer-daemon',
    'postmaster', 'webmaster', 'donotreply',
}

# Domains to skip (tracking, analytics, CMS themes, placeholder)
SKIP_DOMAINS = {
    'sentry.io', 'sentry.dev', 'example.com', 'email.com',
    'test.com', 'localhost', 'wixpress.com',
    'googleusercontent.com', 'placeholder.com',
    'rofyhost.net', 'cloudflare.com', 'amazonaws.com',
    'w3.org', 'schema.org', 'gravatar.com',
    'favethemes.com', 'developer.wordpress.org',
    'developer.mozilla.org', 'developer.android.com',
    'developer.apple.com', 'developer.chrome.com',
    'developer.google.com', 'developer.github.com',
    'developer.microsoft.com', 'developer.paypal.com',
    'developer.wordpress.com', 'developer.shopify.com',
    'developer.wix.com', 'developer.squarespace.com',
    'developer.weebly.com', 'developer.zendesk.com',
    'developer.salesforce.com', 'developer.atlassian.com',
    'developer.hashicorp.com', 'developer.nvidia.com',
    'developer.samsung.com', 'developer.uber.com',
    'developer.stripe.com', 'developer.twitch.tv',
    'developer.ibm.com', 'developer.stackoverflow.com',
}

# Recruiter-style email prefixes (for prioritization)
RECRUITER_PREFIXES = [
    'recrutement', 'rh', 'hr', 'careers', 'jobs', 'emploi',
    'recruitment', 'talent', 'stage', 'contact', 'info',
]

# Social / job-board / infrastructure domains to skip when looking for company websites
SOCIAL_DOMAINS = {
    'facebook.com', 'linkedin.com', 'twitter.com', 'x.com',
    'instagram.com', 'youtube.com', 'tiktok.com', 'google.com',
    'whatsapp.com', 'rekrute.com', 'emploi.ma', 'marocannonces.com',
    'exekutive.biz', 'enkontact.com',
    'w3.org', 'w3schools.com', 'wikipedia.org', 'github.com',
    'stackoverflow.com', 'cloudflare.com', 'googleapis.com',
    'gstatic.com', 'jquery.com', 'bootstrapcdn.com',
    'fontawesome.com', 'cdnjs.com', 'unpkg.com',
}

# Contact/career page paths to check on company websites (kept short to avoid 404 spam)
CONTACT_PATHS = [
    '/contact', '/contactez-nous', '/nous-contacter', '/careers',
]

# Generic / unrelated domains to skip during company website guessing
# (these are world-famous brands that share slugs with Moroccan company names)
GENERIC_SKIP_DOMAINS = {
    'genius.com', 'oracle.com', 'apple.com', 'amazon.com',
    'microsoft.com', 'google.com', 'meta.com', 'ibm.com',
    'deloitte.com', 'dxc.com', 'manpower.com', 'accenture.com',
    'capgemini.com', 'atos.com', 'sopra.com', 'cgi.com',
}

# Known Moroccan cities for extraction
KNOWN_CITIES = {
    'casablanca', 'rabat', 'marrakech', 'fes', 'fès', 'tanger',
    'agadir', 'oujda', 'kenitra', 'meknes', 'meknès', 'sale', 'salé',
    'temara', 'mohammedia', 'safi', 'khouribga', 'beni-mellal',
    'nador', 'tetouan', 'settat', 'berrechid', 'khemisset',
    'benguerir', 'laayoune', 'laâyoune', 'dakhla', 'el-jadida',
    'skhirat', 'ain-sebaa', 'hay-hassani', 'sidi-bernoussi',
    'remote', 'maroc', 'sala-al-jadida', 'beni mellal',
    'el jadida', 'taza', 'guelmim', 'errachidia',
}

# City name normalizations
CITY_MAP = {
    'casa': 'Casablanca', 'casablanca': 'Casablanca',
    'rabat': 'Rabat', 'sale': 'Salé', 'salé': 'Salé',
    'fes': 'Fès', 'fès': 'Fès', 'marrakech': 'Marrakech',
    'tanger': 'Tanger', 'tangier': 'Tanger',
    'oujda': 'Oujda', 'agadir': 'Agadir',
    'meknes': 'Meknès', 'meknès': 'Meknès',
    'kenitra': 'Kénitra', 'kénitra': 'Kénitra',
    'tetouan': 'Tétouan', 'tétouan': 'Tétouan',
    'remote': 'Remote', 'télétravail': 'Télétravail',
    'teletravail': 'Télétravail',
}

# Common Moroccan / French first names (for filtering out person names)
COMMON_FIRST_NAMES = {
    'mohamed', 'mohammed', 'ahmed', 'youssef', 'rachid', 'mustapha',
    'mustafa', 'abdellah', 'abdelkader', 'abdelkhaleq', 'abdelhak',
    'omar', 'hassan', 'ismail', 'karim', 'brahim', 'said', 'saïd',
    'ali', 'khalid', 'hamid', 'aziz', 'nabil', 'adil', 'jawad',
    'hicham', 'mehdi', 'amine', 'oussama', 'mourad',
    'soufiane', 'zakaria', 'imad', 'badr', 'driss', 'ilyas',
    'fatima', 'meriem', 'meryem', 'khadija', 'salwa', 'imane',
    'houda', 'sanaa', 'naima', 'rajae', 'ikram', 'laila', 'leila',
    'amina', 'zineb', 'siham', 'najat', 'loubna', 'souad', 'hanane',
    'asmae', 'samira', 'nadia', 'ghita', 'rim', 'sara', 'wafaa',
    'maryam', 'hajar', 'fouzia', 'malika', 'karima', 'latifa',
    'jean', 'pierre', 'antoine', 'françois', 'marie', 'sophie',
    'philippe', 'christophe', 'thierry', 'laurent',
}

# Keywords that indicate a real company name
COMPANY_HINTS = {
    'sarl', 'sas', 'sa', 'groupe', 'group', 'société', 'societe',
    'ste', 'international', 'consulting', 'services', 'maroc',
    'morocco', 'technologies', 'tech', 'digital', 'solutions',
    'laboratoire', 'labo', 'cabinet', 'agence', 'agency',
    'institut', 'centre', 'center', 'industrie', 'industries',
    'holding', 'capital', 'invest', 'finance', 'bank', 'banque',
    'assurance', 'insurance', 'transport', 'logistique',
    'informatique', 'systems', 'systèmes', 'construction',
    'immobilier', 'pharma', 'medical', 'médicales',
    'performance', 'global', 'pro', 'plus', 'express',
    'assistance', 'recrutement', 'recruitment',
}

# Placeholder company names to skip
SKIP_COMPANY_NAMES = {
    'confidentiel', 'sarl', 'n/a', 'anonyme', 'particulier',
    'non spécifié', 'nc', 'inconnu', 'privé',
}

# Relevance keywords
HIGH_RELEVANCE_KEYWORDS = [
    'react', 'node.js', 'nodejs', 'javascript', 'full stack',
    'fullstack', 'laravel', 'php', 'vue.js', 'vuejs',
    'next.js', 'nextjs', 'flutter', 'react native',
]

MEDIUM_RELEVANCE_KEYWORDS = [
    'java', 'spring boot', 'angular', 'python', 'django',
    'devops', 'docker', 'typescript', 'express',
]


# ═══════════════════════════════════════════════════════════
#  Functions
# ═══════════════════════════════════════════════════════════

def extract_emails_from_text(text):
    """Find all valid email addresses in a block of text."""
    if not text:
        return []
    # Decode URL-encoded entities (e.g. %20ciftanger → ciftanger)
    text = unquote(text)
    emails = EMAIL_PATTERN.findall(text)
    result = []
    for e in emails:
        e_lower = e.lower()
        prefix = e_lower.split('@')[0]
        domain = e_lower.split('@')[1] if '@' in e_lower else ''
        if prefix in SKIP_EMAILS:
            continue
        if any(skip in domain for skip in SKIP_DOMAINS):
            continue
        result.append(e_lower.strip())
    return result


def find_relevant_emails(text, domain=''):
    """Find emails, prioritizing company-domain and recruiter-prefixed ones."""
    all_emails = extract_emails_from_text(text)
    all_emails = [
        e for e in all_emails
        if 'exemple' not in e and 'example' not in e and 'test@' not in e
    ]
    if not all_emails:
        return []

    if domain:
        domain_emails = [e for e in all_emails if domain in e]
        if domain_emails:
            return domain_emails[:3]

    recruiter = [
        e for e in all_emails
        if any(p in e.split('@')[0].lower() for p in RECRUITER_PREFIXES)
    ]
    if recruiter:
        return recruiter[:3]

    return all_emails[:3]


def extract_domain(url):
    """Extract domain from URL (e.g. 'sofrecom.com' from 'https://www.sofrecom.com/')."""
    m = re.search(r'https?://(?:www\.)?([^/]+)', url)
    return m.group(1) if m else ''


def guess_website(company):
    """Guess the most likely website URL from company name."""
    slug = re.sub(r'[^a-z0-9\s]', '', company.lower()).strip()
    slug = re.sub(r'\s+', '', slug)
    if not slug or len(slug) < 3:
        return None
    return f'https://www.{slug}.ma'


def all_website_guesses(company):
    """Generate plausible website URLs for a company (Moroccan bias: .ma first)."""
    slug = re.sub(r'[^a-z0-9\s]', '', company.lower()).strip()
    slug = re.sub(r'\s+', '', slug)
    if not slug or len(slug) < 3:
        return []
    urls = [f'https://www.{slug}.ma']
    # Only add .com if the slug is long enough to be specific (avoid genius.com etc.)
    if len(slug) >= 6 and f'{slug}.com' not in GENERIC_SKIP_DOMAINS:
        urls.append(f'https://www.{slug}.com')
    return urls


def normalize_city(city):
    """Normalize a Moroccan city name."""
    if not city:
        return ''
    city = re.sub(r'\s+', ' ', city).strip()
    return CITY_MAP.get(city.lower(), city.title())


def looks_like_company(name):
    """Determine if a name looks like a real company vs a person."""
    if not name:
        return False
    clean = name.strip()
    words = clean.split()
    lower_words = [w.lower() for w in words]

    # Honorifics → definitely a person
    HONORIFICS = {'mme', 'mlle', 'mr', 'msr', 'dr', 'prof', 'sir', 'mister', 'madame', 'monsieur'}
    if lower_words[0] in HONORIFICS:
        return False

    # Company keywords → definite yes
    if any(w in COMPANY_HINTS for w in lower_words):
        return True

    # Single word ≤ 3 chars all caps → initials
    if len(words) == 1 and len(clean) <= 3 and clean.isupper():
        return False

    # 2 words both ≤ 2 chars → initials
    if len(words) == 2 and all(len(w.replace('.', '')) <= 2 for w in words):
        return False

    # First word is a common first name → person
    if lower_words[0] in COMMON_FIRST_NAMES:
        return False

    # 2 words, either is a first name → person
    if len(words) == 2:
        if any(w in COMMON_FIRST_NAMES for w in lower_words):
            return False

    # Single word ≥ 5 chars → likely company
    if len(words) == 1 and len(clean) >= 5:
        return True

    # 2+ words, total ≥ 6 chars → likely company
    if len(words) >= 2 and len(clean) >= 6:
        return True

    return False


def score_relevance(position='', description=''):
    """Score a contact 1-3 stars based on job keywords."""
    text = f"{position} {description}".lower()

    high_hits = sum(1 for k in HIGH_RELEVANCE_KEYWORDS if k in text)
    medium_hits = sum(1 for k in MEDIUM_RELEVANCE_KEYWORDS if k in text)

    if high_hits >= 1:
        return 3
    elif medium_hits >= 1:
        return 2
    return 1


def make_contact_dict(company, email, position, city='', source_url='',
                      source_site='', description='', contact_name=''):
    """Create a standardized contact dictionary."""
    return {
        'company': company or '—',
        'email': email.lower().strip(),
        'position': position or '—',
        'city': normalize_city(city),
        'source_url': source_url or '',
        'source_site': source_site,
        'scraped_at': datetime.now().isoformat(),
        'job_description': description or '',
        'contact_name': contact_name or '',
        'relevance': score_relevance(position, description),
    }


def is_valid_email(email):
    """Check if email has valid format."""
    pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    return bool(pattern.match(email))


def find_external_website(links, skip_domains=None):
    """Find the first external website link from a list, skipping social/job boards."""
    if skip_domains is None:
        skip_domains = SOCIAL_DOMAINS
    for link in links:
        if not link or not link.startswith('http'):
            continue
        if any(d in link.lower() for d in skip_domains):
            continue
        return link
    return None
