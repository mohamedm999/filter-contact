"""
══════════════════════════════════════════════════════════════
  Sent Email Tracker
  Persistent tracking to prevent re-sending & enable resume
══════════════════════════════════════════════════════════════
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class EmailRecord:
    """Record of a sent/attempted email."""
    email: str
    company: str
    subject: str
    status: str                       # "sent", "failed", "skipped"
    timestamp: str = ""
    attempt: int = 1
    error_message: str = ""
    smtp_response: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class SentTracker:
    """
    Tracks which emails have been sent to prevent duplicates.
    Persists to JSON file for crash recovery / resume capability.
    """

    def __init__(self, tracker_file: str, failed_file: str):
        self.tracker_path = Path(tracker_file)
        self.failed_path = Path(failed_file)

        # Ensure directories exist
        self.tracker_path.parent.mkdir(parents=True, exist_ok=True)
        self.failed_path.parent.mkdir(parents=True, exist_ok=True)

        # In-memory state
        self.sent: Dict[str, EmailRecord] = {}       # email -> record
        self.failed: Dict[str, EmailRecord] = {}     # email -> record
        self.skipped: Dict[str, EmailRecord] = {}    # email -> record

        # Session stats
        self.session_sent: int = 0
        self.session_failed: int = 0
        self.session_skipped: int = 0
        self.session_start: datetime = datetime.now()

        # Load existing data
        self._load()

    def _load(self):
        """Load existing tracker data from disk."""
        if self.tracker_path.exists():
            try:
                data = json.loads(self.tracker_path.read_text(encoding='utf-8'))
                for email, record_data in data.get('sent', {}).items():
                    self.sent[email] = EmailRecord(**record_data)
                for email, record_data in data.get('failed', {}).items():
                    self.failed[email] = EmailRecord(**record_data)
                for email, record_data in data.get('skipped', {}).items():
                    self.skipped[email] = EmailRecord(**record_data)

                logger.info(
                    f"Loaded tracker: {len(self.sent)} sent, "
                    f"{len(self.failed)} failed, {len(self.skipped)} skipped"
                )
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.warning(f"Could not load tracker file: {e}")

    def _save(self):
        """Save current state to disk."""
        data = {
            'last_updated': datetime.now().isoformat(),
            'total_sent': len(self.sent),
            'total_failed': len(self.failed),
            'total_skipped': len(self.skipped),
            'sent': {email: asdict(record) for email, record in self.sent.items()},
            'failed': {email: asdict(record) for email, record in self.failed.items()},
            'skipped': {email: asdict(record) for email, record in self.skipped.items()},
        }
        self.tracker_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

    def is_already_sent(self, email: str) -> bool:
        """Check if an email was already successfully sent."""
        return email.lower() in self.sent

    def was_failed(self, email: str) -> bool:
        """Check if an email previously failed."""
        return email.lower() in self.failed

    def record_sent(self, email: str, company: str, subject: str, smtp_response: str = ""):
        """Record a successfully sent email."""
        email_lower = email.lower()
        record = EmailRecord(
            email=email_lower,
            company=company,
            subject=subject,
            status="sent",
            smtp_response=smtp_response,
        )
        self.sent[email_lower] = record

        # Remove from failed if previously failed
        self.failed.pop(email_lower, None)

        self.session_sent += 1
        self._save()
        logger.info(f"✅ Recorded SENT: {email} ({company})")

    def record_failed(self, email: str, company: str, subject: str,
                      error_message: str, attempt: int = 1):
        """Record a failed email attempt."""
        email_lower = email.lower()
        record = EmailRecord(
            email=email_lower,
            company=company,
            subject=subject,
            status="failed",
            error_message=error_message,
            attempt=attempt,
        )
        self.failed[email_lower] = record
        self.session_failed += 1
        self._save()
        logger.warning(f"❌ Recorded FAILED: {email} ({company}): {error_message}")

    def record_skipped(self, email: str, company: str, reason: str):
        """Record a skipped email."""
        email_lower = email.lower()
        record = EmailRecord(
            email=email_lower,
            company=company,
            subject="",
            status="skipped",
            error_message=reason,
        )
        self.skipped[email_lower] = record
        self.session_skipped += 1
        self._save()
        logger.info(f"⏭️  Recorded SKIPPED: {email} ({company}): {reason}")

    def get_sent_emails(self) -> Set[str]:
        """Get set of all successfully sent email addresses."""
        return set(self.sent.keys())

    def get_failed_emails(self) -> List[EmailRecord]:
        """Get list of all failed email records."""
        return list(self.failed.values())

    def get_session_stats(self) -> dict:
        """Get statistics for the current session."""
        elapsed = datetime.now() - self.session_start
        return {
            'session_sent': self.session_sent,
            'session_failed': self.session_failed,
            'session_skipped': self.session_skipped,
            'session_total': self.session_sent + self.session_failed + self.session_skipped,
            'elapsed_time': str(elapsed).split('.')[0],
            'total_sent_all_time': len(self.sent),
            'total_failed_all_time': len(self.failed),
        }

    def print_session_report(self):
        """Print a formatted session report."""
        stats = self.get_session_stats()
        print(f"\n{'='*60}")
        print(f"  📊 SESSION REPORT")
        print(f"{'='*60}")
        print(f"  ⏱️  Duration:        {stats['elapsed_time']}")
        print(f"  ✅ Sent:            {stats['session_sent']}")
        print(f"  ❌ Failed:          {stats['session_failed']}")
        print(f"  ⏭️  Skipped:         {stats['session_skipped']}")
        print(f"  📧 Session total:   {stats['session_total']}")
        print(f"  ─────────────────────────────────────")
        print(f"  📈 All-time sent:   {stats['total_sent_all_time']}")
        print(f"  📉 All-time failed: {stats['total_failed_all_time']}")
        print(f"{'='*60}\n")
