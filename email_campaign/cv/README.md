# CV / Resume Files

Place your CV files here:

- `cv_fr.pdf` — French version
- `cv_en.pdf` — English version

The system will **auto-select** the correct CV based on the detected language of each contact:
- French company (`.ma`, `.fr`, SARL, etc.) → `cv_fr.pdf`
- English company (`.io`, `.com`, Ltd, Inc, etc.) → `cv_en.pdf`

## Setup

In your `.env` file, set:
```
CV_PATH_FR=email_campaign/cv/cv_fr.pdf
CV_PATH_EN=email_campaign/cv/cv_en.pdf
ATTACH_CV=true
```

Or use the CLI flag: `python main.py --send --attach-cv`

If only one language CV is available, it will be used as fallback for all contacts.
