"""
══════════════════════════════════════════════════════════════
  Apollo.io Spider — Company Enrichment + Contact Search
══════════════════════════════════════════════════════════════

  FREE PLAN (current):
    ✅ organizations/enrich  — given a domain, return company info
                               (website, phone, LinkedIn, industry, size)
    ✅ organizations/search  — find company domain by name + country
    ❌ mixed_people/search   — requires paid plan (Basic+)
    ❌ people/match          — requires paid plan (Basic+)

  FREE PLAN value:
    • enrich_company_info(domain)   — phone + website + LinkedIn for a known domain
    • find_company_domain(name)     — find the website of a scraped company by name

  PAID PLAN (Basic $49/mo+):
    • run_apollo_spider()           — HR + CTO contact search across Morocco

  CLI usage:
    python main.py --scrape --site apollo          # Full search (paid plan)
    python main.py --apollo-enrich                  # Company enrichment (free plan)
"""

import os
import time
import json
import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

from ..helpers import make_contact_dict, is_valid_email

logger = logging.getLogger(__name__)

# Use requests (better headers, avoids Cloudflare WAF)
try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


# ═══════════════════════════════════════════════════════════
#  Config
# ═══════════════════════════════════════════════════════════

APOLLO_API_BASE = "https://api.apollo.io/v1"
APOLLO_API_KEY  = os.getenv("APOLLO_API_KEY", "")

_HEADERS = {
    "Content-Type":   "application/json",
    "Accept":         "application/json",
    "Cache-Control":  "no-cache",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Connection":      "keep-alive",
}

# HR / Recruiter titles
HR_TITLES = [
    "Responsable RH", "DRH", "Directeur RH",
    "Directeur des Ressources Humaines",
    "Talent Acquisition Manager", "Talent Acquisition Specialist",
    "Recruteur", "Chargé de recrutement", "Chargée de recrutement",
    "Responsable Recrutement", "HR Manager", "Human Resources Manager",
    "Head of HR", "HR Director", "Recruiter",
    "Responsable Ressources Humaines",
]

# Tech decision-maker titles
DECISION_MAKER_TITLES = [
    "CTO", "Chief Technology Officer", "Directeur Technique",
    "VP Engineering", "Head of Engineering",
    "CEO", "PDG", "Fondateur", "Co-Fondateur", "Directeur Général", "DG",
]

ALL_TITLES = HR_TITLES + DECISION_MAKER_TITLES

MOROCCO_LOCATIONS = [
    "Morocco", "Casablanca, Morocco", "Rabat, Morocco",
    "Marrakech, Morocco", "Tanger, Morocco", "Agadir, Morocco",
]


# ═══════════════════════════════════════════════════════════
#  Internal HTTP helper
# ═══════════════════════════════════════════════════════════

def _post(endpoint, payload, max_retries=3):
    """POST to Apollo API — key in X-Api-Key header only (body key causes 422)."""
    url     = f"{APOLLO_API_BASE}/{endpoint}"
    headers = dict(_HEADERS)
    headers["X-Api-Key"] = APOLLO_API_KEY

    for attempt in range(max_retries):
        try:
            if _HAS_REQUESTS:
                resp = _requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    return resp.json(), None
                return None, {"status": resp.status_code, "body": resp.text[:300]}
            else:
                import urllib.request
                data = json.dumps(payload).encode("utf-8")
                req  = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode("utf-8")), None

        except Exception as exc:
            logger.warning(f"Apollo request error attempt {attempt + 1}: {exc}")
            if attempt < max_retries - 1:
                time.sleep(5)

    return None, {"status": 0, "body": "Max retries exceeded"}


def _plan_error(endpoint, error):
    """Return True if the error is a free-plan restriction."""
    body = (error or {}).get("body", "")
    return "free plan" in body.lower() or "API_INACCESSIBLE" in body


# ═══════════════════════════════════════════════════════════
#  FREE PLAN — Company enrichment (organizations/enrich)
# ═══════════════════════════════════════════════════════════

