"""
══════════════════════════════════════════════════════════════
  Post-Processing Pipeline — Validate, score, deduplicate & export
══════════════════════════════════════════════════════════════

  Replaces the old Scrapy pipelines. Processes a list of
  contact dicts returned by the Scrapling spider.

  Pipeline steps (in order):
    1. validate      — Drop contacts missing required fields
    2. score         — Score 1-3 stars based on keywords
    3. deduplicate   — Remove duplicate emails (keep highest relevance)
    4. export_md     — Write contacts to .md (same format parse_contacts.py expects)
    5. export_json   — Write raw JSON for programmatic use
"""

import json
import os
import re
import logging
from datetime import datetime
from pathlib import Path

from .helpers import is_valid_email, score_relevance

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  Output directory
# ═══════════════════════════════════════════════════════════

SCRAPER_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scraper_output"
)


# ═══════════════════════════════════════════════════════════
#  1. Validation
# ═══════════════════════════════════════════════════════════

def validate(contacts):
    """Drop contacts that don't have a valid email."""
    valid = []
    dropped = 0
    for c in contacts:
        email = (c.get('email') or '').strip().lower()
        if not email or not is_valid_email(email):
            dropped += 1
            continue
        c['email'] = email
        c.setdefault('company', '—')
        c.setdefault('position', '—')
        if not c['company'] or c['company'] == '—':
            c['company'] = '—'
        if not c['position'] or c['position'] == '—':
            c['position'] = '—'
        valid.append(c)

    if dropped:
        logger.info(f"Validation: dropped {dropped} invalid contacts")
    return valid


# ═══════════════════════════════════════════════════════════
#  2. Relevance Scoring
# ═══════════════════════════════════════════════════════════

def score(contacts):
    """Score contacts 1-3 stars based on job keywords."""
    for c in contacts:
        c['relevance'] = score_relevance(
            c.get('position', ''),
            c.get('job_description', ''),
        )
    return contacts


# ═══════════════════════════════════════════════════════════
#  3. Deduplication
# ═══════════════════════════════════════════════════════════

def deduplicate(contacts):
    """Remove duplicate emails, keeping the highest-relevance version."""
    seen = {}  # email -> (index, relevance)
    for i, c in enumerate(contacts):
        email = c['email']
        rel = c.get('relevance', 1)
        if email in seen:
            prev_i, prev_rel = seen[email]
            if rel > prev_rel:
                seen[email] = (i, rel)
        else:
            seen[email] = (i, rel)

    keep_indices = {idx for idx, _ in seen.values()}
    deduped = [c for i, c in enumerate(contacts) if i in keep_indices]
    removed = len(contacts) - len(deduped)
    if removed:
        logger.info(f"Deduplication: removed {removed} duplicate emails")
    return deduped


# ═══════════════════════════════════════════════════════════
#  4. Markdown Export
# ═══════════════════════════════════════════════════════════

def export_markdown(contacts, output_dir=None):
    """
    Export contacts as markdown in the EXACT format parse_contacts.py expects.
    Returns path to the latest file.
    """
    output_dir = output_dir or SCRAPER_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    if not contacts:
        logger.warning("No contacts to export — no markdown file created.")
        return None

    timestamp = datetime.now().strftime('%d/%m/%Y')
    filename = f"scraped_contacts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    filepath = os.path.join(output_dir, filename)
    latest_path = os.path.join(output_dir, "scraped_contacts_latest.md")

    content = _generate_markdown(contacts, timestamp)

    for path in [filepath, latest_path]:
        Path(path).write_text(content, encoding='utf-8')

    logger.info(f"Exported {len(contacts)} contacts to {filepath}")
    logger.info(f"Latest contacts available at {latest_path}")

    return latest_path


