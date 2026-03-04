"""
══════════════════════════════════════════════════════════════
  Professional Email Sender Engine
  HTML + Signature · Anti-Spam · Rate-Limited · Logged
══════════════════════════════════════════════════════════════

  Anti-Spam Techniques Used:
  ─────────────────────────
  1. TLS encryption (required by Gmail)
  2. Proper MIME structure (multipart/alternative: plain + HTML)
  3. Correct email headers (From, To, Date, Message-ID)
  4. List-Unsubscribe header (reduces spam score)
  5. Randomized delays between emails (human-like)
  6. Batch sending with pauses
  7. Daily/hourly limits
  8. Unique Message-ID per email
  9. Proper Reply-To header
  10. Professional HTML with plain-text fallback
  11. No URL shorteners or tracking pixels
  12. Single SMTP connection reuse (fewer connections = less suspicious)
"""

import smtplib
import ssl
import time
import random
import logging
import socket
import uuid
import html as html_module
import mimetypes
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate, formataddr, make_msgid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from config import CampaignConfig, RateLimitConfig, SignatureConfig
from parse_contacts import Contact
from tracker import SentTracker
from language_detector import LanguageDetector

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Controls sending speed to avoid hitting provider limits.

    Gmail limits:
    - 500 recipients/day (free account)
    - 2000 recipients/day (Google Workspace)
    - No official per-hour limit, but ~20/hour is safe
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.sent_this_hour: int = 0
        self.sent_today: int = 0
        self.hour_start: datetime = datetime.now()
        self.day_start: datetime = datetime.now()
        self.batch_count: int = 0

    def wait_if_needed(self):
        """Block until we're allowed to send the next email."""
        now = datetime.now()

        # Reset hourly counter
        if (now - self.hour_start) >= timedelta(hours=1):
            self.sent_this_hour = 0
            self.hour_start = now
            logger.info("⏰ Hourly counter reset")

        # Reset daily counter
        if (now - self.day_start) >= timedelta(days=1):
            self.sent_today = 0
            self.day_start = now
            logger.info("📅 Daily counter reset")

        # Check daily limit
        if self.sent_today >= self.config.max_emails_per_day:
            wait_until = self.day_start + timedelta(days=1)
            wait_seconds = (wait_until - now).total_seconds()
            logger.warning(
                f"🛑 Daily limit reached ({self.config.max_emails_per_day}). "
                f"Waiting {wait_seconds/3600:.1f} hours..."
            )
            print(
                f"\n🛑 Daily limit reached! Waiting until {wait_until.strftime('%H:%M')}..."
                f"\n   Press Ctrl+C to stop and resume later.\n"
            )
            time.sleep(wait_seconds)
            self.sent_today = 0
            self.day_start = datetime.now()

        # Check hourly limit
        if self.sent_this_hour >= self.config.max_emails_per_hour:
            wait_until = self.hour_start + timedelta(hours=1)
            wait_seconds = (wait_until - now).total_seconds()
            if wait_seconds > 0:
                logger.info(
                    f"⏳ Hourly limit reached ({self.config.max_emails_per_hour}). "
                    f"Waiting {wait_seconds/60:.1f} minutes..."
                )
                print(f"  ⏳ Hourly limit reached. Pausing {wait_seconds/60:.1f} min...")
                time.sleep(wait_seconds)
            self.sent_this_hour = 0
            self.hour_start = datetime.now()

    def add_random_delay(self):
        """Add a human-like random delay between emails."""
        delay = random.uniform(
            self.config.min_delay_seconds,
            self.config.max_delay_seconds
        )
        logger.debug(f"Waiting {delay:.1f}s before next email...")
        time.sleep(delay)

    def check_batch_pause(self):
        """Pause between batches for safety."""
        self.batch_count += 1
        if self.batch_count >= self.config.batch_size:
            pause_seconds = self.config.batch_pause_minutes * 60
            logger.info(
                f"📦 Batch of {self.config.batch_size} complete. "
                f"Pausing {self.config.batch_pause_minutes} minutes..."
            )
            print(
                f"\n  📦 Batch complete ({self.config.batch_size} emails). "
                f"Pausing {self.config.batch_pause_minutes} min for safety...\n"
            )
            time.sleep(pause_seconds)
            self.batch_count = 0

    def record_sent(self):
        """Record that an email was sent."""
        self.sent_this_hour += 1
        self.sent_today += 1


