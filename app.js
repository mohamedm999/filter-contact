/* ========================================
   Contact Filter — Application Logic
   ======================================== */

// ---- State ----
let extractedContacts = [];
let currentLang = 'fr';

// ---- Profile Data ----
const PROFILE = {
    name: 'Mohamed Moukhtari',
    brand: 'M2Dev',
    phone: '+212 772 841 600',
    email: 'moukhtari.mohamed.dev@gmail.com',
    portfolio: 'https://code-folio-portfolio-personnel-fron.vercel.app/',
    github: 'https://github.com/mohamedm999',
    linkedin: 'https://www.linkedin.com/in/mohamed-moukhtari-197a53338/',
    skills: {
        frontend: 'ReactJS, JavaScript (ES6+), TypeScript, HTML5, CSS3, Bootstrap, TailwindCSS, UI/UX',
        backend: 'NodeJS, ExpressJS, NestJS, PHP, Laravel, REST APIs, GraphQL, NextJS',
        databases: 'PostgreSQL, MySQL, MongoDB, Mongoose, Sequelize, Prisma',
        testing: 'Jest, Mocha, Chai, E2E, Unit testing, Postman',
        devops: 'CI/CD, GitHub Actions, Docker, Jenkins',
        tools: 'Git, GitHub, GitLab, Figma, Agile/Scrum, Jira, Trello'
    },
    education: 'YouCode - UM6P (Full Stack JavaScript)',
    experience: 'Stage Développeur Full Stack — OCP Maintenance Solutions (OMS)',
    projects: [
        { name: 'MyArtisan', desc: 'Plateforme de mise en relation Artisan/Client (Laravel, TailwindCSS, PostgreSQL)' },
        { name: 'YouShop', desc: 'Plateforme E-commerce avec architecture modulaire (NestJS, React, Prisma, Docker)' },
        { name: 'Youdemy', desc: 'Plateforme E-learning (PHP, MySQL, TailwindCSS)' },
        { name: 'DataCollect-Inc', desc: 'Application web de collecte de données' }
    ]
};

// ---- Email Templates ----
function getEmailTemplate(contact, lang) {
    const companyName = contact.company || contact.domain;

    if (lang === 'fr') {
        return {
            subject: `Candidature spontanée — Développeur Web Full Stack | ${PROFILE.name}`,
            body: `Bonjour,

Je me permets de vous contacter car je suis vivement intéressé par les activités de ${companyName} et je souhaite vous proposer mes compétences en tant que Développeur Web Full Stack JavaScript & PHP.

Je m'appelle ${PROFILE.name}, développeur passionné et polyvalent, actuellement en formation à YouCode — UM6P. J'ai également effectué un stage en développement Full Stack chez OCP Maintenance Solutions (OMS), où j'ai contribué au développement d'une plateforme de gestion des accès avec Laravel et Vue.js.

Mes compétences techniques couvrent :
• Frontend : ${PROFILE.skills.frontend}
• Backend : ${PROFILE.skills.backend}
• Bases de données : ${PROFILE.skills.databases}
• Testing : ${PROFILE.skills.testing}
• DevOps : ${PROFILE.skills.devops}
• Outils : ${PROFILE.skills.tools}

Parmi mes projets réalisés :
${PROFILE.projects.map(p => `• ${p.name} — ${p.desc}`).join('\n')}

Je suis convaincu que mon profil polyvalent et ma motivation pourraient apporter une vraie valeur ajoutée à vos projets. Je serais ravi d'échanger avec vous pour discuter de la manière dont je pourrais contribuer au succès de ${companyName}.

N'hésitez pas à consulter mon portfolio et mes travaux :
🌐 Portfolio : ${PROFILE.portfolio}
💻 GitHub : ${PROFILE.github}
🔗 LinkedIn : ${PROFILE.linkedin}

Je reste à votre disposition pour un entretien à votre convenance.

Cordialement,
${PROFILE.name}
📞 ${PROFILE.phone}
📧 ${PROFILE.email}`
        };
    } else {
        return {
            subject: `Spontaneous Application — Full Stack Web Developer | ${PROFILE.name}`,
            body: `Dear Hiring Manager,

I am reaching out to express my strong interest in ${companyName} and to offer my skills as a Full Stack Web Developer specializing in JavaScript & PHP.

My name is ${PROFILE.name}, a passionate and versatile developer currently training at YouCode — UM6P (Morocco). I also completed an internship as a Full Stack Developer at OCP Maintenance Solutions (OMS), where I contributed to building an access management platform using Laravel and Vue.js.

My technical skills include:
• Frontend: ${PROFILE.skills.frontend}
• Backend: ${PROFILE.skills.backend}
• Databases: ${PROFILE.skills.databases}
• Testing: ${PROFILE.skills.testing}
• DevOps: ${PROFILE.skills.devops}
• Tools: ${PROFILE.skills.tools}

Some of my key projects:
${PROFILE.projects.map(p => `• ${p.name} — ${p.desc}`).join('\n')}

I believe my versatile skill set and strong motivation could bring real value to your team and projects. I would be delighted to discuss how I can contribute to the success of ${companyName}.

Feel free to explore my portfolio and work:
🌐 Portfolio: ${PROFILE.portfolio}
💻 GitHub: ${PROFILE.github}
🔗 LinkedIn: ${PROFILE.linkedin}

I am available for an interview at your convenience.

Best regards,
${PROFILE.name}
📞 ${PROFILE.phone}
📧 ${PROFILE.email}`
        };
    }
}