def enrich_company_info(domain):
    """
    Enrich a company by domain using Apollo organizations/enrich (FREE).
    Returns a dict with: name, website, phone, linkedin_url, industry,
    estimated_employees, city — or None if not found.

    Args:
        domain: e.g. 'marjane.ma' or 'techcorp.com'
    """
    if not APOLLO_API_KEY or not domain:
        return None

    result, err = _post("organizations/enrich", {"domain": domain})
    if err or not result:
        logger.debug(f"Apollo enrich failed for '{domain}': {err}")
        return None

    org = result.get("organization") or {}
    if not org:
        return None

    return {
        "name":                org.get("name", ""),
        "website":             org.get("website_url", ""),
        "primary_domain":      org.get("primary_domain", ""),
        "phone":               (org.get("primary_phone") or {}).get("sanitized_number", ""),
        "linkedin_url":        org.get("linkedin_url", ""),
        "industry":            org.get("industry", ""),
        "estimated_employees": org.get("estimated_num_employees"),
        "city":                org.get("city", ""),
        "country":             org.get("country", ""),
        "short_description":   org.get("short_description", ""),
        "technologies":        [t.get("name", "") for t in (org.get("current_technologies") or [])],
    }


# ═══════════════════════════════════════════════════════════
#  FREE PLAN — Find company domain by name (organizations/search)
# ═══════════════════════════════════════════════════════════

def find_company_domain(company_name, city=""):
    """
    Find a company's website/domain by name using Apollo organizations/search (FREE).
    Useful when the job board only gives the company name and no URL.

    Args:
        company_name: e.g. 'Marjane Group'
        city:         Optional city hint e.g. 'Casablanca'

    Returns:
        dict with 'domain', 'website', 'phone', 'linkedin' or None
    """
    if not APOLLO_API_KEY or not company_name:
        return None

    locations = [f"{city}, Morocco"] if city else MOROCCO_LOCATIONS
    payload = {
        "q_organization_name":    company_name,
        "organization_locations": locations,
        "page":      1,
        "per_page":  3,
    }

    result, err = _post("organizations/search", payload)
    if err or not result:
        logger.debug(f"Apollo org search failed for '{company_name}': {err}")
        return None

    orgs = result.get("organizations") or []

    # Find best match — prefer orgs with a domain
    for org in orgs:
        domain  = org.get("primary_domain") or ""
        website = org.get("website_url")    or ""
        if not domain and not website:
            continue
        phone = (
            org.get("sanitized_phone")
            or (org.get("primary_phone") or {}).get("sanitized_number", "")
        )
        return {
            "name":     org.get("name", company_name),
            "domain":   domain,
            "website":  website or (f"https://{domain}" if domain else ""),
            "phone":    phone,
            "linkedin": org.get("linkedin_url", ""),
            "industry": org.get("industry", ""),
            "city":     org.get("city", ""),
        }

    return None


# ═══════════════════════════════════════════════════════════
#  FREE PLAN — --apollo-enrich command helper
# ═══════════════════════════════════════════════════════════

