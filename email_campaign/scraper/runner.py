"""
══════════════════════════════════════════════════════════════
  Scrapling Runner — Run spider from within the email campaign
══════════════════════════════════════════════════════════════

  This module lets you run the Scrapling spider programmatically
  from main.py CLI.

  Key changes from old Scrapy runner:
    • Uses Scrapling Spider.start() instead of CrawlerProcess
    • Post-processing replaces Scrapy pipelines
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


def run_scraper(sites=None, keywords=None, dry_run=False):
    """
    Run the Scrapling spider from within the email campaign tool.

    Args:
        sites:    List of site names to scrape (None = all).
                  Options: 'rekrute', 'emploi_ma', 'maroc_annonces', 'bayt', 'linkedin'
        keywords: Comma-separated keywords to search for (None = use defaults).
        dry_run:  If True, just show what would be scraped without running.

    Returns:
        Path to the output markdown file, or None.
    """
    available_sites = ['rekrute', 'emploi_ma', 'maroc_annonces', 'bayt', 'linkedin']

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
            print(f"    • {site}")
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

    # ── LinkedIn uses its own Playwright-based spider ──
    scrapling_sites = [s for s in target_sites if s != 'linkedin']
    has_linkedin = 'linkedin' in target_sites

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

    if has_linkedin:
        import asyncio
        from .spiders.linkedin_spider import run_linkedin_spider

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
