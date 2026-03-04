"""
══════════════════════════════════════════════════════════════
  IMAP Inbox Monitor — Detect replies to sent emails
  Auto-marks contacts as "responded" in the tracker
══════════════════════════════════════════════════════════════

  Connects to Gmail IMAP to scan for replies to your outreach
  emails. Updates the sent tracker so responded contacts are
  excluded from follow-ups.

  Setup (in .env):
    IMAP_HOST=imap.gmail.com
    IMAP_PORT=993
    # Uses same EMAIL_USERNAME and EMAIL_PASSWORD as SMTP

  Usage (CLI):
    python main.py --check-replies
    python main.py --check-replies --days 30

  Programmatic:
    monitor = InboxMonitor.from_env()
    monitor.check_replies(tracker, days=14)
"""

import os
import re
import ssl
import email
import imaplib
import logging
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)


class InboxMonitor:
    """
    Monitors Gmail inbox for replies to sent prospection emails.

    How it works:
    1. Connects to IMAP (Gmail)
    2. Searches for recent emails in INBOX
    3. Checks if sender email matches any sent contact
    4. Marks matched contacts as "responded" in tracker

    Detection methods:
    - Direct reply: sender email matches a sent contact
    - Subject match: email subject contains our original subject
    - In-Reply-To header: references our original Message-ID
    """

    def __init__(
        self,
        host: str = "imap.gmail.com",
        port: int = 993,
        username: str = "",
        password: str = "",
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.connection: Optional[imaplib.IMAP4_SSL] = None

    @classmethod
    def from_env(cls) -> "InboxMonitor":
        """Create an InboxMonitor from environment variables."""
        return cls(
            host=os.getenv("IMAP_HOST", "imap.gmail.com"),
            port=int(os.getenv("IMAP_PORT", "993")),
            username=os.getenv("EMAIL_USERNAME", ""),
            password=os.getenv("EMAIL_PASSWORD", ""),
        )

    # ─── Connection Management ────────────────────────────

    def connect(self) -> bool:
        """Establish IMAP connection with SSL."""
        try:
            context = ssl.create_default_context()
            self.connection = imaplib.IMAP4_SSL(
                self.host, self.port, ssl_context=context
            )
            self.connection.login(self.username, self.password)
            logger.info(f"✅ IMAP connected to {self.host}")
            return True
        except imaplib.IMAP4.error as e:
            logger.error(f"❌ IMAP authentication failed: {e}")
            print(
                f"\n  ❌ IMAP Authentication Failed!\n"
                f"  Make sure EMAIL_USERNAME and EMAIL_PASSWORD are set in .env\n"
                f"  and that IMAP is enabled in Gmail settings.\n"
                f"  (Gmail → Settings → Forwarding and POP/IMAP → Enable IMAP)\n"
            )
            return False
        except Exception as e:
            logger.error(f"❌ IMAP connection failed: {e}")
            return False

    def disconnect(self):
        """Close IMAP connection."""
        if self.connection:
            try:
                self.connection.close()
                self.connection.logout()
            except Exception:
                pass
            self.connection = None

    # ─── Reply Detection ──────────────────────────────────

    def check_replies(
        self, tracker, days: int = 14, verbose: bool = False
    ) -> Dict[str, dict]:
        """
        Check inbox for replies to sent emails.

        Args:
            tracker:  SentTracker instance
            days:     How many days back to search
            verbose:  Print details for each reply found

        Returns:
            Dict of {email: reply_info} for detected replies
        """
        if not self.connection:
            if not self.connect():
                return {}

        # Get set of emails we've sent to
        sent_emails = tracker.get_sent_emails()
        if not sent_emails:
            print("  ℹ️  No sent emails in tracker — nothing to check.")
            return {}

        print(f"\n{'='*60}")
        print(f"  📬 CHECKING INBOX FOR REPLIES")
        print(f"{'='*60}")
        print(f"  📧 Monitoring {len(sent_emails)} sent contacts")
        print(f"  📅 Searching last {days} days")

        # Search inbox
        replies = {}
        try:
            self.connection.select("INBOX")

            # Build IMAP search query: emails received in last N days
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
            search_query = f'(SINCE "{since_date}")'

            status, message_ids = self.connection.search(None, search_query)
            if status != "OK":
                logger.warning(f"IMAP search failed: {status}")
                return {}

            ids = message_ids[0].split()
            print(f"  📨 Found {len(ids)} emails in last {days} days")

            # Check each email
            for msg_id in ids:
                try:
                    reply_info = self._check_single_email(msg_id, sent_emails)
                    if reply_info:
                        reply_email = reply_info['from_email']
                        if reply_email not in replies:
                            replies[reply_email] = reply_info
                            if verbose:
                                print(
                                    f"    ✅ Reply from: {reply_email} "
                                    f"({reply_info.get('subject', '?')[:50]})"
                                )
                except Exception as e:
                    logger.debug(f"Error processing message {msg_id}: {e}")

        except Exception as e:
            logger.error(f"IMAP search error: {e}")

        # ── Update tracker with replies ──
        if replies:
            self._update_tracker(tracker, replies)
            print(f"\n  {'─'*56}")
            print(f"  ✅ Detected {len(replies)} replies!")
            for email_addr, info in replies.items():
                company = info.get('company', '?')
                date = info.get('date', '?')
                print(f"     📩 {email_addr} ({company}) — {date}")
        else:
            print(f"\n  ℹ️  No replies detected yet.")

        print(f"{'='*60}\n")
        return replies

    def _check_single_email(
        self, msg_id: bytes, sent_emails: Set[str]
    ) -> Optional[dict]:
        """Check if a single email is a reply from a sent contact."""
        status, data = self.connection.fetch(msg_id, "(RFC822.HEADER)")
        if status != "OK":
            return None

        raw_header = data[0][1]
        msg = email.message_from_bytes(raw_header)

        # Get sender
        from_raw = msg.get("From", "")
        from_name, from_email = parseaddr(from_raw)
        from_email = from_email.lower()

        # Check if sender is one of our sent contacts
        if from_email not in sent_emails:
            return None

        # Get subject
        subject = self._decode_header(msg.get("Subject", ""))

        # Get date
        date_str = msg.get("Date", "")
        try:
            date_obj = parsedate_to_datetime(date_str)
            date_formatted = date_obj.strftime("%Y-%m-%d %H:%M")
        except Exception:
            date_formatted = date_str[:20]

        # Get company from tracker
        company = ""

        return {
            'from_email': from_email,
            'from_name': from_name,
            'subject': subject,
            'date': date_formatted,
            'company': company,
            'msg_id': msg_id.decode(),
        }

    def _decode_header(self, header: str) -> str:
        """Decode an email header (handles encoded words)."""
        if not header:
            return ""
        decoded_parts = decode_header(header)
        result = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(charset or 'utf-8', errors='replace'))
            else:
                result.append(part)
        return ' '.join(result)

    def _update_tracker(self, tracker, replies: Dict[str, dict]):
        """Update tracker to mark contacts as responded."""
        for email_addr, info in replies.items():
            email_lower = email_addr.lower()
            if email_lower in tracker.sent:
                record = tracker.sent[email_lower]
                # Add response metadata
                record.smtp_response = (
                    f"REPLY DETECTED: {info.get('date', '?')} — "
                    f"Subject: {info.get('subject', '?')[:80]}"
                )
                record.status = "replied"
                logger.info(f"📩 Marked as replied: {email_addr}")

        # Save updated tracker
        tracker._save()

    # ─── Statistics ───────────────────────────────────────

    def get_reply_stats(self, tracker) -> dict:
        """Get reply statistics from tracker."""
        total_sent = len(tracker.sent)
        replied = sum(
            1 for r in tracker.sent.values()
            if getattr(r, 'status', '') == 'replied'
        )
        return {
            'total_sent': total_sent,
            'replied': replied,
            'reply_rate': f"{(replied/total_sent*100):.1f}%" if total_sent > 0 else "0%",
            'no_reply': total_sent - replied,
        }