def enrich_contacts_file(contacts, verbose=True):
    """
    For each contact, use Apollo organizations/search + enrich to find:
      • The company website (to scrape for emails)
      • Phone number (alternative contact)
      • LinkedIn company page
      • Industry & tech stack (for AI email context)

    Returns list of enriched contact dicts (adds 'apollo_*' keys).
    """
    if not APOLLO_API_KEY:
        print("  ❌ APOLLO_API_KEY not set in .env")
        return contacts

    enriched_contacts = []
    found = 0

    for i, contact in enumerate(contacts, 1):
        company = contact.get("company", "") or ""
        email   = contact.get("email", "")   or ""
        city    = contact.get("city", "")    or ""

        # Extract domain from email (e.g. hr@techcorp.ma → techcorp.ma)
        domain = email.split("@")[-1] if "@" in email else ""

        # Skip generic providers
        skip_providers = {
            "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
            "live.com", "aol.com"
        }
        if domain in skip_providers:
            domain = ""

        stars = "⭐" * contact.get("relevance", 1)
        if verbose:
            print(f"  [{i}/{len(contacts)}] {stars} {company} ({city})")

        info = None

        # Try enrich by domain first (more accurate)
        if domain:
            info = enrich_company_info(domain)

        # Fall back to name search
        if not info and company:
            org = find_company_domain(company, city)
            if org and org.get("domain"):
                info = enrich_company_info(org["domain"])
                if not info and org:
                    # Use org search result directly
                    info = {
                        "name":     org.get("name", company),
                        "website":  org.get("website", ""),
                        "phone":    org.get("phone", ""),
                        "linkedin_url": org.get("linkedin", ""),
                        "industry": org.get("industry", ""),
                        "city":     org.get("city", ""),
                    }

        if info:
            contact = dict(contact)
            contact["apollo_website"]    = info.get("website", "")
            contact["apollo_phone"]      = info.get("phone", "")
            contact["apollo_linkedin"]   = info.get("linkedin_url", "") or info.get("linkedin", "")
            contact["apollo_industry"]   = info.get("industry", "")
            contact["apollo_employees"]  = info.get("estimated_employees", "")
            contact["apollo_tech"]       = ", ".join(info.get("technologies", [])[:5])
            contact["apollo_desc"]       = info.get("short_description", "")
            found += 1
            if verbose:
                phone = info.get("phone", "")
                web   = info.get("website", "")
                print(f"        ✅ Found: {web or 'no website'} | 📞 {phone or 'no phone'}")
        else:
            if verbose:
                print(f"        ⚠️  Not found on Apollo")

        enriched_contacts.append(contact)

        if i < len(contacts):
            time.sleep(1.5)   # Stay under Apollo rate limits

    print(f"\n  ✅ Apollo enriched {found}/{len(contacts)} contacts")
    return enriched_contacts


# ═══════════════════════════════════════════════════════════
#  FREE PLAN — Scrape websites from enrichment → new contacts
# ═══════════════════════════════════════════════════════════

def scrape_websites_from_enrichment(enrichment_json_path):
    """
    Read apollo_enrichment.json, scrape each apollo_website for email
    addresses, and return new contact dicts ready for post-processing.

    This is what powers --apollo-merge:
      enrichment JSON → scrape websites → new contacts with emails

    Args:
        enrichment_json_path: Path to apollo_enrichment.json

    Returns:
        List of contact dicts (same format as make_contact_dict)
    """
    import json as _json
    from pathlib import Path as _Path

    path = _Path(enrichment_json_path)
    if not path.exists():
        logger.warning(f"Enrichment file not found: {path}")
        return []

    data = _json.loads(path.read_text(encoding="utf-8"))
    if not data:
        return []

    contacts = []
    seen_emails = set(data.keys())   # skip emails we already have

    total = sum(1 for v in data.values() if v.get("apollo_website"))
    print(f"  🌐 Found {total} companies with websites in Apollo enrichment")
    print(f"  🔍 Scraping each website for new email contacts...\n")

    done = 0
    for existing_email, info in data.items():
        website  = info.get("apollo_website") or ""
        industry = info.get("apollo_industry") or ""
        desc     = info.get("apollo_desc") or ""
        phone    = info.get("apollo_phone") or ""

        if not website:
            continue

        # Derive company name from domain (e.g. http://www.cnexia.com → Cnexia)
        domain = website.split("//")[-1].lstrip("www.").split("/")[0].split(".")[0]
        company = domain.title()

        done += 1
        print(f"  [{done}/{total}] {company} — {website}")

        found = _fetch_emails_from_website(website)

        # Also try /contact page
        if not found:
            contact_url = website.rstrip("/") + "/contact"
            found = _fetch_emails_from_website(contact_url)

        if found:
            for email in found:
                if email in seen_emails:
                    continue
                seen_emails.add(email)
                c = make_contact_dict(
                    company=company,
                    email=email,
                    position="—",
                    city="Morocco",
                    source_url=website,
                    source_site="apollo_website",
                    description=f"{industry}. {desc[:200]}".strip(". "),
                    contact_name="",
                )
                # Add phone as extra field (useful for AI context)
                if phone:
                    c["apollo_phone"] = phone
                contacts.append(c)
                print(f"       ✅ {email}")
        else:
            print(f"       ⚠️  No email found")

        time.sleep(1)   # polite crawl rate

    print(f"\n  ✅ Scraped {len(contacts)} new email contacts from Apollo websites")
    return contacts