// ---- Extraction Logic ----
function extractEmails(text) {
    const emailRegex = /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g;
    const matches = text.match(emailRegex) || [];
    // Deduplicate and remove own email
    const unique = [...new Set(matches.map(e => e.toLowerCase()))];
    return unique.filter(e => e !== PROFILE.email.toLowerCase());
}

function inferCompanyFromEmail(email) {
    const domain = email.split('@')[1];
    if (!domain) return { company: '', domain: '' };

    const domainName = domain.split('.')[0];
    // Common generic domains
    const generic = ['gmail', 'yahoo', 'hotmail', 'outlook', 'live', 'aol', 'icloud', 'protonmail', 'mail', 'yandex', 'zoho', 'gmx'];
    
    if (generic.includes(domainName.toLowerCase())) {
        return { company: '(Personnel)', domain: domain };
    }

    // Capitalize and clean company name
    const company = domainName
        .replace(/[-_]/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase());

    return { company, domain };
}

// ---- Main Functions ----
function extractContacts() {
    const text = document.getElementById('rawTextInput').value.trim();
    if (!text) {
        showToast('⚠️ Veuillez coller du texte d\'abord !');
        return;
    }

    const emails = extractEmails(text);
    if (emails.length === 0) {
        showToast('❌ Aucun email trouvé dans le texte.');
        return;
    }

    extractedContacts = emails.map(email => {
        const { company, domain } = inferCompanyFromEmail(email);
        return { email, company, domain, selected: true };
    });

    renderContactsTable();
    document.getElementById('step-contacts').classList.remove('hidden');
    document.getElementById('contactCount').textContent = extractedContacts.length;
    document.getElementById('selectAll').checked = true;

    // Hide emails section if previously shown
    document.getElementById('step-emails').classList.add('hidden');

    // Smooth scroll
    document.getElementById('step-contacts').scrollIntoView({ behavior: 'smooth', block: 'start' });

    showToast(`✅ ${extractedContacts.length} contact(s) extrait(s) !`);
}

function renderContactsTable() {
    const tbody = document.getElementById('contactsBody');
    tbody.innerHTML = extractedContacts.map((c, i) => `
        <tr>
            <td>
                <label class="checkbox-label">
                    <input type="checkbox" ${c.selected ? 'checked' : ''} onchange="toggleContact(${i})">
                    <span class="custom-checkbox"></span>
                </label>
            </td>
            <td class="email-cell">${escapeHtml(c.email)}</td>
            <td class="company-cell">${escapeHtml(c.company)}</td>
            <td class="domain-cell">${escapeHtml(c.domain)}</td>
        </tr>
    `).join('');
}

function toggleContact(index) {
    extractedContacts[index].selected = !extractedContacts[index].selected;
    updateSelectAll();
}

function toggleSelectAll() {
    const checked = document.getElementById('selectAll').checked;
    extractedContacts.forEach(c => c.selected = checked);
    renderContactsTable();
}

function updateSelectAll() {
    const allSelected = extractedContacts.every(c => c.selected);
    document.getElementById('selectAll').checked = allSelected;
}

function setLang(lang) {
    currentLang = lang;
    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.lang === lang);
    });
}

