"""
══════════════════════════════════════════════════════════════
  Auto Follow-Up System
  Sends follow-up emails to contacts who haven't replied
══════════════════════════════════════════════════════════════

  Automatically generates and sends follow-up emails to contacts
  who were emailed X days ago but haven't responded yet.

  Features:
  - Configurable delay (default: 5 days)
  - AI-generated follow-up with different tone (shorter, lighter)
  - Maximum follow-ups per contact (default: 2)
  - Respects rate limiting and anti-spam rules
  - Tracks follow-ups separately

  Usage (CLI):
    python main.py --follow-up                    # Follow up after 5 days
    python main.py --follow-up --days 7           # Follow up after 7 days
    python main.py --follow-up --max-followups 1  # Only 1 follow-up per contact
    python main.py --follow-up --preview          # Preview without sending

  Setup:
    Uses same SMTP and AI settings as regular emails.
"""

import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)


@dataclass
class FollowUpRecord:
    """Record of a follow-up email sent."""
    email: str
    company: str
    followup_number: int        # 1st, 2nd, 3rd follow-up
    subject: str
    timestamp: str = ""
    status: str = "sent"        # "sent", "failed"

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class FollowUpTracker:
    """
    Tracks follow-up emails separately from initial sends.
    Persists to JSON file for resume capability.
    """

    def __init__(self, tracker_file: str):
        self.tracker_path = Path(tracker_file)
        self.tracker_path.parent.mkdir(parents=True, exist_ok=True)
        self.followups: Dict[str, List[FollowUpRecord]] = {}  # email -> list of follow-ups
        self._load()

    def _load(self):
        """Load existing follow-up data."""
        if self.tracker_path.exists():
            try:
                data = json.loads(self.tracker_path.read_text(encoding='utf-8'))
                for email_addr, records in data.get('followups', {}).items():
                    self.followups[email_addr] = [
                        FollowUpRecord(**r) for r in records
                    ]
                logger.info(f"Loaded {sum(len(v) for v in self.followups.values())} follow-up records")
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Could not load follow-up tracker: {e}")

    def _save(self):
        """Save follow-up data to disk."""
        data = {
            'last_updated': datetime.now().isoformat(),
            'total_followups': sum(len(v) for v in self.followups.values()),
            'contacts_followed_up': len(self.followups),
            'followups': {
                email: [asdict(r) for r in records]
                for email, records in self.followups.items()
            },
        }
        self.tracker_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

    def get_followup_count(self, email: str) -> int:
        """Get number of follow-ups sent to this email."""
        return len(self.followups.get(email.lower(), []))

    def record_followup(self, email: str, company: str, subject: str,
                        followup_number: int, status: str = "sent"):
        """Record a follow-up email."""
        email_lower = email.lower()
        record = FollowUpRecord(
            email=email_lower,
            company=company,
            followup_number=followup_number,
            subject=subject,
            status=status,
        )
        if email_lower not in self.followups:
            self.followups[email_lower] = []
        self.followups[email_lower].append(record)
        self._save()


class FollowUpGenerator:
    """
    Generates follow-up email content using AI.
    Follow-ups are shorter & lighter than initial emails.
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self._init_ai()

    def _init_ai(self):
        """Initialize AI client."""
        api_key = os.getenv("OPENAI_API_KEY", "")
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

        if not api_key and not openrouter_key:
            raise ValueError("No AI API key set! Set OPENAI_API_KEY or OPENROUTER_API_KEY in .env")

        from openai import OpenAI

        if api_key:
            self.client = OpenAI(api_key=api_key)
            self.provider = "OpenAI"
        else:
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=openrouter_key,
            )
            self.model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
            self.provider = "OpenRouter"

    def generate_followup(
        self,
        company: str,
        position: str,
        email: str,
        original_subject: str,
        followup_number: int = 1,
        lang: str = "fr",
    ) -> Tuple[str, str]:
        """
        Generate a follow-up email subject and body.

        Args:
            followup_number: 1 = first follow-up, 2 = second, etc.
            lang:           'fr' for French, 'en' for English.

        Returns:
            Tuple of (subject, body)
        """
        sender_name = os.getenv("SENDER_NAME", "Your Name")

        if lang == "en":
            system_prompt = self._build_en_prompt(followup_number, sender_name)
            user_prompt = (
                f"Generate a follow-up email #{followup_number} for:\n"
                f"- Company: {company}\n"
                f"- Position: {position}\n"
                f"- Original subject: {original_subject}\n"
                f'Respond ONLY in JSON: {{"subject": "...", "body": "..."}}'
            )
            default_subject = f"Re: {original_subject}"
        else:
            system_prompt = self._build_fr_prompt(followup_number, sender_name)
            user_prompt = (
                f"Génère un email de relance #{followup_number} pour:\n"
                f"- Entreprise: {company}\n"
                f"- Poste: {position}\n"
                f"- Sujet original: {original_subject}\n"
                f'Réponds UNIQUEMENT en JSON: {{"subject": "...", "body": "..."}}'
            )
            default_subject = f"Re: {original_subject}"

        try:
            kwargs = dict(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=600,
            )
            if self.provider == "OpenAI":
                kwargs["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**kwargs)
            raw = response.choices[0].message.content

            data = json.loads(raw)
            subject = data.get('subject', default_subject)
            body = data.get('body', '')

            if not subject:
                subject = default_subject
            return subject, body

        except Exception as e:
            logger.error(f"Follow-up generation failed: {e}")
            # Return a simple template fallback
            if lang == "en":
                body = (
                    f"Dear Hiring Manager,\n\n"
                    f"I wanted to follow up on my previous email regarding the "
                    f"{position} position at {company}.\n\n"
                    f"I remain very interested in this opportunity and would be happy "
                    f"to discuss how my skills could contribute to your team.\n\n"
                    f"Best regards,"
                )
            else:
                body = (
                    f"Madame, Monsieur,\n\n"
                    f"Je me permets de revenir vers vous concernant ma candidature "
                    f"pour le poste de {position} au sein de {company}.\n\n"
                    f"Je reste très motivé par cette opportunité et serais ravi "
                    f"d'échanger avec vous sur la valeur que je pourrais apporter à votre équipe.\n\n"
                    f"Cordialement,"
                )
            return default_subject, body

    def _build_fr_prompt(self, followup_number: int, sender_name: str) -> str:
        """French follow-up system prompt."""
        tone = "poli et professionnel" if followup_number == 1 else "bref et direct"
        return f"""Tu es un assistant qui génère des emails de relance professionnels en français.

