"""
══════════════════════════════════════════════════════════════
  Email Campaign CLI — Main Entry Point
  Professional Email Prospection Tool
══════════════════════════════════════════════════════════════

  Usage:
    python main.py                     # Dry run (default, safe)
    python main.py --send              # Actually send emails
    python main.py --status            # Show campaign status
    python main.py --retry-failed      # Retry previously failed emails
    python main.py --preview 5         # Preview first 5 emails
    python main.py --test              # Send a test email to yourself
    python main.py --min-stars 3       # Only ⭐⭐⭐ contacts
    python main.py --limit 10          # Send max 10 emails this session
    python main.py --send --min-stars 2 --limit 20

  Environment Variables (recommended for security):
    set EMAIL_USERNAME=your.email@gmail.com
    set EMAIL_PASSWORD=your-16-char-app-password
"""

import sys
import os
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_config, CampaignConfig
from parse_contacts import EmailProspectionParser, print_contacts_summary, Contact
from email_sender import EmailSender, EmailValidator
from tracker import SentTracker


# ═══════════════════════════════════════════════════════════
#  Logging Setup
# ═══════════════════════════════════════════════════════════

def setup_logging(config: CampaignConfig):
    """Configure logging to file and console."""
    log_dir = Path(config.paths.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # File handler — detailed logs
    file_handler = logging.FileHandler(
        config.paths.log_file,
        encoding='utf-8',
        mode='a'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
    ))

    # Console handler — info only
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter('  %(levelname)s: %(message)s'))

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.info(f"{'='*60}")
    logging.info(f"Session started at {datetime.now().isoformat()}")
    logging.info(f"{'='*60}")


# ═══════════════════════════════════════════════════════════
#  CLI Commands
# ═══════════════════════════════════════════════════════════

def cmd_preview(config: CampaignConfig, limit: int = 5, min_stars: int = 1):
    """Preview emails that would be sent."""
    parser = EmailProspectionParser(config.paths.contacts_file)
    result = parser.parse()

    contacts = [c for c in result.contacts if c.relevance >= min_stars and c.has_custom_email]

    print(f"\n{'='*70}")
    print(f"  👁️  EMAIL PREVIEW — Showing {min(limit, len(contacts))} of {len(contacts)}")
    print(f"{'='*70}")

    for i, contact in enumerate(contacts[:limit]):
        stars = '⭐' * contact.relevance
        print(f"\n  {'─'*66}")
        print(f"  📧 #{contact.index} | {contact.company} | {stars}")
        print(f"  To:      {contact.email}")
        print(f"  Subject: {contact.subject}")
        print(f"  {'─'*66}")

        # Show first 10 lines of body
        body_lines = contact.body.split('\n')
        preview_lines = body_lines[:10]
        for line in preview_lines:
            print(f"  │ {line}")
        if len(body_lines) > 10:
            print(f"  │ ... ({len(body_lines) - 10} more lines)")

    print(f"\n{'='*70}\n")


def cmd_status(config: CampaignConfig):
    """Show campaign status and tracker stats."""
    tracker = SentTracker(config.paths.sent_tracker_file, config.paths.failed_file)
    parser = EmailProspectionParser(config.paths.contacts_file)
    result = parser.parse()

    total = len(result.contacts)
    with_email = sum(1 for c in result.contacts if c.has_custom_email)
    sent_emails = tracker.get_sent_emails()
    failed = tracker.get_failed_emails()

    remaining = [
        c for c in result.contacts
        if c.has_custom_email and c.email.lower() not in sent_emails
    ]

    print(f"\n{'='*60}")
    print(f"  📊 CAMPAIGN STATUS")
    print(f"{'='*60}")
    print(f"  📋 Total contacts in file:    {total}")
    print(f"  ✉️  With email template:       {with_email}")
    print(f"  ❌ Without email template:     {total - with_email}")
    print(f"  🔄 Duplicates removed:         {result.duplicates_removed}")
    print(f"  {'─'*56}")
    print(f"  ✅ Already sent:               {len(sent_emails)}")
    print(f"  ❌ Failed:                     {len(failed)}")
    print(f"  📤 Remaining to send:          {len(remaining)}")
    print(f"{'='*60}")

    if failed:
        print(f"\n  ❌ Failed Emails:")
        for f_record in failed[:10]:
            print(f"     • {f_record.email} ({f_record.company}): {f_record.error_message}")
        if len(failed) > 10:
            print(f"     ... and {len(failed) - 10} more")

    print()


