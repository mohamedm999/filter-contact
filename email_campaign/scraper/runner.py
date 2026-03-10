"""
══════════════════════════════════════════════════════════════
  Scrapling Runner — Run spider from within the email campaign
══════════════════════════════════════════════════════════════

  This module lets you run the Scrapling spider programmatically
  from main.py CLI.

  Key changes from old Scrapy runner:
    • Uses Scrapling Spider.start() instead of CrawlerProcess
    • Post-processing replaces Scrapy pipelines
    • Indeed spider powered by JobSpy
    • Same CLI interface (run_scraper / merge_scraped_contacts)
"""

import os
import sys
import logging
from pathlib import Path

# Load .env for API keys
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

logger = logging.getLogger(__name__)

# Ensure the project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ═══════════════════════════════════════════════════════════
#  Search Keywords Configuration
# ═══════════════════════════════════════════════════════════

SEARCH_KEYWORDS = [
    # ── Core stack (FR — Moroccan job boards) ──
    "développeur full stack",
    "développeur web",
    "développeur react",
    "développeur node.js",
    "développeur javascript",
    "développeur typescript",
    "développeur php",
    "développeur laravel",
    "développeur vue.js",
    "développeur NestJS",
    # ── Core stack (EN — multinational companies) ──
    "full stack developer",
    "frontend developer",
    "backend developer",
    "MERN stack developer",
    "react developer",
    "node.js developer",
    # ── DevOps / Docker ──
    "devops",
    "docker developer",
    # ── Stage / Internship ──
    "stage développement web",
    "stage informatique",
    "stage pfe",
    "stage développeur full stack",
]

# Output directory
SCRAPER_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scraper_output"
)