RÈGLES:
1. Ton {tone}
2. L'email de relance doit être COURT (3-5 phrases maximum)
3. Rappeler brièvement la candidature initiale
4. {"Montrer un intérêt sincère sans être insistant" if followup_number == 1 else "Être encore plus concis, mentionner que c'est la dernière relance"}
5. Terminer par "Cordialement," — PAS de signature/liens/coordonnées
6. Le sujet doit commencer par "Re: " suivi du sujet original
7. Commencer par "Madame, Monsieur," ou "Bonjour,"
8. NE PAS inclure signature, nom, téléphone, email, liens — ajoutés automatiquement
9. JAMAIS de texte entre crochets ou de placeholders

Réponds EXACTEMENT en JSON: {{"subject": "...", "body": "..."}}
Le body commence à la salutation, sans signature.
"""

    def _build_en_prompt(self, followup_number: int, sender_name: str) -> str:
        """English follow-up system prompt."""
        tone = "polite and professional" if followup_number == 1 else "brief and direct"
        return f"""You are an assistant that generates professional follow-up emails in English.

RULES:
1. Tone: {tone}
2. The follow-up must be SHORT (3-5 sentences maximum)
3. Briefly reference the initial application
4. {"Show genuine interest without being pushy" if followup_number == 1 else "Be even more concise, mention this is the final follow-up"}
5. End with "Best regards," — NO signature/links/contact info
6. Subject should start with "Re: " followed by original subject
7. Start with "Dear Hiring Manager," or "Hello,"
8. Do NOT include signature, name, phone, email, links — added automatically
9. NEVER use bracket placeholders

