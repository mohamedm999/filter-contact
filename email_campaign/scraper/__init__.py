"""
══════════════════════════════════════════════════════════════
  Job Board Scraper Module (Scrapling-based)
  Scrapes job listings → feeds into Email Campaign pipeline
══════════════════════════════════════════════════════════════

  This module automates contact collection from Moroccan job
  boards. It outputs contacts in the same markdown format that
  parse_contacts.py already understands.

  Usage (from CLI):
    python main.py --scrape                    # Scrape all configured sites
    python main.py --scrape --site rekrute     # Scrape only ReKrute
    python main.py --scrape --keywords "react" # Custom keywords
    python main.py --scrape --dry-scrape       # Preview what would be scraped

  Supported job boards:
    - ReKrute.com    (Moroccan job board — fast HTTP)
    - Emploi.ma      (Moroccan job board — stealth browser, CF bypass)
    - MarocAnnonces  (Moroccan classifieds — fast HTTP)

  Architecture:
    Scrapling Spider (multi-session) → Post-Processing → Markdown / JSON
"""

from .runner import run_scraper

__all__ = ['run_scraper']