def cmd_test(config: CampaignConfig):
    """Send a test email to yourself."""
    print(f"\n{'='*60}")
    print(f"  🧪 SENDING TEST EMAIL TO YOURSELF")
    print(f"{'='*60}")

    if not config.smtp.username or not config.smtp.password:
        print(
            "\n  ❌ SMTP credentials not set!\n"
            "  Run:\n"
            '    set EMAIL_USERNAME=your.email@gmail.com\n'
            '    set EMAIL_PASSWORD=your-app-password\n'
        )
        return

    test_contact = Contact(
        index=0,
        company="TEST — Self",
        email=config.sender.email,
        position="Test",
        city="Test",
        relevance=3,
        subject=f"[TEST] Email Campaign Test — {datetime.now().strftime('%H:%M:%S')}",
        body=(
            f"This is a test email from your Email Campaign tool.\n\n"
            f"If you receive this, your SMTP configuration is working correctly!\n\n"
            f"Timestamp: {datetime.now().isoformat()}\n"
            f"SMTP Host: {config.smtp.host}\n"
            f"Username: {config.smtp.username}\n\n"
            f"— Email Campaign Tool"
        ),
        has_custom_email=True,
    )

    # Force live mode for test
    config.dry_run = False

    tracker = SentTracker(config.paths.sent_tracker_file, config.paths.failed_file)
    sender = EmailSender(config, tracker)

    if sender.connect():
        success, message = sender.send_one(test_contact)
        sender.disconnect()
        if success:
            print(f"\n  ✅ Test email sent to {config.sender.email}")
            print(f"  Check your inbox (and spam folder)!\n")
        else:
            print(f"\n  ❌ Failed: {message}\n")
    else:
        print("\n  ❌ Could not connect to SMTP server.\n")


def cmd_send(config: CampaignConfig, min_stars: int = 1, limit: int = 0,
             retry_failed: bool = False):
    """Send the email campaign."""
    parser = EmailProspectionParser(config.paths.contacts_file)
    result = parser.parse()

    # Filter by relevance
    contacts = [c for c in result.contacts if c.relevance >= min_stars]

    if retry_failed:
        # Only retry previously failed emails
        tracker_temp = SentTracker(config.paths.sent_tracker_file, config.paths.failed_file)
        failed_emails = {r.email for r in tracker_temp.get_failed_emails()}
        contacts = [c for c in contacts if c.email.lower() in failed_emails]
        print(f"\n  🔄 Retrying {len(contacts)} previously failed emails...")

    # Apply limit
    if limit > 0:
        contacts = contacts[:limit]

    # Validate contacts
    valid_contacts = []
    for contact in contacts:
        valid, msg = EmailValidator.validate_contact(contact)
        if valid:
            valid_contacts.append(contact)
        else:
            logging.debug(f"Validation failed for {contact.email}: {msg}")

    print(f"\n  📋 Contacts after filtering: {len(valid_contacts)}")
    print(f"  ⭐ Minimum relevance: {min_stars} star(s)")

    if limit > 0:
        print(f"  🔢 Session limit: {limit} emails")

    # Show summary
    print_contacts_summary(valid_contacts[:20])
    if len(valid_contacts) > 20:
        print(f"  ... and {len(valid_contacts) - 20} more contacts\n")

    # Initialize tracker and sender
    tracker = SentTracker(config.paths.sent_tracker_file, config.paths.failed_file)
    sender = EmailSender(config, tracker)
    sender.auto_confirm = getattr(config, 'auto_confirm', False)

    # Run campaign
    stats = sender.send_campaign(valid_contacts)

    # Print report
    tracker.print_session_report()

    return stats


