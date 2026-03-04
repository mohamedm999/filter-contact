"""
══════════════════════════════════════════════════════════════
  Language Detector — Auto-detect email language (FR / EN)
  Determines the optimal language for each contact based on
  email domain, company name, and job listing signals.
══════════════════════════════════════════════════════════════
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  TLD-based hints
# ═══════════════════════════════════════════════════════════

# Domains / TLDs that strongly suggest French
FRENCH_TLDS = {
    '.ma', '.fr', '.be', '.ch', '.dz', '.tn', '.sn', '.cm',
    '.ci', '.cd', '.mg', '.ml', '.bf', '.ne', '.td', '.ga',
    '.cg', '.bj', '.tg', '.rw', '.bi', '.dj', '.cf', '.gn',
    '.ht', '.lu', '.mc', '.mq', '.gp', '.re', '.nc', '.pf',
}

# Domains / TLDs that strongly suggest English
ENGLISH_TLDS = {
    '.us', '.uk', '.co.uk', '.au', '.ca', '.nz', '.ie', '.in',
    '.ph', '.ng', '.za', '.pk', '.gh', '.ke', '.sg', '.my',
    '.io', '.ai', '.dev', '.tech', '.app',
}


# ═══════════════════════════════════════════════════════════
#  Keyword-based signals
# ═══════════════════════════════════════════════════════════

# French keywords in job titles / descriptions
FR_KEYWORDS = {
    'développeur', 'developpeur', 'ingénieur', 'ingenieur',
    'stage', 'stagiaire', 'alternance', 'poste', 'emploi',
    'responsable', 'chef de projet', 'directeur', 'technicien',
    'analyste', 'concepteur', 'consultant', 'chargé',
    'administrateur', 'assistant', 'coordinateur',
    'recrutement', 'candidature', 'entretien', 'entreprise',
    'société', 'agence', 'bureau', 'service',
    'informatique', 'numérique', 'numerique',
    'web', 'logiciel', 'programmeur',
}

# English keywords in job titles / descriptions
EN_KEYWORDS = {
    'developer', 'engineer', 'intern', 'internship',
    'manager', 'director', 'analyst', 'consultant', 'specialist',
    'coordinator', 'assistant', 'administrator', 'technician',
    'designer', 'architect', 'recruiter', 'hiring',
    'software', 'digital', 'remote', 'freelance',
    'frontend', 'backend', 'fullstack', 'full-stack', 'full stack',
    'junior', 'senior', 'lead', 'head of',
    'job', 'position', 'role', 'opportunity', 'vacancy',
    'recruitment', 'interview', 'company', 'agency',
}


# ═══════════════════════════════════════════════════════════
#  Known Moroccan / French job boards
# ═══════════════════════════════════════════════════════════

FR_DOMAINS = {
    'rekrute.com', 'emploi.ma', 'marocannonces.com',
    'menarajob.com', 'anapec.org', 'aumaroc.com',
    'stagiaire.ma', 'offres-emploi.ma', 'indeed.fr',
    'monster.fr', 'pole-emploi.fr', 'apec.fr',
    'cadremploi.fr', 'hellowork.com', 'keljob.com',
}

EN_DOMAINS = {
    'bayt.com', 'linkedin.com', 'indeed.com', 'glassdoor.com',
    'monster.com', 'dice.com', 'stackoverflow.com',
    'angel.co', 'wellfound.com', 'hired.com',
    'remoteok.com', 'remote.co', 'weworkremotely.com',
}


# ═══════════════════════════════════════════════════════════
#  Detector
# ═══════════════════════════════════════════════════════════

class LanguageDetector:
    """
    Detects whether an email should be written in French or English
    based on multiple signals: domain TLD, company name, position title,
    city, and optional job description text.

    Scoring:
      - Each signal contributes a weighted score to FR vs EN
      - Default fallback is French (Moroccan market)
    """

    def __init__(self, default_lang: str = "fr"):
        """
        Args:
            default_lang: Fallback language when signals are ambiguous.
                         'fr' for French, 'en' for English.
        """
        self.default_lang = default_lang

    def detect(
        self,
        email: str = "",
        company: str = "",
        position: str = "",
        city: str = "",
        job_description: str = "",
        source_site: str = "",
    ) -> str:
        """
        Detect the best language for an email.

        Returns:
            'fr' for French, 'en' for English.
        """
        score_fr = 0.0
        score_en = 0.0

        # ── 1. Email domain TLD ──
        if email and '@' in email:
            domain = email.split('@')[1].lower()
            tld_score = self._score_tld(domain)
            score_fr += tld_score['fr']
            score_en += tld_score['en']

            # Known job board domains
            for fr_dom in FR_DOMAINS:
                if fr_dom in domain:
                    score_fr += 2.0
                    break
            for en_dom in EN_DOMAINS:
                if en_dom in domain:
                    score_en += 2.0
                    break

        # ── 2. Source site (where the contact was scraped from) ──
        site = source_site.lower() if source_site else ""
        if site in ('rekrute', 'emploi_ma', 'maroc_annonces'):
            score_fr += 3.0
        elif site in ('bayt', 'linkedin'):
            score_en += 1.5  # LinkedIn can be either

        # ── 3. Position / job title keywords ──
        if position:
            pos_lower = position.lower()
            fr_hits = sum(1 for kw in FR_KEYWORDS if kw in pos_lower)
            en_hits = sum(1 for kw in EN_KEYWORDS if kw in pos_lower)
            score_fr += fr_hits * 1.5
            score_en += en_hits * 1.5

        # ── 4. Company name analysis ──
        if company:
            comp_lower = company.lower()
            # French company indicators
            if any(x in comp_lower for x in ['sarl', 's.a.r.l', 'eurl', 'sa ', 'sas']):
                score_fr += 2.0
            # English company indicators
            if any(x in comp_lower for x in ['ltd', 'inc', 'corp', 'llc', 'plc']):
                score_en += 2.5

        # ── 5. City (Moroccan cities → French) ──
        if city:
            moroccan_cities = {
                'casablanca', 'rabat', 'marrakech', 'fes', 'fès', 'tanger',
                'agadir', 'oujda', 'meknès', 'meknes', 'kenitra', 'kénitra',
                'tetouan', 'tétouan', 'safi', 'el jadida', 'settat', 'beni mellal',
                'nador', 'salé', 'sale', 'mohammedia', 'laayoune', 'khouribga',
            }
            if city.lower().strip() in moroccan_cities:
                score_fr += 2.0

        # ── 6. Job description text analysis ──
        if job_description:
            desc_lower = job_description.lower()
            fr_desc_hits = sum(1 for kw in FR_KEYWORDS if kw in desc_lower)
            en_desc_hits = sum(1 for kw in EN_KEYWORDS if kw in desc_lower)
            score_fr += fr_desc_hits * 0.5
            score_en += en_desc_hits * 0.5

            # French specific patterns
            if re.search(r'nous\s+recherchons|profil\s+recherché|mission|poste\s+à\s+pourvoir', desc_lower):
                score_fr += 3.0
            if re.search(r'we\s+are\s+looking|requirements?|responsibilities|about\s+the\s+role', desc_lower):
                score_en += 3.0

        # ── Decision ──
        lang = self.default_lang
        if score_fr > score_en:
            lang = 'fr'
        elif score_en > score_fr:
            lang = 'en'
        # If equal, use default (French for Moroccan market)

        logger.debug(
            f"Language detection for {email}: "
            f"FR={score_fr:.1f} EN={score_en:.1f} → {lang.upper()}"
        )
        return lang

    def _score_tld(self, domain: str) -> dict:
        """Score a domain's TLD for language hints."""
        scores = {'fr': 0.0, 'en': 0.0}
        for tld in FRENCH_TLDS:
            if domain.endswith(tld):
                scores['fr'] += 3.0
                return scores
        for tld in ENGLISH_TLDS:
            if domain.endswith(tld):
                scores['en'] += 3.0
                return scores
        # .com is neutral but slightly english-leaning
        if domain.endswith('.com'):
            scores['en'] += 0.5
        return scores

    def detect_for_contact(self, contact) -> str:
        """
        Convenience method: detect language from a Contact dataclass.

        Args:
            contact: parse_contacts.Contact instance
        """
        return self.detect(
            email=getattr(contact, 'email', ''),
            company=getattr(contact, 'company', ''),
            position=getattr(contact, 'position', ''),
            city=getattr(contact, 'city', ''),
        )