def run_apollo_enrich(contacts_file, min_stars=1, limit=0):
    """
    Enrich contacts in emails_prospection.md using Apollo's free-plan API.

    For each contact Apollo returns:
      • Company website URL (more reliable than guessing)
      • Phone number (alternative contact channel)
      • LinkedIn company page
      • Industry & technology stack (used as AI email generation context)

    Enriched data is saved to a JSON sidecar file next to the contacts file
    so the AI email generator can use it for personalisation.

    Args:
        contacts_file: Path to emails_prospection.md
        min_stars:     Minimum relevance of contacts to enrich (1-3)
        limit:         Max contacts to enrich this session (0 = no limit)

    Returns:
        List of enriched contact dicts (with apollo_* keys added)
    """
    from email_campaign.parse_contacts import EmailProspectionParser
    from .spiders.apollo_spider import enrich_contacts_file, APOLLO_API_KEY
    import json as _json
    from pathlib import Path as _Path

    if not APOLLO_API_KEY:
        print("  ❌ APOLLO_API_KEY not set in .env")
        print("     Add:  APOLLO_API_KEY=your-key-here")
        return []

    contacts_path = _Path(contacts_file)
    if not contacts_path.exists():
        # Try the latest scraped contacts as fallback
        fallback = _Path(SCRAPER_OUTPUT_DIR) / "scraped_contacts_latest.md"
        if fallback.exists():
            print(f"  ⚠️  Main contacts file not found:")
            print(f"     {contacts_file}")
            print(f"  ↩️  Falling back to latest scraped contacts:")
            print(f"     {fallback}\n")
            contacts_file = str(fallback)
        else:
            print(f"  ❌ Contacts file not found: {contacts_file}")
            print(f"  💡 Save your emails_prospection.md file first (Ctrl+S in editor)")
            print(f"     Or run --scrape first to create scraped_contacts_latest.md")
            return []

    parser = EmailProspectionParser(contacts_file)
    result = parser.parse()

    # Target all contacts (enrich gives company info even if they have an email template)
    candidates = [c for c in result.contacts if c.relevance >= min_stars]

    if limit > 0:
        candidates = candidates[:limit]

    print(f"\n{'='*60}")
    print(f"  🔍 APOLLO COMPANY ENRICHMENT (Free Plan)")
    print(f"{'='*60}")
    print(f"  📋 Contacts to enrich: {len(candidates)}")
    print(f"  ⭐ Minimum relevance:  {min_stars} star(s)")
    if limit:
        print(f"  🔢 Limit:              {limit}")
    print(f"\n  Apollo will look up each company to find:")
    print(f"    • Company website URL")
    print(f"    • Phone number")
    print(f"    • LinkedIn company page")
    print(f"    • Industry & tech stack (for AI email personalisation)")
    print()

    # Convert Contact dataclasses → dicts for apollo spider
    contact_dicts = [
        {
            "company":   c.company,
            "email":     c.email,
            "position":  c.position,
            "city":      c.city,
            "relevance": c.relevance,
        }
        for c in candidates
    ]

    enriched = enrich_contacts_file(contact_dicts, verbose=True)

    # Save enrichment sidecar JSON (used by AI email generator for context)
    if enriched:
        sidecar_path = _Path(contacts_file).parent / "apollo_enrichment.json"
        existing = {}
        if sidecar_path.exists():
            try:
                existing = _json.loads(sidecar_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        for c in enriched:
            email = c.get("email", "").lower()
            if email:
                existing[email] = {
                    "apollo_website":   c.get("apollo_website", ""),
                    "apollo_phone":     c.get("apollo_phone", ""),
                    "apollo_linkedin":  c.get("apollo_linkedin", ""),
                    "apollo_industry":  c.get("apollo_industry", ""),
                    "apollo_employees": c.get("apollo_employees", ""),
                    "apollo_tech":      c.get("apollo_tech", ""),
                    "apollo_desc":      c.get("apollo_desc", ""),
                }

        sidecar_path.write_text(
            _json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  💾 Enrichment saved to: {sidecar_path}")
        print(f"     (Used automatically by --generate-emails for AI personalisation)")

    return enriched


def run_apollo_merge(contacts_file, min_stars=1):
    """
    Scrape the company websites found by --apollo-enrich for email addresses,
    then merge the new contacts directly into the main contacts file.

    Flow:
      apollo_enrichment.json
          → scrape each apollo_website for emails
          → new contact dicts
          → saved to scraped_contacts_latest.md
          → merged into emails_prospection.md

    Args:
        contacts_file: Path to emails_prospection.md (merge target)
        min_stars:     Minimum relevance for merging (default 1 = all)
    """
    from pathlib import Path as _Path
    from .spiders.apollo_spider import scrape_websites_from_enrichment
    from .post_processing import process_contacts

    # Apollo enrichment JSON lives next to the contacts file OR in scraper_output
    candidates = [
        _Path(contacts_file).parent / "apollo_enrichment.json",
        _Path(SCRAPER_OUTPUT_DIR) / "apollo_enrichment.json",
    ]
    enrichment_path = next((p for p in candidates if p.exists()), None)

    if not enrichment_path:
        print("  ❌ No apollo_enrichment.json found.")
        print("     Run first:  python main.py --apollo-enrich")
        return

    print(f"\n{'='*60}")
    print(f"  🚀 APOLLO MERGE")
    print(f"{'='*60}")
    print(f"  📂 Enrichment file: {enrichment_path}")
    print(f"  🎯 Target file:     {contacts_file}\n")

    # Step 1 — Scrape websites from enrichment for new emails
    new_contacts = scrape_websites_from_enrichment(str(enrichment_path))

    if not new_contacts:
        print("  ⚠️  No new email contacts found from Apollo websites.")
        print("     The websites may not have public emails, or all were duplicates.")
        return

    # Step 2 — Run post-processing (validate, score, deduplicate, export)
    print(f"\n  📊 Post-processing {len(new_contacts)} raw contacts...")
    processed, md_path, json_path = process_contacts(
        new_contacts, output_dir=SCRAPER_OUTPUT_DIR
    )

    if not processed:
        print("  ⚠️  No valid contacts survived post-processing.")
        return

    print(f"  📝 Saved to: {md_path}")

    # Step 3 — Merge into main contacts file (if it exists)
    from pathlib import Path as _P
    if _P(contacts_file).exists():
        print(f"\n  📥 Merging into {contacts_file}...")
        added, skipped_dup, skipped_low = merge_scraped_contacts(
            scraped_file=md_path,
            target_file=contacts_file,
            min_stars=min_stars,
            auto_generate_emails=False,   # user can run --generate-emails separately
        )
        print(f"\n  ✅ Done! {added} new contacts added to your main file.")
        if added:
            print(f"\n  Next steps:")
            print(f"    python main.py --generate-emails   # AI email for new contacts")
            print(f"    python main.py --preview 5         # Preview emails")
            print(f"    python main.py --send --min-stars 2")
    else:
        print(f"\n  ⚠️  Main contacts file not found: {contacts_file}")
        print(f"     New contacts saved to scraper output. Run:")
        print(f"     python main.py --merge-scraped")


def run_scraper(sites=None, keywords=None, dry_run=False):
    """
    Run the Scrapling spider from within the email campaign tool.

    Args:
        sites:    List of site names to scrape (None = all).
                  Options: 'rekrute', 'emploi_ma', 'maroc_annonces', 'bayt',
                           'linkedin', 'indeed', 'apollo'
        keywords: Comma-separated keywords to search for (None = use defaults).
        dry_run:  If True, just show what would be scraped without running.

    Returns:
        Path to the output markdown file, or None.
    """
    available_sites = [
        'rekrute', 'emploi_ma', 'maroc_annonces', 'bayt',
        'linkedin', 'indeed', 'apollo',
    ]

    # Validate sites
    if sites:
        invalid = [s for s in sites if s not in available_sites]
        if invalid:
            print(f"  ❌ Unknown sites: {', '.join(invalid)}")
            print(f"  Available: {', '.join(available_sites)}")
            return None
        target_sites = sites
    else:
        target_sites = available_sites

    # ── Dry run: just show plan ──
    if dry_run:
        print(f"\n{'='*60}")
        print(f"  🔍 SCRAPER DRY RUN — Preview")
        print(f"{'='*60}")
        print(f"  Sites to scrape:")
        for site in target_sites:
            extra = " (Apollo.io API — HR & CTO contacts)" if site == "apollo" else ""
            print(f"    • {site}{extra}")
        print(f"\n  Keywords:")
        if keywords:
            for kw in keywords.split(','):
                print(f"    • {kw.strip()}")
        else:
            for kw in SEARCH_KEYWORDS[:10]:
                print(f"    • {kw}")
            remaining = len(SEARCH_KEYWORDS) - 10
            if remaining > 0:
                print(f"    ... and {remaining} more")

        print(f"\n  Output directory:")
        print(f"    {SCRAPER_OUTPUT_DIR}")
        print(f"\n  To actually scrape, run:")
        print(f"    python main.py --scrape")
        print(f"{'='*60}\n")
        return None

    # ── Run the spider ──
    print(f"\n{'='*60}")
    print(f"  🕷️  STARTING WEB SCRAPER (Scrapling)")
    print(f"{'='*60}")
    print(f"  Sites: {', '.join(target_sites)}")
    print(f"  This may take several minutes...\n")

    from .post_processing import process_contacts

    raw_contacts = []

    # ── LinkedIn, Indeed, and Apollo use their own non-Scrapling spiders ──
    scrapling_sites = [s for s in target_sites if s not in ('linkedin', 'indeed', 'apollo')]
    has_linkedin = 'linkedin' in target_sites
    has_indeed   = 'indeed'   in target_sites
    has_apollo   = 'apollo'   in target_sites

    if scrapling_sites:
        from .spiders.job_spider import JobBoardSpider

        spider = JobBoardSpider(
            sites=scrapling_sites,
            keywords=keywords,
        )

        print(f"  🚀 Running Scrapling spider ({', '.join(scrapling_sites)})...\n")
        result = spider.start()

        raw_contacts.extend(list(result.items))
        stats = result.stats

        print(f"\n  📊 Spider Stats:")
        print(f"     Requests: {stats.requests_count}")
        print(f"     Items scraped: {stats.items_scraped}")
        print(f"     Items dropped: {stats.items_dropped}")
        if stats.failed_requests_count:
            print(f"     Failed requests: {stats.failed_requests_count}")
        if stats.blocked_requests_count:
            print(f"     Blocked requests: {stats.blocked_requests_count}")

    if has_indeed:
        from .spiders.indeed_spider import run_indeed_spider
        from pathlib import Path as _IndPath

        # ── Recover partial results from previous crash ──
        partial_json = _IndPath(SCRAPER_OUTPUT_DIR) / 'indeed_partial.json'
        if partial_json.exists():
            try:
                import json as _json_ind
                partial = _json_ind.loads(partial_json.read_text(encoding='utf-8'))
                if partial:
                    print(f"\n  🔄 Found {len(partial)} contacts from previous Indeed crash")
                    print(f"     Recovering into this batch...")
                    raw_contacts.extend(partial)
                    partial_json.unlink()
            except Exception as e:
                print(f"  ⚠️  Could not recover Indeed partial results: {e}")

        print(f"\n  💼 Running Indeed spider (JobSpy)...\n")

        # Parse keywords for Indeed
        ind_keywords = None
        if keywords:
            ind_keywords = [k.strip() for k in keywords.split(',')]

        indeed_contacts = run_indeed_spider(keywords=ind_keywords)
        raw_contacts.extend(indeed_contacts)
        print(f"  📊 Indeed: {len(indeed_contacts)} contacts found")

    if has_apollo:
        from .spiders.apollo_spider import run_apollo_spider

        # Parse page count from keywords arg if user passed e.g. "pages=5"
        apollo_pages = 3
        apollo_kwds  = None
        if keywords:
            kw_list = [k.strip() for k in keywords.split(',')]
            page_kw = [k for k in kw_list if k.startswith('pages=')]
            if page_kw:
                try:
                    apollo_pages = int(page_kw[0].split('=')[1])
                except ValueError:
                    pass
                kw_list = [k for k in kw_list if not k.startswith('pages=')]
            if kw_list:
                apollo_kwds = kw_list

        print(f"\n  🔭 Running Apollo.io spider...\n")
        apollo_contacts = run_apollo_spider(pages=apollo_pages, keywords=apollo_kwds)
        raw_contacts.extend(apollo_contacts)
        print(f"  📊 Apollo: {len(apollo_contacts)} contacts found")

    if has_linkedin:
        import asyncio
        from .spiders.linkedin_spider import run_linkedin_spider
        from pathlib import Path as _LiPath

        # ── Recover partial results from previous crash ──
        partial_json = _LiPath(SCRAPER_OUTPUT_DIR) / 'linkedin_partial.json'
        if partial_json.exists():
            try:
                import json as _json
                partial = _json.loads(partial_json.read_text(encoding='utf-8'))
                if partial:
                    print(f"\n  🔄 Found {len(partial)} contacts from previous crashed run")
                    print(f"     Recovering into this batch...")
                    raw_contacts.extend(partial)
                    partial_json.unlink()
                    # Also remove partial markdown
                    partial_md = partial_json.with_suffix('.md')
                    if partial_md.exists():
                        partial_md.unlink()
            except Exception as e:
                print(f"  ⚠️  Could not recover partial results: {e}")

        print(f"\n  🔗 Running LinkedIn spider...\n")

        # Parse keywords for LinkedIn
        li_keywords = None
        if keywords:
            li_keywords = [k.strip() for k in keywords.split(',')]

        linkedin_contacts = asyncio.run(run_linkedin_spider(
            keywords=li_keywords,
        ))
        raw_contacts.extend(linkedin_contacts)
        print(f"  📊 LinkedIn: {len(linkedin_contacts)} contacts found")

    # Post-process contacts
    processed, md_path, json_path = process_contacts(
        raw_contacts, output_dir=SCRAPER_OUTPUT_DIR
    )

    # ── Report results ──
    print(f"\n{'='*60}")
    print(f"  ✅ SCRAPING COMPLETE")
    print(f"{'='*60}")

    if md_path:
        print(f"  📝 Markdown: {md_path}")
    if json_path:
        print(f"  📊 JSON:     {json_path}")
    print(f"  📋 Contacts: {len(processed)}")

    print(f"\n  Next steps:")
    print(f"    1. Review the scraped contacts in the output file")
    print(f"    2. Merge into your main contacts file:")
    print(f"       python main.py --merge-scraped")
    print(f"    3. Generate emails and send:")
    print(f"       python main.py --preview 10")
    print(f"       python main.py --send --min-stars 3")
    print(f"{'='*60}\n")

    return md_path


def run_linkedin_test():
    """
    Run the LinkedIn pipeline in test mode — no login needed.
    Uses mock company data with real websites to test email extraction.
    """
    import asyncio
    from .spiders.linkedin_spider import run_linkedin_test as _run_test
    from .post_processing import process_contacts

    raw_contacts = asyncio.run(_run_test())

    if raw_contacts:
        processed, md_path, json_path = process_contacts(
            raw_contacts, output_dir=SCRAPER_OUTPUT_DIR
        )
        print(f"\n  📝 Output: {md_path}")
        print(f"  📊 JSON:   {json_path}")
        print(f"  📋 Contacts saved: {len(processed)}")
    else:
        print("\n  ⚠️  No contacts found during test.")

    return raw_contacts


def merge_scraped_contacts(scraped_file, target_file, min_stars=1,
                           auto_generate_emails=True):
    """
    Merge scraped contacts into the main emails_prospection.md file.
    Only adds contacts that don't already exist (by email).
    Optionally auto-generates email bodies via OpenAI GPT.

    Args:
        scraped_file:          Path to scraped_contacts_latest.md
        target_file:           Path to emails_prospection.md
        min_stars:             Minimum relevance to merge (1-3)
        auto_generate_emails:  If True, generate email bodies via AI after merging

    Returns:
        Tuple of (added_count, skipped_duplicates, skipped_low_relevance)
    """
    # Import the parser to read both files
    from email_campaign.parse_contacts import EmailProspectionParser

    # Parse existing contacts
    existing_parser = EmailProspectionParser(target_file)
    existing_result = existing_parser.parse()
    existing_emails = {c.email.lower() for c in existing_result.contacts}

    # Parse scraped contacts
    scraped_parser = EmailProspectionParser(scraped_file)
    scraped_result = scraped_parser.parse()

    added = 0
    skipped_dup = 0
    skipped_low = 0

    # Read existing file
    target_path = Path(target_file)
    content = target_path.read_text(encoding='utf-8')
    lines = content.split('\n')

    # Find the end of the table section (last |...| line)
    table_end_idx = 0
    last_index = len(existing_result.contacts)

    for i, line in enumerate(lines):
        if line.strip().startswith('|') and '|' in line[1:]:
            table_end_idx = i

    # Build new rows to insert
    new_rows = []
    for contact in scraped_result.contacts:
        if contact.email.lower() in existing_emails:
            skipped_dup += 1
            continue
        if contact.relevance < min_stars:
            skipped_low += 1
            continue

        last_index += 1
        stars = '⭐' * contact.relevance
        city = contact.city or '—'
        company = contact.company or '—'
        position = contact.position or '—'

        new_rows.append(
            f"| {last_index} | {company} | {contact.email} "
            f"| {position} | {city} | {stars} |"
        )
        existing_emails.add(contact.email.lower())
        added += 1

    if new_rows:
        # Insert new rows after the last table row
        for idx, row in enumerate(new_rows):
            lines.insert(table_end_idx + 1 + idx, row)

        target_path.write_text('\n'.join(lines), encoding='utf-8')

    print(f"\n{'='*60}")
    print(f"  📥 MERGE RESULTS")
    print(f"{'='*60}")
    print(f"  ✅ Added:                {added} new contacts")
    print(f"  🔄 Skipped (duplicate):  {skipped_dup}")
    print(f"  ⭐ Skipped (low stars):  {skipped_low}")
    print(f"  📋 Total in file now:    {len(existing_result.contacts) + added}")
    print(f"{'='*60}\n")

    # Auto-generate email bodies for newly added contacts
    if auto_generate_emails and added > 0:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if api_key:
            print(f"  🤖 Auto-generating email bodies for {added} new contacts...\n")
            from email_campaign.scraper.email_generator import generate_emails_for_contacts
            generate_emails_for_contacts(
                contacts_file=target_file,
                min_stars=min_stars,
                api_key=api_key,
            )
        else:
            print(f"  💡 Tip: Set OPENAI_API_KEY to auto-generate email bodies:")
            print(f"     set OPENAI_API_KEY=sk-your-key-here")
            print(f"     python main.py --generate-emails")
            print()

    return added, skipped_dup, skipped_low
