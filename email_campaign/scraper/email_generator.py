"""
══════════════════════════════════════════════════════════════
  AI Email Body Generator (OpenAI GPT + OpenRouter fallback)
  Generates personalized prospection emails for scraped contacts
══════════════════════════════════════════════════════════════

  Uses OpenAI GPT as primary provider, falls back to OpenRouter
  (compatible with many models) when OpenAI quota is exceeded.

  Setup (in .env):
    OPENAI_API_KEY=sk-your-key-here
    OPENROUTER_API_KEY=sk-or-v1-your-key-here

  Usage:
    python main.py --merge-scraped               # Merge + generate emails
    python main.py --generate-emails              # Generate for contacts without emails
    python main.py --generate-emails --min-stars 2  # Only for ⭐⭐+ contacts
"""

import os
import re
import sys
import json
import time
import logging
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass

# Load .env for OPENAI_API_KEY etc.
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

logger = logging.getLogger(__name__)

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ═══════════════════════════════════════════════════════════
#  Sender identity (from .env)
# ═══════════════════════════════════════════════════════════
SENDER_NAME  = os.getenv("SENDER_NAME", "Your Name")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "your.email@gmail.com")
SENDER_PHONE = os.getenv("SENDER_PHONE", "+212 000 000 000")

# ═══════════════════════════════════════════════════════════
#  Your Profile — loaded from sender_profile.txt (gitignored)
#  Copy sender_profile.example.txt → sender_profile.txt
#  and fill in your real data.
# ═══════════════════════════════════════════════════════════
_SCRAPER_DIR = Path(__file__).resolve().parent
_PROFILE_FILE = _SCRAPER_DIR / "sender_profile.txt"

if _PROFILE_FILE.exists():
    SENDER_PROFILE = _PROFILE_FILE.read_text(encoding="utf-8")
else:
    logger.warning(
        f"sender_profile.txt not found — using minimal profile from .env. "
        f"Copy sender_profile.example.txt → sender_profile.txt and customise it."
    )
    SENDER_PROFILE = f"""Nom: {SENDER_NAME}
Contact: {SENDER_PHONE} — {SENDER_EMAIL}
"""

# ═══════════════════════════════════════════════════════════
#  Example emails (few-shot learning for GPT)
#  Loaded from example_emails.json (gitignored).
#  Copy example_emails.example.json → example_emails.json
#  and customise with your own style samples.
# ═══════════════════════════════════════════════════════════
_EXAMPLES_FILE = _SCRAPER_DIR / "example_emails.json"