# ═══════════════════════════════════════════════════════════
#  Main Entry Point
# ═══════════════════════════════════════════════════════════

def main():
    """CLI entry point."""
    arg_parser = argparse.ArgumentParser(
        description='📧 Professional Email Campaign Tool — Anti-Spam, Rate-Limited',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                         Dry run (safe test)
  python main.py --preview 5             Preview first 5 emails
  python main.py --test                  Send test email to yourself
  python main.py --status                Check campaign progress
  python main.py --send --min-stars 3    Send only to ⭐⭐⭐ contacts
  python main.py --send --limit 10       Send max 10 emails
  python main.py --retry-failed          Retry failed emails

Before sending, set credentials:
  set EMAIL_USERNAME=your.email@gmail.com
  set EMAIL_PASSWORD=your-16-char-app-password
        """
    )

    arg_parser.add_argument(
        '--send', action='store_true',
        help='Actually send emails (default is dry-run)'
    )
    arg_parser.add_argument(
        '--preview', type=int, nargs='?', const=5, default=0,
        help='Preview N emails (default: 5)'
    )
    arg_parser.add_argument(
        '--test', action='store_true',
        help='Send a test email to yourself'
    )
    arg_parser.add_argument(
        '--status', action='store_true',
        help='Show campaign status'
    )
    arg_parser.add_argument(
        '--retry-failed', action='store_true',
        help='Retry previously failed emails'
    )
    arg_parser.add_argument(
        '--min-stars', type=int, default=1, choices=[1, 2, 3],
        help='Minimum relevance stars (1-3, default: 1)'
    )
    arg_parser.add_argument(
        '--limit', type=int, default=0,
        help='Maximum emails to send this session (0 = no limit)'
    )
    arg_parser.add_argument(
        '--verbose', action='store_true',
        help='Show verbose output'
    )
    arg_parser.add_argument(
        '--yes', '-y', action='store_true',
        help='Skip confirmation prompt (auto-confirm)'
    )

    args = arg_parser.parse_args()

    # ── Banner ──
    print("""
    ╔══════════════════════════════════════════════════════╗
    ║  📧  Email Campaign Tool — Professional Outreach    ║
    ║  Anti-Spam · Rate-Limited · Error-Resilient         ║
    ╚══════════════════════════════════════════════════════╝
    """)

    # ── Load config ──
    config = load_config()
    config.verbose = args.verbose

    # ── Setup logging ──
    setup_logging(config)

    # ── Route to command ──

    if args.status:
        cmd_status(config)
        return

    if args.test:
        cmd_test(config)
        return

    if args.preview:
        cmd_preview(config, limit=args.preview, min_stars=args.min_stars)
        return

    # Default: dry run or send
    if args.send:
        config.dry_run = False
        print("  ⚠️  LIVE MODE — Emails will be sent for real!\n")
    else:
        config.dry_run = True
        print("  🔵 DRY RUN MODE — No emails will be sent (use --send to send)\n")

    # Check credentials for live mode
    if not config.dry_run:
        if not config.smtp.username or not config.smtp.password:
            print(
                "  ❌ SMTP credentials not configured!\n\n"
                "  Option 1 — Environment variables (recommended):\n"
                '    set EMAIL_USERNAME=your.email@gmail.com\n'
                '    set EMAIL_PASSWORD=your-16-char-app-password\n\n'
                "  Option 2 — Edit email_campaign/config.py directly\n\n"
                "  Need an App Password? Go to:\n"
                "    https://myaccount.google.com/apppasswords\n"
            )
            sys.exit(1)

    # Pass auto-confirm flag
    if args.yes:
        config.auto_confirm = True

    cmd_send(
        config,
        min_stars=args.min_stars,
        limit=args.limit,
        retry_failed=args.retry_failed,
    )


if __name__ == '__main__':
    main()