class EmailSender:
    """
    Production-grade email sender with anti-spam protection.

    Features:
    - SMTP connection pooling (reuses connection)
    - TLS encryption
    - Proper email headers
    - Rate limiting & random delays
    - Retry logic with exponential backoff
    - Sent tracking & crash recovery
    - Dry-run mode for testing
    """

    # Generic email domains to optionally skip
    GENERIC_DOMAINS = {
        'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
        'live.com', 'aol.com', 'icloud.com', 'protonmail.com',
        'yandex.com', 'zoho.com', 'gmx.com', 'mail.com'
    }

    def __init__(self, config: CampaignConfig, tracker: SentTracker):
        self.config = config
        self.tracker = tracker
        self.rate_limiter = RateLimiter(config.rate_limit)
        self.smtp_connection: Optional[smtplib.SMTP] = None
        self.consecutive_errors: int = 0

    # ─── SMTP Connection Management ───────────────────────

    def connect(self) -> bool:
        """Establish SMTP connection with TLS."""
        try:
            logger.info(f"Connecting to {self.config.smtp.host}:{self.config.smtp.port}...")

            # Create SSL context
            context = ssl.create_default_context()

            # Connect
            self.smtp_connection = smtplib.SMTP(
                self.config.smtp.host,
                self.config.smtp.port,
                timeout=30
            )

            # Enable TLS
            if self.config.smtp.use_tls:
                self.smtp_connection.ehlo()
                self.smtp_connection.starttls(context=context)
                self.smtp_connection.ehlo()

            # Authenticate
            self.smtp_connection.login(
                self.config.smtp.username,
                self.config.smtp.password
            )

            logger.info("✅ SMTP connection established successfully")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"❌ Authentication failed: {e}")
            print(
                "\n❌ SMTP Authentication Failed!\n"
                "   Make sure you're using a Gmail App Password, NOT your regular password.\n"
                "   Steps:\n"
                "   1. Enable 2FA at https://myaccount.google.com/security\n"
                "   2. Create App Password at https://myaccount.google.com/apppasswords\n"
                "   3. Set EMAIL_PASSWORD environment variable\n"
            )
            return False

        except Exception as e:
            logger.error(f"❌ SMTP connection failed: {e}")
            return False

    def disconnect(self):
        """Safely close SMTP connection."""
        if self.smtp_connection:
            try:
                self.smtp_connection.quit()
                logger.info("SMTP connection closed")
            except Exception:
                pass
            self.smtp_connection = None

    def _ensure_connected(self) -> bool:
        """Ensure we have a live SMTP connection, reconnect if needed."""
        if self.smtp_connection is None:
            return self.connect()

        try:
            # Test connection with NOOP
            status = self.smtp_connection.noop()
            return status[0] == 250
        except Exception:
            logger.warning("SMTP connection lost, reconnecting...")
            self.disconnect()
            return self.connect()

    # ─── Email Building ───────────────────────────────────

    def _build_plain_signature(self) -> str:
        """Build a professional plain-text signature."""
        sig = self.config.signature
        sender = self.config.sender
        lines = [
            "",
            "—",
            f"{sender.name}",
        ]
        if sig.title:
            lines.append(sig.title)
        lines.append("")
        if sender.phone:
            lines.append(f"Tél : {sender.phone}")
        if sender.email:
            lines.append(f"Email : {sender.email}")
        if sig.portfolio_url:
            lines.append(f"Portfolio : {sig.portfolio_url}")
        if sig.github_url:
            lines.append(f"GitHub : {sig.github_url}")
        if sig.linkedin_url:
            lines.append(f"LinkedIn : {sig.linkedin_url}")
        return "\n".join(lines)

    # ── Icon URLs (hosted PNGs — works in all email clients) ──
    ICON_PHONE    = "https://img.icons8.com/fluency/18/phone.png"
    ICON_EMAIL    = "https://img.icons8.com/fluency/18/email.png"
    ICON_GLOBE    = "https://img.icons8.com/fluency/18/domain.png"
    ICON_GITHUB   = "https://img.icons8.com/fluency/18/github.png"
    ICON_LINKEDIN = "https://img.icons8.com/fluency/18/linkedin.png"

    def _icon(self, url: str, alt: str = "") -> str:
        """Render a small inline icon image tag for email signatures."""
        return (
            f'<img src="{url}" alt="{alt}" width="16" height="16" '
            f'style="vertical-align:middle;border:0;margin-right:5px;" />'
        )

    def _build_html_signature(self) -> str:
        """
        Build a professional HTML email signature with icons.
        Uses tables + hosted PNG icons for maximum email client compatibility
        (Outlook, Gmail, Yahoo, Apple Mail, etc.).
        """
        sig = self.config.signature
        sender = self.config.sender
        accent = sig.accent_color or "#2563EB"

        # ── Contact rows with icons ──
        contact_rows = []
        if sender.phone:
            contact_rows.append(
                f'<tr><td style="padding:2px 0;font-size:13px;color:#333333;">'
                f'{self._icon(self.ICON_PHONE, "Tel")}'
                f'<a href="tel:{sender.phone.replace(" ", "")}" '
                f'style="color:#333333;text-decoration:none;">{html_module.escape(sender.phone)}</a>'
                f'</td></tr>'
            )
        if sender.email:
            contact_rows.append(
                f'<tr><td style="padding:2px 0;font-size:13px;color:#333333;">'
                f'{self._icon(self.ICON_EMAIL, "Email")}'
                f'<a href="mailto:{html_module.escape(sender.email)}" '
                f'style="color:#333333;text-decoration:none;">{html_module.escape(sender.email)}</a>'
                f'</td></tr>'
            )

        # ── Social link rows with icons ──
        social_rows = []
        if sig.portfolio_url:
            social_rows.append(
                f'<tr><td style="padding:2px 0;font-size:13px;">'
                f'{self._icon(self.ICON_GLOBE, "Portfolio")}'
                f'<a href="{html_module.escape(sig.portfolio_url)}" '
                f'style="color:{accent};text-decoration:none;font-weight:500;" '
                f'target="_blank">Portfolio</a></td></tr>'
            )
        if sig.github_url:
            social_rows.append(
                f'<tr><td style="padding:2px 0;font-size:13px;">'
                f'{self._icon(self.ICON_GITHUB, "GitHub")}'
                f'<a href="{html_module.escape(sig.github_url)}" '
                f'style="color:{accent};text-decoration:none;font-weight:500;" '
                f'target="_blank">GitHub</a></td></tr>'
            )
        if sig.linkedin_url:
            social_rows.append(
                f'<tr><td style="padding:2px 0;font-size:13px;">'
                f'{self._icon(self.ICON_LINKEDIN, "LinkedIn")}'
                f'<a href="{html_module.escape(sig.linkedin_url)}" '
                f'style="color:{accent};text-decoration:none;font-weight:500;" '
                f'target="_blank">LinkedIn</a></td></tr>'
            )

        # ── Optional logo/photo ──
        logo_html = ""
        if sig.logo_url:
            logo_html = f"""
          <td width="75" valign="top" style="padding-right:15px;">
            <img src="{html_module.escape(sig.logo_url)}" alt="{html_module.escape(sender.name)}"
                 width="64" height="64"
                 style="border-radius:50%;border:2px solid {accent};display:block;" />
          </td>"""

        all_contact = '\n'.join(contact_rows)
        all_social = '\n'.join(social_rows)

        # Spacer row between contact and social if both exist
        spacer = ""
        if contact_rows and social_rows:
            spacer = '<tr><td style="padding:4px 0;font-size:1px;line-height:1px;">&nbsp;</td></tr>'

        return f"""
<table cellpadding="0" cellspacing="0" border="0" style="margin-top:20px;border-collapse:collapse;">
  <tr>
    <td colspan="2" style="padding-bottom:10px;">
      <table cellpadding="0" cellspacing="0" border="0" width="300">
        <tr><td style="border-top:2px solid {accent};font-size:1px;line-height:1px;">&nbsp;</td></tr>
      </table>
    </td>
  </tr>
  <tr>{logo_html}
    <td valign="top" style="font-family:Arial,Helvetica,sans-serif;">
      <table cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="font-size:16px;font-weight:bold;color:#1A1A1A;padding-bottom:2px;">
            {html_module.escape(sender.name)}
          </td>
        </tr>
        <tr>
          <td style="font-size:13px;color:{accent};font-weight:600;padding-bottom:10px;">
            {html_module.escape(sig.title)}
          </td>
        </tr>
{all_contact}
{spacer}
{all_social}
      </table>
    </td>
  </tr>
</table>"""

    def _body_to_html(self, plain_text: str) -> str:
        """
        Convert plain-text email body to clean HTML.
        Handles paragraphs, bullet points (•), and links.
        """
        import re

        # Escape HTML special chars first
        text = html_module.escape(plain_text)

        # Convert URLs to clickable links
        url_pattern = r'(https?://[^\s&lt;]+)'
        text = re.sub(url_pattern, r'<a href="\1" style="color:#2563EB;text-decoration:none;">\1</a>', text)

        # Split into paragraphs
        paragraphs = text.split('\n\n')
        html_parts = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            lines = para.split('\n')
            # Check if this paragraph contains bullet points
            bullet_lines = [l for l in lines if l.strip().startswith('•') or l.strip().startswith('&bull;')]

            if bullet_lines and len(bullet_lines) >= len(lines) * 0.5:
                # This is a bullet list — possibly with a header line
                list_html = ""
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith('•') or stripped.startswith('&bull;'):
                        item_text = stripped.lstrip('•').lstrip('&bull;').strip()
                        list_html += f'<li style="margin-bottom:3px;">{item_text}</li>\n'
                    else:
                        # Header line before bullets
                        if list_html:
                            html_parts.append(
                                f'<ul style="margin:5px 0 5px 15px;padding:0;list-style:disc;'
                                f'color:#333333;font-size:14px;line-height:22px;">{list_html}</ul>'
                            )
                            list_html = ""
                        html_parts.append(
                            f'<p style="margin:0 0 8px 0;color:#333333;'
                            f'font-size:14px;line-height:22px;">{stripped}</p>'
                        )
                if list_html:
                    html_parts.append(
                        f'<ul style="margin:5px 0 5px 15px;padding:0;list-style:disc;'
                        f'color:#333333;font-size:14px;line-height:22px;">{list_html}</ul>'
                    )
            else:
                # Regular paragraph
                combined = '<br/>'.join(l.strip() for l in lines if l.strip())
                html_parts.append(
                    f'<p style="margin:0 0 12px 0;color:#333333;'
                    f'font-size:14px;line-height:22px;">{combined}</p>'
                )

        return '\n'.join(html_parts)

    def _resolve_cv_path(self, lang: str = 'fr') -> str:
        """
        Resolve which CV file to attach based on detected language.

        Rules:
          - French emails → attach cv_fr.pdf
          - English emails → attach cv_en.pdf
          - No cross-language fallback (never send FR CV with EN email or vice-versa)

        Auto-discovers CVs from the cv/ folder. No config needed.
        Returns empty string if no CV found (email sends without attachment).
        """
        cfg = self.config.email_content

        # Auto-discover from cv/ folder next to this script
        cv_dir = Path(__file__).parent / 'cv'
        auto_fr = str(cv_dir / 'cv_fr.pdf')
        auto_en = str(cv_dir / 'cv_en.pdf')

        # Pick candidates for the detected language ONLY (no fallback)
        if lang == 'fr':
            candidates = [p for p in [cfg.cv_path_fr, auto_fr] if p]
        else:
            candidates = [p for p in [cfg.cv_path_en, auto_en] if p]

        for p in candidates:
            if Path(p).is_file():
                return p

        # No matching CV for this language → send without attachment
        return ""

    def _build_message(self, contact: Contact, lang: str = 'fr') -> MIMEMultipart:
        """
        Build a properly formatted email with HTML body + professional signature.
        Includes both plain-text and HTML parts (multipart/alternative).
        Optionally attaches a CV/resume file (auto-selects FR/EN based on lang).
        """
        # Resolve the correct CV for this contact's language
        # Auto-attaches if CV files exist, skips silently if not
        cv_file = self._resolve_cv_path(lang)

        if cv_file:
            msg = MIMEMultipart('mixed')
            body_container = MIMEMultipart('alternative')
        else:
            msg = MIMEMultipart('alternative')
            body_container = msg

        # ── Required headers ──
        msg['From'] = formataddr((
            self.config.sender.name,
            self.config.sender.email
        ))
        msg['To'] = contact.email
        msg['Subject'] = contact.subject
        msg['Reply-To'] = self.config.sender.reply_to

        # ── Anti-spam headers ──
        if self.config.email_content.add_date_header:
            msg['Date'] = formatdate(localtime=True)

        if self.config.email_content.add_message_id:
            domain = self.config.sender.email.split('@')[1]
            msg['Message-ID'] = make_msgid(domain=domain)

        if self.config.email_content.add_list_unsubscribe:
            msg['List-Unsubscribe'] = f'<mailto:{self.config.sender.email}?subject=unsubscribe>'

        # ── MIME version ──
        msg['MIME-Version'] = '1.0'

        # ── Priority (normal) ──
        msg['X-Priority'] = '3'
        msg['X-Mailer'] = 'Professional-Outreach/1.0'

        # ── Body text (AI-generated, without signature) ──
        body_text = contact.body

        # Add small unique variation to avoid identical content detection
        if self.config.email_content.add_random_greeting_variation:
            body_text = self._add_subtle_variation(body_text)

        # ── 1. Plain-text part (always attached first) ──
        plain_signature = self._build_plain_signature()
        plain_full = body_text + "\n" + plain_signature
        text_part = MIMEText(plain_full, 'plain', self.config.email_content.charset)
        body_container.attach(text_part)

        # ── 2. HTML part (rich formatting + professional signature) ──
        if self.config.email_content.send_as_html:
            html_body = self._body_to_html(body_text)
            html_signature = self._build_html_signature()

            html_full = f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:20px;font-family:Arial,Helvetica,sans-serif;background-color:#FFFFFF;">