// ---- Email Generation ----
function generateEmails() {
    const selected = extractedContacts.filter(c => c.selected);
    if (selected.length === 0) {
        showToast('⚠️ Sélectionnez au moins un contact.');
        return;
    }

    const container = document.getElementById('emailsContainer');
    container.innerHTML = selected.map((contact, i) => {
        const tpl = getEmailTemplate(contact, currentLang);
        return `
            <div class="email-card" style="animation-delay: ${i * 0.08}s">
                <div class="email-card-header">
                    <span class="email-recipient">📧 ${escapeHtml(contact.email)}</span>
                    <span class="email-company-tag">${escapeHtml(contact.company)}</span>
                </div>
                <div class="email-card-body">
                    <div class="email-field">
                        <div class="email-field-label">Destinataire (To)</div>
                        <div class="email-field-value">${escapeHtml(contact.email)}</div>
                    </div>
                    <div class="email-field">
                        <div class="email-field-label">Objet (Subject)</div>
                        <div class="email-field-value">${escapeHtml(tpl.subject)}</div>
                    </div>
                    <div class="email-field">
                        <div class="email-field-label">Corps (Body)</div>
                        <div class="email-field-value">${escapeHtml(tpl.body)}</div>
                    </div>
                </div>
                <div class="email-card-actions">
                    <button class="btn btn-secondary btn-sm" onclick="copyEmail(${i})">
                        <span class="btn-icon">📋</span> Copier
                    </button>
                    <button class="btn btn-secondary btn-sm" onclick="openMailto(${i})">
                        <span class="btn-icon">📨</span> Ouvrir dans Mail
                    </button>
                </div>
            </div>
        `;
    }).join('');

    document.getElementById('step-emails').classList.remove('hidden');
    document.getElementById('emailCount').textContent = selected.length;
    document.getElementById('step-emails').scrollIntoView({ behavior: 'smooth', block: 'start' });

    showToast(`✨ ${selected.length} email(s) généré(s) !`);
}

function copyEmail(index) {
    const selected = extractedContacts.filter(c => c.selected);
    const contact = selected[index];
    const tpl = getEmailTemplate(contact, currentLang);
    const text = `To: ${contact.email}\nSubject: ${tpl.subject}\n\n${tpl.body}`;
    navigator.clipboard.writeText(text).then(() => {
        showToast('✅ Email copié dans le presse-papiers !');
    });
}

function openMailto(index) {
    const selected = extractedContacts.filter(c => c.selected);
    const contact = selected[index];
    const tpl = getEmailTemplate(contact, currentLang);
    const mailto = `mailto:${encodeURIComponent(contact.email)}?subject=${encodeURIComponent(tpl.subject)}&body=${encodeURIComponent(tpl.body)}`;
    window.open(mailto, '_blank');
}

function copyAllEmails() {
    const selected = extractedContacts.filter(c => c.selected);
    if (selected.length === 0) return;

    const allText = selected.map(contact => {
        const tpl = getEmailTemplate(contact, currentLang);
        return `═══════════════════════════════════════\nTo: ${contact.email}\nCompany: ${contact.company}\nSubject: ${tpl.subject}\n\n${tpl.body}`;
    }).join('\n\n');

    navigator.clipboard.writeText(allText).then(() => {
        showToast(`✅ ${selected.length} email(s) copié(s) !`);
    });
}

// ---- Export ----
function exportCSV() {
    if (extractedContacts.length === 0) return;
    const rows = [['Email', 'Entreprise', 'Domaine']];
    extractedContacts.forEach(c => {
        rows.push([c.email, c.company, c.domain]);
    });
    downloadCSV(rows, 'contacts_extraits.csv');
    showToast('📥 Fichier CSV téléchargé !');
}

function exportAllEmails() {
    const selected = extractedContacts.filter(c => c.selected);
    if (selected.length === 0) return;

    const rows = [['Email', 'Entreprise', 'Objet', 'Corps']];
    selected.forEach(contact => {
        const tpl = getEmailTemplate(contact, currentLang);
        rows.push([contact.email, contact.company, tpl.subject, tpl.body.replace(/\n/g, '\\n')]);
    });
    downloadCSV(rows, 'emails_prospection.csv');
    showToast('📥 Fichier CSV téléchargé !');
}

function downloadCSV(rows, filename) {
    const csvContent = rows.map(row =>
        row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')
    ).join('\n');

    const BOM = '\uFEFF'; // UTF-8 BOM for Excel
    const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

// ---- Utilities ----
function clearInput() {
    document.getElementById('rawTextInput').value = '';
    extractedContacts = [];
    document.getElementById('step-contacts').classList.add('hidden');
    document.getElementById('step-emails').classList.add('hidden');
    showToast('🗑 Nettoyé !');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message) {
    const toast = document.getElementById('toast');
    document.getElementById('toastMsg').textContent = message;
    toast.classList.remove('hidden');
    toast.classList.add('show');
    clearTimeout(window._toastTimeout);
    window._toastTimeout = setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.classList.add('hidden'), 300);
    }, 2500);
}

// ---- Keyboard Shortcuts ----
document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'Enter') {
        const step2 = document.getElementById('step-contacts');
        if (step2.classList.contains('hidden')) {
            extractContacts();
        } else {
            generateEmails();
        }
    }
});
