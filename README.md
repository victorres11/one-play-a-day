# 🏈 One Play a Day

A searchable database of daily football plays, sourced from Coach Dan Casey's "One Play a Day" email newsletter.

**Live Site:** [one-play-a-day-app.vercel.app](https://one-play-a-day-app.vercel.app)

## Overview

One Play a Day showcases curated football plays with multiple camera angles, play diagrams, and detailed breakdowns. Each play includes formation details, personnel packages, and situational context (down & distance).

## Features

- 📹 **Multi-angle video playback** — Most plays include 2-3 camera angles
- 📊 **Play diagrams** — Visual breakdown of each play
- 📋 **Play details** — Down & distance, personnel, formation
- ⚡ **Lazy-loaded videos** — Fast page loads, videos load as you scroll
- 📱 **Responsive design** — Works on desktop and mobile

## Tech Stack

- **Frontend:** Vanilla HTML/CSS/JS (no framework needed)
- **Hosting:** Vercel
- **Media CDN:** Cloudflare R2
- **Data:** Static JSON (`plays.json`)
- **Source:** Gmail API (Coach Dan Casey's newsletter)

## Data Pipeline

```
Gmail (One Play a Day emails)
    ↓
extract_plays.py (parse HTML, extract media URLs)
    ↓
Download GIFs → Convert to MP4 (ffmpeg)
    ↓
Upload to Cloudflare R2
    ↓
Update plays.json
    ↓
Deploy to Vercel
```

### Running the Extraction Script

```bash
# Activate virtual environment
cd ~/clawd && source venv/bin/activate

# Full extraction from Gmail (new emails)
cd one-play-a-day-app
python scripts/extract_plays.py --max 50

# Upload local media files to R2 (for backfills)
python scripts/extract_plays.py --upload-local --batch 50

# Refresh titles/details from emails
python scripts/extract_plays.py --refresh-details
```

## Data Schema

Each play in `plays.json`:

```json
{
  "play_number": 738,
  "date": "2026-01-28",
  "title": "Lions PA Deep Shot - 2025 Week 12",
  "angles": [
    "https://pub-xxx.r2.dev/media/738_angle1.mp4",
    "https://pub-xxx.r2.dev/media/738_angle2.mp4"
  ],
  "play_details": {
    "down_and_distance": "2nd & 10",
    "personnel": "11p",
    "formation": "Dual Rt"
  },
  "play_diagram": "https://pub-xxx.r2.dev/media/738_diagram.jpg"
}
```

## Local Development

```bash
# Serve locally (any static server works)
npx serve .

# Or use Python
python -m http.server 8000
```

Visit `http://localhost:8000`

## Deployment

```bash
# Deploy to Vercel
vercel --prod --yes
```

## Roadmap

See [BACKLOG.md](BACKLOG.md) for planned features:

- 🏷️ **Tagging system** — Play types, formations, play callers
- 🔍 **Filters & search** — Find plays by tag, team, situation
- 📈 **Coach profiles** — Link plays to coordinators and their schemes
- 🌲 **Coaching trees** — Track coaching lineages and influences

## Credits

- **Play Source:** [Coach Dan Casey](https://coachdancasey.com) — One Play a Day newsletter
- **Built by:** [VT Sports Solutions](https://vtsportssolutions.com)

---

*Data is sourced from publicly available newsletter content for educational purposes.*