def _fetch_emails_from_website(url):
    """Fetch a URL and extract email addresses. Returns list of emails."""
    from ..helpers import find_relevant_emails, extract_domain
    try:
        if _HAS_REQUESTS:
            resp = _requests.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                },
                timeout=10,
                allow_redirects=True,
            )
            domain = extract_domain(url)
            return find_relevant_emails(resp.text, domain)
    except Exception as exc:
        logger.debug(f"Fetch error for {url}: {exc}")
    return []


# ═══════════════════════════════════════════════════════════
#  PAID PLAN — Standalone contact search (mixed_people/search)
# ═══════════════════════════════════════════════════════════

def run_apollo_spider(pages=3, per_page=25, keywords=None):
    """
    Standalone Apollo spider: fetch HR & tech decision-maker contacts in Morocco.
    Requires Apollo Basic plan or higher ($49/mo).

    On free plan → shows upgrade instructions.
    """
    if not APOLLO_API_KEY:
        print("  ❌ APOLLO_API_KEY not set in .env")
        return []

    titles = keywords or ALL_TITLES

    print(f"  🔍 Apollo.io — HR & Decision-Maker Search · Morocco")
    print(f"     Titles:   HR/RH, DRH, Talent Acquisition, CTO, CEO ...")
    print(f"     Location: Morocco (Casablanca, Rabat, Marrakech, Tanger ...)")
    print(
        f"     Plan:     {pages} pages × {per_page}/page "
        f"= up to {pages * per_page} candidates\n"
    )

    payload = {
        "person_titles":    titles,
        "person_locations": MOROCCO_LOCATIONS,
        "page":             1,
        "per_page":         per_page,
        "person_seniority": [
            "manager", "director", "vp", "c_suite", "founder", "senior",
        ],
    }

    result, err = _post("mixed_people/search", payload)

    if err and _plan_error("mixed_people/search", err):
        print("  ⚠️  Apollo people search requires a paid plan (Basic $49/mo+).")
        print("     Your current free plan supports company enrichment only.")
        print()
        print("  ✅ What works for FREE on your plan:")
        print("     • python main.py --apollo-enrich")
        print("       Enriches companies in your contacts file with:")
        print("       - Company website URL")
        print("       - Phone number")
        print("       - LinkedIn company page")
        print("       - Industry & technology stack (for AI email context)")
        print()
        print("  💳 To unlock full HR contact search, upgrade at:")
        print("     https://app.apollo.io/#/settings/plans/upgrade")
        return []

    if err or not result:
        logger.error(f"Apollo search failed: {err}")
        return []

    people   = result.get("people") or []
    contacts = []
    for person in people:
        c = _person_to_contact(person)
        if c:
            contacts.append(c)

    all_contacts = list(contacts)

    for page in range(2, pages + 1):
        payload["page"] = page
        result, err = _post("mixed_people/search", payload)
        if err or not result:
            break
        more = result.get("people") or []
        page_contacts = [_person_to_contact(p) for p in more]
        page_contacts = [c for c in page_contacts if c]
        all_contacts.extend(page_contacts)
        print(
            f"  📄 Page {page}: {len(page_contacts)} contacts "
            f"(cumulative: {len(all_contacts)})"
        )
        if not more:
            break
        time.sleep(2)

    print(f"\n  ✅ Apollo search complete: {len(all_contacts)} contacts")
    return all_contacts


def _person_to_contact(person, fallback_position=""):
    """Convert Apollo person dict → standard contact dict."""
    email = (person.get("email") or "").strip()
    if not email or "***" in email or not is_valid_email(email):
        return None

    first = person.get("first_name") or ""
    last  = person.get("last_name")  or ""
    name  = f"{first} {last}".strip()
    title = person.get("title") or fallback_position or "—"

    org     = person.get("organization") or {}
    company = org.get("name") or person.get("organization_name") or "—"
    website = org.get("website_url") or ""

    city    = person.get("city")    or ""
    country = person.get("country") or ""
    if not city and "Morocco" in country:
        city = "Morocco"

    return make_contact_dict(
        company=company, email=email, position=title, city=city,
        source_url=website, source_site="apollo",
        description=f"Apollo: {name} · {title}", contact_name=name,
    )