def _generate_markdown(contacts, timestamp):
    """Generate markdown in the exact format parse_contacts.py expects."""
    lines = []

    # ── Header ──
    lines.append("# 📧 Emails de Prospection — Contacts Scrapés")
    lines.append("")
    lines.append(f"> Fichier généré automatiquement le {timestamp}")
    lines.append("> Contacts extraits par le scraper depuis les sites d'emploi")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Summary table ──
    lines.append("## 📋 Récapitulatif des Contacts")
    lines.append("")
    lines.append("| # | Entreprise | Email | Poste | Ville | Pertinence |")
    lines.append("|---|-----------|-------|-------|-------|------------|")

    # Sort: 3 stars first, then 2, then 1
    sorted_contacts = sorted(
        contacts,
        key=lambda c: c.get('relevance', 1),
        reverse=True,
    )

    for i, contact in enumerate(sorted_contacts, 1):
        company = contact.get('company', '—') or '—'
        email = contact.get('email', '')
        position = contact.get('position', '—') or '—'
        city = contact.get('city', '—') or '—'
        relevance = contact.get('relevance', 1)
        stars = '⭐' * relevance

        lines.append(
            f"| {i} | {company} | {email} | {position} | {city} | {stars} |"
        )

    lines.append("")
    lines.append(
        "> **Légende pertinence :** "
        "⭐⭐⭐ = Très pertinent (Full Stack JS/PHP) · "
        "⭐⭐ = Pertinent · "
        "⭐ = Moins adapté au profil"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Stats ──
    total = len(contacts)
    star3 = sum(1 for c in contacts if c.get('relevance') == 3)
    star2 = sum(1 for c in contacts if c.get('relevance') == 2)
    star1 = sum(1 for c in contacts if c.get('relevance') == 1)

    sources = {}
    for c in contacts:
        src = c.get('source_site', 'unknown')
        sources[src] = sources.get(src, 0) + 1

    lines.append("## 📊 Statistiques du Scraping")
    lines.append("")
    lines.append(f"- **Total contacts:** {total}")
    lines.append(f"- **⭐⭐⭐ Très pertinent:** {star3}")
    lines.append(f"- **⭐⭐ Pertinent:** {star2}")
    lines.append(f"- **⭐ Moins pertinent:** {star1}")
    lines.append("")

    for src, count in sources.items():
        lines.append(f"- **Source {src}:** {count} contacts")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "> ⚠️ **Note:** Ce fichier ne contient que le tableau des contacts. "
        "Pour générer les emails personnalisés, utilisez:\n"
        "> `python main.py --generate-emails scraped_contacts_latest.md`"
    )

    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════
#  5. JSON Export
# ═══════════════════════════════════════════════════════════

def export_json(contacts, output_dir=None):
    """Export contacts as JSON for programmatic access."""
    output_dir = output_dir or SCRAPER_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    if not contacts:
        return None

    filepath = os.path.join(output_dir, "scraped_contacts_latest.json")
    data = {
        'scraped_at': datetime.now().isoformat(),
        'total': len(contacts),
        'contacts': contacts,
    }

    Path(filepath).write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )

    logger.info(f"Exported JSON to {filepath}")
    return filepath


# ═══════════════════════════════════════════════════════════
#  Full Pipeline
# ═══════════════════════════════════════════════════════════

def process_contacts(contacts, output_dir=None):
    """
    Run the full post-processing pipeline on scraped contacts.

    Args:
        contacts: List of contact dicts from spider
        output_dir: Optional output directory override

    Returns:
        Tuple of (processed_contacts, md_path, json_path)
    """
    logger.info(f"Processing {len(contacts)} raw contacts...")

    # 1. Validate
    contacts = validate(contacts)
    logger.info(f"After validation: {len(contacts)}")

    # 2. Score relevance
    contacts = score(contacts)

    # 3. Deduplicate
    contacts = deduplicate(contacts)
    logger.info(f"After dedup: {len(contacts)}")

    # 4. Export markdown
    md_path = export_markdown(contacts, output_dir)

    # 5. Export JSON
    json_path = export_json(contacts, output_dir)

    return contacts, md_path, json_path