Respond EXACTLY in JSON: {{"subject": "...", "body": "..."}}
The body starts at the salutation, no signature.
"""


# ═══════════════════════════════════════════════════════════
#  Main Follow-Up Command
# ═══════════════════════════════════════════════════════════

def cmd_followup(
    config,
    days: int = 5,
    max_followups: int = 2,
    limit: int = 0,
    preview: bool = False,
    min_stars: int = 1,
):
    """
    Send follow-up emails to contacts who haven't replied.

    Args:
        config:        CampaignConfig
        days:          Days to wait before following up
        max_followups: Maximum follow-ups per contact
        limit:         Max follow-ups to send this session (0 = no limit)
        preview:       If True, just show what would be sent
        min_stars:     Minimum relevance stars
    """
    from tracker import SentTracker

    print(f"\n{'='*60}")
    print(f"  🔄 AUTO FOLLOW-UP SYSTEM")
    print(f"{'='*60}")
    print(f"  ⏰ Follow up after: {days} days without reply")
    print(f"  🔢 Max follow-ups per contact: {max_followups}")
    if limit:
        print(f"  📊 Session limit: {limit}")

    # Load trackers
    tracker = SentTracker(config.paths.sent_tracker_file, config.paths.failed_file)
    followup_tracker_file = str(
        Path(config.paths.log_dir) / "followup_tracker.json"
    )
    fu_tracker = FollowUpTracker(followup_tracker_file)

    # Find contacts eligible for follow-up
    cutoff = datetime.now() - timedelta(days=days)
    eligible = []

    for email_addr, record in tracker.sent.items():
        # Skip if already replied
        if getattr(record, 'status', '') == 'replied':
            continue

        # Skip if max follow-ups reached
        fu_count = fu_tracker.get_followup_count(email_addr)
        if fu_count >= max_followups:
            continue

        # Check if enough time has passed
        try:
            sent_time = datetime.fromisoformat(record.timestamp)
        except (ValueError, TypeError):
            continue

        # For first follow-up: check time since original send
        # For subsequent: check time since last follow-up
        if fu_count > 0:
            last_fu = fu_tracker.followups[email_addr][-1]
            try:
                last_fu_time = datetime.fromisoformat(last_fu.timestamp)
                if last_fu_time > cutoff:
                    continue  # Not enough time since last follow-up
            except (ValueError, TypeError):
                continue
        else:
            if sent_time > cutoff:
                continue  # Not enough time since original send

        eligible.append({
            'email': email_addr,
            'company': record.company,
            'subject': record.subject,
            'followup_number': fu_count + 1,
            'sent_date': record.timestamp,
        })

    if not eligible:
        print(f"\n  ✅ No contacts eligible for follow-up!")
        print(f"     (Either too recent, already replied, or max follow-ups reached)")
        print(f"{'='*60}\n")
        return

    if limit > 0:
        eligible = eligible[:limit]

    print(f"\n  📋 Eligible for follow-up: {len(eligible)} contacts")

    # Show preview
    for i, info in enumerate(eligible[:10], 1):
        fu_num = info['followup_number']
        print(f"    [{fu_num}] {info['company']:<25} → {info['email']}")
    if len(eligible) > 10:
        print(f"    ... and {len(eligible) - 10} more")

    if preview:
        print(f"\n  👁️  PREVIEW MODE — No emails sent")
        print(f"{'='*60}\n")
        return

    # Detect language (lazy import)
    try:
        from language_detector import LanguageDetector
        detector = LanguageDetector(default_lang="fr")
    except ImportError:
        detector = None

    # Generate and send follow-ups
    try:
        generator = FollowUpGenerator(model=getattr(config, '_ai_model', 'gpt-4o-mini'))
    except (ValueError, ImportError) as e:
        print(f"\n  ❌ AI init failed: {e}")
        return

    from email_sender import EmailSender
    from parse_contacts import Contact

    sender = EmailSender(config, tracker)

    if not config.dry_run:
        if not sender.connect():
            print("  ❌ Could not connect to SMTP. Aborting.")
            return

    sent_count = 0
    failed_count = 0

    try:
        for i, info in enumerate(eligible, 1):
            # Detect language
            lang = "fr"
            if detector:
                lang = detector.detect(email=info['email'], company=info['company'])

            # Generate follow-up
            fu_num = info['followup_number']
            lang_tag = "🇫🇷" if lang == "fr" else "🇬🇧"
            print(
                f"  [{i}/{len(eligible)}] {lang_tag} Follow-up #{fu_num} → "
                f"{info['company']:<20} {info['email']}",
                end="  ", flush=True
            )

            subject, body = generator.generate_followup(
                company=info['company'],
                position="",  # Position not stored in tracker
                email=info['email'],
                original_subject=info['subject'],
                followup_number=fu_num,
                lang=lang,
            )

            # Build contact for sending
            contact = Contact(
                index=0,
                company=info['company'],
                email=info['email'],
                position="Follow-up",
                city="",
                relevance=2,
                subject=subject,
                body=body,
                has_custom_email=True,
            )

            if config.dry_run:
                print(f"✅ [DRY RUN]")
                fu_tracker.record_followup(
                    info['email'], info['company'], subject, fu_num
                )
                sent_count += 1
            else:
                success, message = sender.send_one(contact)
                if success:
                    print(f"✅")
                    fu_tracker.record_followup(
                        info['email'], info['company'], subject, fu_num
                    )
                    sent_count += 1
                else:
                    print(f"❌ {message}")
                    fu_tracker.record_followup(
                        info['email'], info['company'], subject, fu_num,
                        status="failed"
                    )
                    failed_count += 1

                # Rate limiting
                if i < len(eligible):
                    sender.rate_limiter.add_random_delay()

    except KeyboardInterrupt:
        print("\n\n  ⚠️  Interrupted. Progress saved.")

    finally:
        sender.disconnect()

    # Summary
    print(f"\n  {'─'*56}")
    print(f"  📊 FOLLOW-UP RESULTS")
    print(f"  ✅ Sent:   {sent_count}")
    print(f"  ❌ Failed: {failed_count}")
    if config.dry_run:
        print(f"  🔵 (DRY RUN — no emails actually sent)")
    print(f"{'='*60}\n")