if _EXAMPLES_FILE.exists():
    try:
        EXAMPLE_EMAILS = json.loads(_EXAMPLES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Could not load example_emails.json: {exc}")
        EXAMPLE_EMAILS = []
else:
    logger.warning(
        "example_emails.json not found — GPT will generate without style examples. "
        "Copy example_emails.example.json → example_emails.json and customise it."
    )
    EXAMPLE_EMAILS = []


# ═══════════════════════════════════════════════════════════
#  OpenAI Email Generator
# ═══════════════════════════════════════════════════════════

class AIEmailGenerator:
    """
    Generates personalized email subject + body using OpenAI GPT.
    Falls back to OpenRouter when OpenAI fails (quota exceeded, etc.).
    Uses few-shot examples to match your existing email style.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model
        self.client = None
        self._cost_total = 0.0
        self._emails_generated = 0

        # OpenRouter fallback config
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
        self.fallback_client = None
        self._using_fallback = False

        if not self.api_key and not self.openrouter_key:
            raise ValueError(
                "No AI API key set!\n"
                "  Set OPENAI_API_KEY or OPENROUTER_API_KEY in .env"
            )

        try:
            from openai import OpenAI
            if self.api_key:
                self.client = OpenAI(api_key=self.api_key)
                logger.info(f"OpenAI client initialized (model: {self.model})")
            if self.openrouter_key:
                self.fallback_client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=self.openrouter_key,
                )
                logger.info(f"OpenRouter fallback ready (model: {self.openrouter_model})")
            # If no OpenAI key but we have OpenRouter, use it as primary
            if not self.client and self.fallback_client:
                self.client = self.fallback_client
                self.model = self.openrouter_model
                self._using_fallback = True
                logger.info("Using OpenRouter as primary provider")
        except ImportError:
            raise ImportError(
                "OpenAI package not installed!\n"
                "  Run: pip install openai"
            )

    def _build_system_prompt(self) -> str:
        """Build the system prompt with profile and style instructions."""
        examples_text = ""
        for i, ex in enumerate(EXAMPLE_EMAILS, 1):
            examples_text += f"""
--- Exemple {i} ---
Entreprise: {ex['company']}
Poste: {ex['position']}
Ville: {ex.get('city', '—')}
Pertinence: {'⭐' * ex['relevance']}

Subject: {ex['subject']}

{ex['body']}
"""

        return f"""Tu es un assistant qui génère des emails de candidature spontanée professionnels en français.

Tu génères des emails pour le candidat décrit dans le profil ci-dessous.

PROFIL DU CANDIDAT:
{SENDER_PROFILE}

RÈGLES STRICTES:
1. L'email doit être en FRANÇAIS
2. Ton professionnel mais pas formel — direct et concis
3. Personnalise CHAQUE email en fonction du poste et de l'entreprise
4. Mentionne UNIQUEMENT les compétences pertinentes pour le poste
5. Si le poste ne correspond pas directement au profil, explique poliment quel autre besoin tu pourrais combler
6. Pour les ⭐⭐⭐ (très pertinent): email détaillé avec compétences listées, projets, stage
7. Pour les ⭐⭐ (pertinent): email moyen, compétences clés + un projet
8. Pour les ⭐ (moins pertinent): email court, candidature spontanée
9. Toujours terminer avec les liens (Portfolio, GitHub, LinkedIn) et coordonnées
10. La signature doit utiliser le nom et les coordonnées du profil candidat
11. NE PAS inventer de compétences qui ne sont pas dans le profil
12. NE PAS mentionner de numéro d'offre inventé
13. Le sujet doit suivre le format: "Candidature — [Poste adapté] | {SENDER_NAME}"

EXEMPLES DE TON STYLE (à imiter):
{examples_text}

Réponds EXACTEMENT au format JSON:
{{"subject": "...", "body": "..."}}

Le body ne doit PAS inclure la ligne Subject. Juste le contenu de l'email à partir de "Bonjour".
"""

    def _call_api(self, client, model: str, user_prompt: str, provider: str = "OpenAI"):
        """Call an OpenAI-compatible API and return (subject, body)."""
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": user_prompt},
        ]

        kwargs = dict(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=1200,
        )
        # response_format may not be supported by all OpenRouter models
        if provider == "OpenAI":
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        raw = response.choices[0].message.content

        # Try JSON parse
        try:
            data = json.loads(raw)
            subject = data.get('subject', '')
            body = data.get('body', '')
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code block
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
                subject = data.get('subject', '')
                body = data.get('body', '')
            else:
                subject, body = self._fallback_parse(raw, '', '')

        # Track usage
        self._emails_generated += 1
        if response.usage:
            tokens = response.usage.total_tokens
            estimated_cost = tokens * 0.0003 / 1000
            self._cost_total += estimated_cost
            logger.info(
                f"[{provider}] Generated email "
                f"({tokens} tokens, ~${estimated_cost:.4f})"
            )

        return subject, body

    def generate_email(self, company: str, position: str, email: str,
                       city: str = '', relevance: int = 2,
                       job_description: str = '') -> Tuple[str, str]:
        """
        Generate a personalized email subject and body.
        Tries OpenAI first, falls back to OpenRouter on failure.

        Returns:
            Tuple of (subject, body)
        """
        stars = '⭐' * relevance

        user_prompt = f"""Génère un email de candidature pour:
- Entreprise: {company or '—'}
- Poste: {position or '—'}
- Email du contact: {email}
- Ville: {city or '—'}
- Pertinence: {stars}"""

        if job_description:
            user_prompt += f"\n- Description du poste: {job_description[:500]}"

        user_prompt += "\n\nRéponds UNIQUEMENT en JSON: {\"subject\": \"...\", \"body\": \"...\"}"

        # Try primary provider
        try:
            subject, body = self._call_api(
                self.client, self.model, user_prompt,
                provider="OpenRouter" if self._using_fallback else "OpenAI"
            )
            if not subject:
                subject = f"Candidature — {position} | {SENDER_NAME}"
            return subject, body

        except Exception as primary_err:
            # If we have a fallback and aren't already using it, try it
            if self.fallback_client and not self._using_fallback:
                logger.warning(
                    f"OpenAI failed ({type(primary_err).__name__}), "
                    f"switching to OpenRouter ({self.openrouter_model})..."
                )
                try:
                    subject, body = self._call_api(
                        self.fallback_client, self.openrouter_model, user_prompt,
                        provider="OpenRouter"
                    )
                    if not subject:
                        subject = f"Candidature — {position} | {SENDER_NAME}"
                    return subject, body
                except Exception as fallback_err:
                    logger.error(f"OpenRouter also failed: {fallback_err}")
                    raise fallback_err

            logger.error(f"API error for {email}: {primary_err}")
            raise

    def _fallback_parse(self, raw: str, company: str, position: str) -> Tuple[str, str]:
        """Try to extract subject/body from non-JSON GPT response."""
        subject = f"Candidature — {position} | {SENDER_NAME}"
        body = raw.strip()

        # Try to find subject line in text
        subj_match = re.search(r'[Ss]ubject[:\s]*(.+)', raw)
        if subj_match:
            subject = subj_match.group(1).strip().strip('"')
            # Remove subject line from body
            body = raw[subj_match.end():].strip()

        return subject, body

    def generate_batch(self, contacts: list, delay: float = 1.0) -> list:
        """
        Generate emails for a batch of contacts.

        Args:
            contacts: List of dicts with keys: company, position, email, city, relevance
            delay:    Seconds between API calls (rate limiting)

        Returns:
            List of dicts with keys: email, subject, body, success
        """
        results = []
        total = len(contacts)

        for i, contact in enumerate(contacts, 1):
            print(f"  🤖 [{i}/{total}] Generating email for {contact.get('email', '?')}...",
                  end=' ', flush=True)

            try:
                subject, body = self.generate_email(
                    company=contact.get('company', ''),
                    position=contact.get('position', ''),
                    email=contact.get('email', ''),
                    city=contact.get('city', ''),
                    relevance=contact.get('relevance', 2),
                    job_description=contact.get('job_description', ''),
                )
                results.append({
                    'email': contact['email'],
                    'company': contact.get('company', ''),
                    'subject': subject,
                    'body': body,
                    'success': True,
                })
                print("✅")
            except Exception as e:
                results.append({
                    'email': contact['email'],
                    'company': contact.get('company', ''),
                    'subject': '',
                    'body': '',
                    'success': False,
                    'error': str(e),
                })
                print(f"❌ {e}")

            # Rate limit between calls
            if i < total:
                time.sleep(delay)

        return results

    def print_stats(self):
        """Print generation statistics."""
        print(f"\n  📊 AI Generation Stats:")
        print(f"     Emails generated: {self._emails_generated}")
        print(f"     Estimated cost:   ~${self._cost_total:.4f}")
        print(f"     Model:            {self.model}")


# ═══════════════════════════════════════════════════════════
#  Integration with emails_prospection.md
# ═══════════════════════════════════════════════════════════

def generate_emails_for_contacts(
    contacts_file: str,
    min_stars: int = 1,
    limit: int = 0,
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
) -> int:
    """
    Generate email bodies for contacts in emails_prospection.md
    that don't have custom email sections yet.

    Args:
        contacts_file: Path to emails_prospection.md
        min_stars:     Minimum relevance (1-3)
        limit:         Max emails to generate (0 = no limit)
        api_key:       OpenAI API key (or use OPENAI_API_KEY env var)
        model:         OpenAI model to use

    Returns:
        Number of emails generated
    """
    from email_campaign.parse_contacts import EmailProspectionParser

    print(f"\n{'='*60}")
    print(f"  🤖 AI EMAIL GENERATOR (OpenAI {model})")
    print(f"{'='*60}")

    # Parse contacts
    parser = EmailProspectionParser(contacts_file)
    result = parser.parse()

    # Find contacts WITHOUT custom email body
    needs_email = [
        c for c in result.contacts
        if not c.has_custom_email
        and c.relevance >= min_stars
        and c.email
        and '@' in c.email
    ]

    if limit > 0:
        needs_email = needs_email[:limit]

    if not needs_email:
        print(f"\n  ✅ All contacts already have email templates!")
        print(f"     (or none match min-stars={min_stars})")
        print(f"{'='*60}\n")
        return 0

    print(f"  📋 Contacts needing emails: {len(needs_email)}")
    print(f"  ⭐ Min relevance: {min_stars} star(s)")
    if limit > 0:
        print(f"  🔢 Limit: {limit}")
    print()

    # Show preview
    for c in needs_email[:5]:
        stars = '⭐' * c.relevance
        print(f"    {stars} {c.company:<25} {c.email}")
    if len(needs_email) > 5:
        print(f"    ... and {len(needs_email) - 5} more")
    print()

    # Initialize generator
    try:
        generator = AIEmailGenerator(api_key=api_key, model=model)
    except (ValueError, ImportError) as e:
        print(f"\n  ❌ {e}")
        return 0

    # Generate emails
    contact_dicts = [
        {
            'company': c.company,
            'position': c.position,
            'email': c.email,
            'city': c.city,
            'relevance': c.relevance,
        }
        for c in needs_email
    ]

    results = generator.generate_batch(contact_dicts, delay=1.5)

    # Write generated emails to the markdown file
    successful = [r for r in results if r['success'] and r['body']]

    if successful:
        _append_email_sections(contacts_file, needs_email, successful)

    # Print summary
    failed = [r for r in results if not r['success']]
    generator.print_stats()

    print(f"\n{'='*60}")
    print(f"  📧 GENERATION RESULTS")
    print(f"{'='*60}")
    print(f"  ✅ Generated:  {len(successful)} emails")
    print(f"  ❌ Failed:     {len(failed)}")
    if failed:
        for f in failed[:5]:
            print(f"     • {f['email']}: {f.get('error', '?')}")
    print(f"{'='*60}\n")

    return len(successful)


def _append_email_sections(contacts_file: str, contacts: list, results: list):
    """
    Append generated email sections to the markdown file in the
    exact format that parse_contacts.py expects:

    ### N. Company — email@domain.com
    **To:** email@domain.com
    **Subject:** Subject line
    Body text...
    ---
    """
    filepath = Path(contacts_file)
    content = filepath.read_text(encoding='utf-8')

    # Build a map from email to result
    result_map = {r['email'].lower(): r for r in results}

    # Build new sections
    new_sections = []
    for contact in contacts:
        result = result_map.get(contact.email.lower())
        if not result or not result['success']:
            continue

        section = f"""

---

### {contact.index}. {contact.company} — {contact.email}

**To:** {contact.email}
**Subject:** {result['subject']}

{result['body']}"""

        new_sections.append(section)

    if new_sections:
        # Append all sections at the end of the file
        content = content.rstrip()
        content += '\n' + '\n'.join(new_sections) + '\n\n---\n'
        filepath.write_text(content, encoding='utf-8')
        logger.info(f"Appended {len(new_sections)} email sections to {contacts_file}")
        print(f"\n  📝 Appended {len(new_sections)} email sections to the file")
