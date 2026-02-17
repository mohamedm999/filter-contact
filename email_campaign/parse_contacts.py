"""
══════════════════════════════════════════════════════════════
  Markdown Email Parser
  Parses emails_prospection.md to extract contacts & emails
══════════════════════════════════════════════════════════════
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  Data Models
# ═══════════════════════════════════════════════════════════

@dataclass
class Contact:
    """Represents a single contact from the table."""
    index: int                    # Row number in the table
    company: str                  # Company name
    email: str                    # Email address
    position: str                 # Job position/title
    city: str                     # City
    relevance: int                # Star count (1-3)
    subject: str = ""             # Email subject line
    body: str = ""                # Email body text
    has_custom_email: bool = False # Whether a custom email was found in sections


@dataclass
class ParseResult:
    """Result of parsing the markdown file."""
    contacts: List[Contact]
    total_found: int
    with_custom_email: int
    without_custom_email: int
    duplicates_removed: int
    errors: List[str]


# ═══════════════════════════════════════════════════════════
#  Parser
# ═══════════════════════════════════════════════════════════

class EmailProspectionParser:
    """
    Parses the emails_prospection.md file format.

    Expected format:
    - Table section with | # | Company | Email | Position | City | Relevance |
    - Email sections with ### N. Company — email@domain.com
      **To:** email
      **Subject:** subject line
      Body text...
      ---
    """

    # Regex patterns
    TABLE_ROW_RE = re.compile(
        r'^\|\s*(\d+)\s*\|'           # | 1 |
        r'\s*([^|]*?)\s*\|'            # | Company |
        r'\s*([^|]*?)\s*\|'            # | Email |
        r'\s*([^|]*?)\s*\|'            # | Position |
        r'\s*([^|]*?)\s*\|'            # | City |
        r'\s*([^|]*?)\s*\|'            # | Relevance |
    )

    SECTION_HEADER_RE = re.compile(
        r'^###\s*(\d+)\.\s*(.+?)\s*—\s*(\S+@\S+)',
        re.IGNORECASE
    )

    TO_RE = re.compile(r'^\*\*To:\*\*\s*(.+)', re.IGNORECASE)
    SUBJECT_RE = re.compile(r'^\*\*Subject:\*\*\s*(.+)', re.IGNORECASE)

    STAR_RE = re.compile(r'⭐')

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.errors: List[str] = []

    def parse(self) -> ParseResult:
        """Parse the full markdown file and return structured data."""
        logger.info(f"Parsing file: {self.file_path}")

        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

        content = self.file_path.read_text(encoding='utf-8')
        lines = content.split('\n')

        # Step 1: Parse the contact table
        contacts = self._parse_table(lines)
        logger.info(f"Parsed {len(contacts)} contacts from table")

        # Step 2: Parse email sections and attach to contacts
        self._parse_email_sections(lines, contacts)

        # Step 3: Deduplicate by email (keep first occurrence)
        contacts, dupes_removed = self._deduplicate(contacts)

        # Step 4: Count stats
        with_email = sum(1 for c in contacts if c.has_custom_email)
        without_email = len(contacts) - with_email

        result = ParseResult(
            contacts=contacts,
            total_found=len(contacts),
            with_custom_email=with_email,
            without_custom_email=without_email,
            duplicates_removed=dupes_removed,
            errors=self.errors
        )

        logger.info(
            f"Parse complete: {result.total_found} contacts, "
            f"{result.with_custom_email} with custom emails, "
            f"{result.duplicates_removed} duplicates removed"
        )

        return result

    def _parse_table(self, lines: List[str]) -> List[Contact]:
        """Extract contacts from the markdown table."""
        contacts = []

        for line_num, line in enumerate(lines, 1):
            match = self.TABLE_ROW_RE.match(line.strip())
            if not match:
                continue

            idx, company, email, position, city, relevance_str = match.groups()
            email = email.strip().lower()

            # Validate email
            if not email or '@' not in email:
                self.errors.append(f"Line {line_num}: Invalid email '{email}' for {company}")
                continue

            # Count stars
            stars = len(self.STAR_RE.findall(relevance_str))

            contact = Contact(
                index=int(idx),
                company=company.strip(),
                email=email,
                position=position.strip(),
                city=city.strip() if city.strip() != '—' else '',
                relevance=max(1, stars),  # At least 1 star
            )
            contacts.append(contact)

        return contacts

    def _parse_email_sections(self, lines: List[str], contacts: List[Contact]):
        """
        Parse the ### email sections and attach subject/body to matching contacts.
        """
        # Build a lookup by email for quick matching
        contact_map = {}
        for c in contacts:
            if c.email not in contact_map:
                contact_map[c.email] = c

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Look for section header: ### N. Company — email@domain.com
            header_match = self.SECTION_HEADER_RE.match(line)
            if not header_match:
                i += 1
                continue

            section_idx = int(header_match.group(1))
            section_company = header_match.group(2).strip()
            section_email = header_match.group(3).strip().lower()

            # Parse the section content
            i += 1
            to_email = ""
            subject = ""
            body_lines = []
            parsing_body = False

            while i < len(lines):
                current = lines[i]
                stripped = current.strip()

                # End of section: --- separator or next ### header
                if stripped == '---' or (stripped.startswith('### ') and self.SECTION_HEADER_RE.match(stripped)):
                    break

                # Parse To:
                to_match = self.TO_RE.match(stripped)
                if to_match and not parsing_body:
                    to_email = to_match.group(1).strip().lower()
                    i += 1
                    continue

                # Parse Subject:
                subj_match = self.SUBJECT_RE.match(stripped)
                if subj_match and not parsing_body:
                    subject = subj_match.group(1).strip()
                    i += 1
                    continue

                # Everything after Subject is body
                if subject and not parsing_body:
                    # Skip empty lines between Subject and body start
                    if stripped == '':
                        i += 1
                        continue
                    parsing_body = True

                if parsing_body:
                    body_lines.append(current.rstrip())

                i += 1

            # Clean up body: remove trailing empty lines
            while body_lines and body_lines[-1].strip() == '':
                body_lines.pop()

            body = '\n'.join(body_lines)

            # Attach to matching contact
            lookup_email = to_email or section_email
            if lookup_email in contact_map:
                contact = contact_map[lookup_email]
                # Only set if not already set (keep first custom email, not duplicates)
                if not contact.has_custom_email:
                    contact.subject = subject
                    contact.body = body
                    contact.has_custom_email = True
                    logger.debug(f"Attached email for {lookup_email} ({contact.company})")
            else:
                # Contact exists in sections but not in table — add it
                self.errors.append(
                    f"Section #{section_idx} email '{lookup_email}' "
                    f"not found in table — skipped"
                )

            # Don't increment i here, the while loop already positioned us

        attached = sum(1 for c in contacts if c.has_custom_email)
        logger.info(f"Attached {attached}/{len(contacts)} custom email templates")

    def _deduplicate(self, contacts: List[Contact]) -> Tuple[List[Contact], int]:
        """Remove duplicate contacts by email, keeping the first (with custom email preferred)."""
        seen = {}
        unique = []
        dupes = 0

        for contact in contacts:
            if contact.email in seen:
                # Keep the one with a custom email template
                existing = seen[contact.email]
                if not existing.has_custom_email and contact.has_custom_email:
                    # Replace with the one that has a custom email
                    idx = unique.index(existing)
                    unique[idx] = contact
                    seen[contact.email] = contact
                dupes += 1
            else:
                seen[contact.email] = contact
                unique.append(contact)

        return unique, dupes

    def get_contacts_by_relevance(self, min_stars: int = 1) -> List[Contact]:
        """Get contacts filtered by minimum relevance."""
        result = self.parse()
        return [c for c in result.contacts if c.relevance >= min_stars]


# ═══════════════════════════════════════════════════════════
#  Utility
# ═══════════════════════════════════════════════════════════

def print_contacts_summary(contacts: List[Contact]):
    """Pretty print a summary of parsed contacts."""
    print(f"\n{'='*70}")
    print(f"  📊 CONTACTS SUMMARY — {len(contacts)} contacts")
    print(f"{'='*70}")

    for c in contacts:
        stars = '⭐' * c.relevance
        has_email = '✅' if c.has_custom_email else '❌'
        city = c.city or '—'
        print(
            f"  {c.index:>3}. {has_email} {stars:<9} "
            f"{c.company:<25} {c.email:<40} {city}"
        )

    with_email = sum(1 for c in contacts if c.has_custom_email)
    print(f"\n  ✅ With custom email: {with_email}")
    print(f"  ❌ Without custom email: {len(contacts) - with_email}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    """Quick test of the parser."""
    logging.basicConfig(level=logging.INFO)

    parser = EmailProspectionParser(
        r"c:\laragon\www\filter contact\emails_prospection.md"
    )
    result = parser.parse()
    print_contacts_summary(result.contacts)

    if result.errors:
        print(f"\n⚠️  Parsing Errors ({len(result.errors)}):")
        for err in result.errors[:10]:
            print(f"  - {err}")