<div style="max-width:600px;margin:0 auto;">
{html_body}
{html_signature}
</div>
</body>
</html>"""

            html_part = MIMEText(html_full, 'html', self.config.email_content.charset)
            body_container.attach(html_part)

        # ── 3. CV/Resume attachment (optional) ──
        if cv_file:
            msg.attach(body_container)
            cv_path = Path(cv_file)
            mime_type, _ = mimetypes.guess_type(str(cv_path))
            if mime_type is None:
                mime_type = 'application/octet-stream'
            main_type, sub_type = mime_type.split('/', 1)

            with open(cv_path, 'rb') as f:
                attachment = MIMEBase(main_type, sub_type)
                attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            attachment.add_header(
                'Content-Disposition', 'attachment',
                filename=cv_path.name
            )
            msg.attach(attachment)
            lang_label = "🇫🇷 FR" if lang == 'fr' else "🇬🇧 EN"
            logger.debug(f"Attached CV ({lang_label}): {cv_path.name}")

        return msg

    def _add_subtle_variation(self, body: str) -> str:
        """
        Add subtle, invisible variations to email content.
        This prevents spam filters from detecting identical mass emails.
        Uses a zero-width space + unique HTML comment (invisible to recipient).
        """
        # Each email is already unique via Message-ID header and personalized content.
        # Add an invisible zero-width space variation for extra uniqueness.
        now = datetime.now()
        variation = f"\u200B"  # Zero-width space — invisible but makes text unique
        # Insert at a random position in the body for natural variation
        words = body.split(' ')
        if len(words) > 10:
            pos = random.randint(5, len(words) - 3)
            words[pos] = words[pos] + variation
        return ' '.join(words)

    # ─── Sending Logic ────────────────────────────────────

    def should_skip(self, contact: Contact) -> Optional[str]:
        """
        Check if a contact should be skipped. Returns reason string or None.
        """
        email = contact.email.lower()

        # Already sent
        if self.tracker.is_already_sent(email):
            return "Already sent (tracked)"

        # In skip list
        if email in [e.lower() for e in self.config.filters.skip_emails]:
            return "In skip list"

        # No custom email template
        if not contact.has_custom_email or not contact.body.strip():
            return "No email template available"

        # No subject
        if not contact.subject.strip():
            return "Missing subject line"

        # Below minimum relevance
        if contact.relevance < self.config.filters.min_relevance_stars:
            return f"Relevance too low ({contact.relevance} < {self.config.filters.min_relevance_stars} stars)"

        # Personal email filter
        if self.config.filters.skip_personal_emails:
            domain = email.split('@')[1] if '@' in email else ''
            if domain in self.GENERIC_DOMAINS:
                return f"Personal email domain ({domain})"

        # Domain filter
        if self.config.filters.only_domains:
            domain = email.split('@')[1] if '@' in email else ''
            if domain not in self.config.filters.only_domains:
                return f"Domain not in allowed list ({domain})"

        return None

    def send_one(self, contact: Contact) -> Tuple[bool, str]:
        """
        Send a single email with retry logic.

        Returns:
            (success: bool, message: str)
        """
        # Detect language for CV auto-selection
        lang = LanguageDetector().detect_for_contact(contact)

        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would send to: {contact.email}")
            return True, "DRY RUN \u2014 not actually sent"

        # Ensure connection
        if not self._ensure_connected():
            return False, "Could not establish SMTP connection"

        # Build message
        msg = self._build_message(contact, lang=lang)

        # Retry loop
        last_error = ""
        for attempt in range(1, self.config.rate_limit.max_retries_per_email + 1):
            try:
                # Send!
                result = self.smtp_connection.send_message(msg)

                # Record success
                self.rate_limiter.record_sent()
                self.consecutive_errors = 0

                response_str = str(result) if result else "OK"
                return True, f"Sent successfully (attempt {attempt})"

            except smtplib.SMTPRecipientsRefused as e:
                last_error = f"Recipient refused: {e}"
                logger.warning(f"Recipient refused {contact.email}: {e}")
                break  # Don't retry — recipient issue

            except smtplib.SMTPSenderRefused as e:
                last_error = f"Sender refused: {e}"
                logger.error(f"Sender refused (account issue?): {e}")
                break  # Don't retry — account issue

            except smtplib.SMTPDataError as e:
                last_error = f"SMTP data error: {e}"
                logger.warning(f"SMTP data error for {contact.email}: {e}")
                if attempt < self.config.rate_limit.max_retries_per_email:
                    time.sleep(self.config.rate_limit.retry_delay_seconds)

            except smtplib.SMTPServerDisconnected:
                last_error = "Server disconnected"
                logger.warning("Server disconnected, reconnecting...")
                self.disconnect()
                if not self.connect():
                    break
                msg = self._build_message(contact, lang=lang)  # Rebuild message

            except (socket.timeout, ConnectionError) as e:
                last_error = f"Connection error: {e}"
                logger.warning(f"Connection error: {e}")
                self.disconnect()
                if attempt < self.config.rate_limit.max_retries_per_email:
                    time.sleep(self.config.rate_limit.retry_delay_seconds)
                    if not self.connect():
                        break

            except Exception as e:
                last_error = f"Unexpected error: {e}"
                logger.error(f"Unexpected error sending to {contact.email}: {e}")
                if attempt < self.config.rate_limit.max_retries_per_email:
                    time.sleep(self.config.rate_limit.retry_delay_seconds)

        self.consecutive_errors += 1
        return False, last_error

    def send_campaign(self, contacts: List[Contact]) -> dict:
        """
        Send emails to a list of contacts with full protection.

        Returns session statistics dict.
        """
        total = len(contacts)
        sendable = []
        skip_reasons = {}

        # ── Pre-filter contacts ──
        print(f"\n{'='*60}")
        print(f"  📧 PRE-FLIGHT CHECK — {total} contacts")
        print(f"{'='*60}")

        for contact in contacts:
            reason = self.should_skip(contact)
            if reason:
                self.tracker.record_skipped(contact.email, contact.company, reason)
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            else:
                sendable.append(contact)

        print(f"  ✅ Ready to send:  {len(sendable)}")
        print(f"  ⏭️  Skipping:       {total - len(sendable)}")
        if skip_reasons:
            for reason, count in skip_reasons.items():
                print(f"     └─ {reason}: {count}")
        print(f"{'='*60}")

        if not sendable:
            print("\n  ℹ️  No emails to send!")
            return self.tracker.get_session_stats()

        # ── Confirm before sending ──
        if not self.config.dry_run and not getattr(self, 'auto_confirm', False):
            print(f"\n  ⚠️  LIVE MODE — Emails will be sent for real!")
            print(f"  Rate: ~{self.config.rate_limit.min_delay_seconds}-{self.config.rate_limit.max_delay_seconds}s delay between emails")
            print(f"  Batches of {self.config.rate_limit.batch_size} with {self.config.rate_limit.batch_pause_minutes}min pause")
            print(f"\n  Press Enter to continue, or Ctrl+C to cancel...")
            try:
                input()
            except KeyboardInterrupt:
                print("\n  ❌ Cancelled by user.")
                return self.tracker.get_session_stats()
        elif not self.config.dry_run:
            print(f"\n  ⚠️  LIVE MODE — Auto-confirmed (--yes)")
        else:
            print(f"\n  🔵 DRY RUN MODE — No emails will actually be sent")

        # ── Connect SMTP ──
        if not self.config.dry_run:
            if not self.connect():
                print("  ❌ Could not connect to SMTP server. Aborting.")
                return self.tracker.get_session_stats()

        # ── Send loop ──
        try:
            for i, contact in enumerate(sendable, 1):
                # Check consecutive error limit
                if self.consecutive_errors >= self.config.rate_limit.max_consecutive_errors:
                    print(
                        f"\n  🛑 Too many consecutive errors "
                        f"({self.consecutive_errors}). Stopping."
                        f"\n  Run again to resume from where you left off.\n"
                    )
                    logger.error("Stopped due to consecutive errors")
                    break

                # Rate limiting
                self.rate_limiter.wait_if_needed()

                # Progress display
                progress = f"[{i}/{len(sendable)}]"
                print(
                    f"  {progress} 📤 {contact.company:<25} → {contact.email}",
                    end="", flush=True
                )

                # Send
                success, message = self.send_one(contact)

                if success:
                    self.tracker.record_sent(
                        contact.email, contact.company, contact.subject, message
                    )
                    print(f"  ✅ {message}")
                else:
                    self.tracker.record_failed(
                        contact.email, contact.company, contact.subject, message
                    )
                    print(f"  ❌ {message}")

                # Delay before next email (skip on last email)
                if i < len(sendable):
                    self.rate_limiter.add_random_delay()
                    self.rate_limiter.check_batch_pause()

        except KeyboardInterrupt:
            print("\n\n  ⚠️  Interrupted by user. Progress has been saved.")
            print("  Run again to resume from where you left off.\n")

        finally:
            self.disconnect()

        return self.tracker.get_session_stats()


class EmailValidator:
    """Basic email validation before sending."""

    @staticmethod
    def validate_email(email: str) -> Tuple[bool, str]:
        """Validate email format."""
        import re

        if not email or not email.strip():
            return False, "Empty email"

        email = email.strip().lower()

        # Basic format check
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return False, f"Invalid format: {email}"

        # Check for obviously fake domains
        domain = email.split('@')[1]
        if domain in ('example.com', 'test.com', 'localhost'):
            return False, f"Test domain: {domain}"

        return True, "Valid"

    @staticmethod
    def validate_contact(contact: Contact) -> Tuple[bool, str]:
        """Validate a contact is ready to receive an email."""
        # Email valid?
        valid, msg = EmailValidator.validate_email(contact.email)
        if not valid:
            return False, msg

        # Has content?
        if not contact.subject:
            return False, "Missing subject"

        if not contact.body or len(contact.body.strip()) < 50:
            return False, "Body too short or missing"

        return True, "Ready"
