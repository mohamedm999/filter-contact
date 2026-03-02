"""
══════════════════════════════════════════════════════════════
  Email Campaign Configuration
  Anti-Spam · Rate-Limited · Professional Email Sender
══════════════════════════════════════════════════════════════

  HOW TO SET UP GMAIL APP PASSWORD:
  1. Go to https://myaccount.google.com/security
  2. Enable 2-Factor Authentication (required)
  3. Go to https://myaccount.google.com/apppasswords
  4. Create a new App Password for "Mail"
  5. Copy the 16-character password below (no spaces)

  ⚠️  NEVER use your real Gmail password here!
  ⚠️  NEVER commit this file to Git with real credentials!
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Load .env file from project root (one level up from email_campaign/)
from dotenv import load_dotenv
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


# ═══════════════════════════════════════════════════════════
#  SMTP Configuration
# ═══════════════════════════════════════════════════════════

@dataclass
class SMTPConfig:
    """SMTP server settings. Defaults to Gmail."""
    host: str = "smtp.gmail.com"
    port: int = 587                          # TLS port (recommended)
    use_tls: bool = True                     # Always use TLS
    username: str = ""                       # Loaded from .env → EMAIL_USERNAME
    password: str = ""                       # Loaded from .env → EMAIL_PASSWORD

    def __post_init__(self):
        # Always load from .env / environment variables
        self.username = os.getenv("EMAIL_USERNAME", self.username)
        self.password = os.getenv("EMAIL_PASSWORD", self.password)


# ═══════════════════════════════════════════════════════════
#  Sender Profile
# ═══════════════════════════════════════════════════════════

@dataclass
class SenderProfile:
    """Your personal info used in email headers."""
    name: str = ""                        # Loaded from .env → SENDER_NAME
    email: str = ""                       # Loaded from .env → SENDER_EMAIL
    phone: str = ""                       # Loaded from .env → SENDER_PHONE
    reply_to: str = ""                    # If empty, uses email

    def __post_init__(self):
        self.name = os.getenv("SENDER_NAME", self.name)
        self.email = os.getenv("SENDER_EMAIL", self.email)
        self.phone = os.getenv("SENDER_PHONE", self.phone)
        if not self.reply_to:
            self.reply_to = self.email


# ═══════════════════════════════════════════════════════════
#  Anti-Spam & Rate Limiting
# ═══════════════════════════════════════════════════════════

@dataclass
class RateLimitConfig:
    """
    Gmail limits (free account):
    - 500 emails/day
    - ~20 emails/hour recommended for cold outreach
    - Too fast = flagged as spam or account locked

    These defaults are SAFE for cold email prospection.
    """

    # ── Per-email delays ──
    min_delay_seconds: int = 45              # Minimum wait between emails
    max_delay_seconds: int = 120             # Maximum wait (randomized)

    # ── Batch controls ──
    batch_size: int = 10                     # Emails per batch
    batch_pause_minutes: int = 15            # Pause between batches

    # ── Daily limits ──
    max_emails_per_day: int = 40             # Stay well under Gmail's 500 limit
    max_emails_per_hour: int = 15            # ~1 email every 4 minutes

    # ── Session controls ──
    max_consecutive_errors: int = 3          # Stop after N consecutive failures
    max_retries_per_email: int = 2           # Retry failed emails
    retry_delay_seconds: int = 60            # Wait before retrying


# ═══════════════════════════════════════════════════════════
#  Email Content Settings
# ═══════════════════════════════════════════════════════════

@dataclass
class EmailContentConfig:
    """Settings for email formatting and anti-spam tricks."""

    # ── MIME settings ──
    send_as_html: bool = False               # Plain text = less spammy
    charset: str = "utf-8"

    # ── Anti-spam headers ──
    add_message_id: bool = True              # Unique Message-ID per email
    add_date_header: bool = True             # Proper Date header
    add_list_unsubscribe: bool = True        # Unsubscribe header (reduces spam score)

    # ── Content variations ──
    # Small random variations make emails look less like mass-mail
    add_random_greeting_variation: bool = True
    add_timestamp_signature: bool = False     # Adds timestamp to make each email unique


# ═══════════════════════════════════════════════════════════
#  File Paths
# ═══════════════════════════════════════════════════════════

@dataclass
class PathConfig:
    """File paths for data and logs."""
    # Source file with contacts and email templates
    contacts_file: str = r"c:\laragon\www\filter contact\emails_prospection.md"

    # Tracking & logs directory
    log_dir: str = r"c:\laragon\www\filter contact\email_campaign\logs"

    # Sent tracking file (JSON) - prevents re-sending
    sent_tracker_file: str = r"c:\laragon\www\filter contact\email_campaign\logs\sent_tracker.json"

    # Detailed log file
    log_file: str = r"c:\laragon\www\filter contact\email_campaign\logs\campaign.log"

    # Failed emails log
    failed_file: str = r"c:\laragon\www\filter contact\email_campaign\logs\failed_emails.json"


# ═══════════════════════════════════════════════════════════
#  Filter Settings
# ═══════════════════════════════════════════════════════════

@dataclass
class FilterConfig:
    """Which contacts to include/exclude."""

    # Only send to contacts with this minimum relevance (star count)
    min_relevance_stars: int = 1             # 1=all, 2=pertinent+, 3=very pertinent only

    # Skip generic email providers (personal emails less likely to respond)
    skip_personal_emails: bool = False

    # Skip these specific emails
    skip_emails: list = field(default_factory=lambda: [
        os.getenv("SENDER_EMAIL", ""),       # Your own email (from .env)
    ])

    # Only send to these domains (empty = all domains)
    only_domains: list = field(default_factory=list)


# ═══════════════════════════════════════════════════════════
#  Master Config
# ═══════════════════════════════════════════════════════════

@dataclass
class CampaignConfig:
    """Master configuration combining all settings."""
    smtp: SMTPConfig = field(default_factory=SMTPConfig)
    sender: SenderProfile = field(default_factory=SenderProfile)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    email_content: EmailContentConfig = field(default_factory=EmailContentConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)

    # ── Dry run mode ──
    dry_run: bool = True   # ⚠️ SET TO False WHEN READY TO SEND FOR REAL

    # ── Verbose output ──
    verbose: bool = True


def load_config() -> CampaignConfig:
    """
    Load configuration from .env file (auto-loaded at module import).

    All secrets are read from:  .env  (project root)
    Copy .env.example → .env and fill in your values.
    """
    config = CampaignConfig()

    # Campaign-level overrides from .env
    if os.getenv("DRY_RUN", "").lower() in ("false", "0", "no"):
        config.dry_run = False
    if os.getenv("MIN_RELEVANCE_STARS"):
        config.filters.min_relevance_stars = int(os.getenv("MIN_RELEVANCE_STARS"))
    if os.getenv("MAX_EMAILS_PER_DAY"):
        config.rate_limit.max_emails_per_day = int(os.getenv("MAX_EMAILS_PER_DAY"))
    if os.getenv("MAX_EMAILS_PER_HOUR"):
        config.rate_limit.max_emails_per_hour = int(os.getenv("MAX_EMAILS_PER_HOUR"))
    if os.getenv("BATCH_SIZE"):
        config.rate_limit.batch_size = int(os.getenv("BATCH_SIZE"))
    if os.getenv("BATCH_PAUSE_MINUTES"):
        config.rate_limit.batch_pause_minutes = int(os.getenv("BATCH_PAUSE_MINUTES"))
    if os.getenv("CONTACTS_FILE"):
        config.paths.contacts_file = os.getenv("CONTACTS_FILE")
    if os.getenv("LOG_DIR"):
        config.paths.log_dir = os.getenv("LOG_DIR")

    return config
