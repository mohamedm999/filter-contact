"""
Quick test: Preview the professional HTML email output.
Generates an HTML file you can open in a browser to see the result.

Usage:
    cd email_campaign
    python test_email_preview.py
"""

import sys
import os
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_config
from email_sender import EmailSender
from tracker import SentTracker
from parse_contacts import Contact


def main():
    config = load_config()
    config.dry_run = True

    tracker = SentTracker(config.paths.sent_tracker_file, config.paths.failed_file)
    sender = EmailSender(config, tracker)

    # Create a fake contact to test with
    test_contact = Contact(
        index=999,
        company="TestCorp Maroc",
        email="recrutement@testcorp.ma",
        position="Développeur Full Stack",
        city="Casablanca",
        relevance=3,
        has_custom_email=True,
        subject="Candidature — Développeur Full Stack | Mohamed Moukhtari",
        body=(
            "Madame, Monsieur,\n\n"
            "Je me permets de vous contacter suite à votre offre de Développeur Full Stack "
            "chez TestCorp Maroc à Casablanca.\n\n"
            "Je m'appelle Mohamed Moukhtari, développeur Web Full Stack JavaScript & PHP, "
            "actuellement en formation à YouCode — UM6P. J'ai effectué un stage chez "
            "OCP Maintenance Solutions (OMS) en développement Full Stack (Laravel, Vue.js).\n\n"
            "Mes compétences techniques :\n"
            "• Frontend : ReactJS, JavaScript (ES6+), TypeScript, TailwindCSS\n"
            "• Backend : NodeJS, NestJS, PHP, Laravel, REST APIs\n"
            "• Bases de données : PostgreSQL, MySQL, MongoDB\n"
            "• DevOps : Docker, CI/CD, GitHub Actions\n\n"
            "Projets clés :\n"
            "• MyArtisan — Plateforme Artisan/Client (Laravel, TailwindCSS, PostgreSQL)\n"
            "• YouShop — E-commerce modulaire (NestJS, React, Prisma, Docker)\n\n"
            "Je serais ravi de pouvoir échanger avec vous sur ma candidature et sur la "
            "manière dont je pourrais contribuer à vos projets.\n\n"
            "Cordialement,"
        ),
    )

    # Build the MIME message
    msg = sender._build_message(test_contact)

    # Extract HTML and plain-text parts
    html_content = None
    plain_content = None
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "text/html":
            html_content = part.get_payload(decode=True).decode("utf-8")
        elif ct == "text/plain":
            plain_content = part.get_payload(decode=True).decode("utf-8")

    # Save HTML preview
    preview_path = Path(__file__).parent / "logs" / "email_preview.html"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    if html_content:
        preview_path.write_text(html_content, encoding="utf-8")
        print(f"\n✅ HTML preview saved: {preview_path}")
    else:
        print("\n⚠️  No HTML content generated (send_as_html may be False)")

    # Show plain-text version
    print(f"\n{'='*60}")
    print("  📧 PLAIN-TEXT VERSION")
    print(f"{'='*60}")
    print(f"  From:    {msg['From']}")
    print(f"  To:      {msg['To']}")
    print(f"  Subject: {msg['Subject']}")
    print(f"{'='*60}")
    if plain_content:
        print(plain_content)
    print(f"{'='*60}")

    # Summary
    print(f"\n📋 Email Structure:")
    print(f"   Content-Type: multipart/alternative")
    print(f"   Parts: {len(list(msg.walk())) - 1}")
    for part in msg.walk():
        ct = part.get_content_type()
        if ct != "multipart/alternative":
            print(f"     → {ct}")
    print(f"   Headers: From, To, Subject, Reply-To, Date, Message-ID, "
          f"List-Unsubscribe, X-Priority, X-Mailer")
    if html_content:
        print(f"\n🌐 Open the HTML preview in your browser:")
        print(f"   {preview_path.resolve()}")


if __name__ == "__main__":
    main()
