# 🏈 One Play a Day

A clean, modern football play database featuring daily plays curated by Coach Dan Casey.

## Overview

This static site showcases football plays extracted from daily email breakdowns. Each play includes:
- Multiple camera angles (MP4 video)
- Play diagram
- Situational details (down & distance, personnel, formation)
- Play date and description

## Features

- 📱 **Responsive Design** - Works beautifully on all devices
- 🎥 **Lazy Loading** - Videos load only when scrolled into view for optimal performance
- 📄 **Pagination** - Browse plays 10 at a time
- 🎨 **Modern UI** - Clean sports analytics aesthetic
- ⚡ **Optimized Media** - MP4 videos (44% smaller than original GIFs)

## Tech Stack

- Pure HTML/CSS/JavaScript (no framework needed)
- Static site ready for Vercel deployment
- IntersectionObserver API for lazy loading
- Responsive grid layout

## Local Development

Simply open `index.html` in a browser, or serve with any static file server:

```bash
# Using Python
python -m http.server 8000

# Using Node
npx serve

# Using PHP
php -S localhost:8000
```

Then visit `http://localhost:8000`

## Media Conversion

Original GIFs were converted to MP4 for better performance:

```bash
./scripts/convert_media.sh
```

**Results:**
- Total GIF size: 57 MiB
- Total MP4 size: 32 MiB
- **Savings: 25 MiB (44%)**

## Project Structure

```
.
├── index.html          # Main gallery page
├── plays.json          # Play data
├── css/
│   └── style.css       # Styles
├── js/
│   └── app.js          # Pagination & lazy loading
├── media/
│   ├── *.mp4           # Video files
│   ├── *.png/*.jpg     # Diagrams
│   └── originals/      # Original GIF backups
└── scripts/
    └── convert_media.sh # GIF to MP4 converter
```

## Deployment

This site is designed to deploy to Vercel with zero configuration. Simply:

1. Connect the GitHub repo to Vercel
2. Deploy (no build step needed)
3. Done!

## Future Enhancements

- [ ] Move media to Cloudflare R2 for CDN delivery
- [ ] Add search/filter functionality
- [ ] Category/tag system for plays
- [ ] Export individual plays as shareable links

---

**Built by VT Sports Solutions** | Curated by Coach Dan Casey
