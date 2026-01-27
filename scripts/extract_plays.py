#!/usr/bin/env python3
"""
One Play a Day - Email Extraction Script
Extracts play data from Gmail and populates plays.json
"""

import json
import subprocess
import sys
import re
import os
from pathlib import Path
from datetime import datetime
import argparse
import logging
from urllib.parse import urlparse
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
SCRIPT_DIR = Path(__file__).parent
APP_DIR = SCRIPT_DIR.parent
MEDIA_DIR = APP_DIR / "media"
ORIGINALS_DIR = MEDIA_DIR / "originals"
PLAYS_JSON = APP_DIR / "plays.json"
VENV_PYTHON = Path.home() / "clawd" / "venv" / "bin" / "python"

# Ensure directories exist
MEDIA_DIR.mkdir(exist_ok=True)
ORIGINALS_DIR.mkdir(exist_ok=True)


def run_gog_command(args):
    """Run a gog command and return output"""
    cmd = ["gog"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=True,
            cwd=Path.home() / "clawd"
        )
        # Handle encoding errors by using 'replace' mode
        output = result.stdout.decode('utf-8', errors='replace')
        return output
    except subprocess.CalledProcessError as e:
        logger.error(f"gog command failed: {' '.join(cmd)}")
        try:
            error_msg = e.stderr.decode('utf-8', errors='replace')
            logger.error(f"Error: {error_msg}")
        except:
            pass
        return None


def search_emails(max_results=50):
    """Search for One Play a Day emails"""
    logger.info(f"Searching for up to {max_results} One Play a Day emails...")
    
    output = run_gog_command([
        "gmail", "search",
        "from:dan@coachdancasey.com subject:'One Play a Day'",
        "--max", str(max_results),
        "--json"
    ])
    
    if not output:
        return []
    
    try:
        data = json.loads(output)
        # gog returns "threads" not "messages"
        emails = data.get("threads", []) or data.get("messages", [])
        logger.info(f"Found {len(emails)} emails")
        return emails
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse search results: {e}")
        return []


def get_email_content(email_id):
    """Fetch full email content"""
    logger.info(f"Fetching email {email_id}...")
    return run_gog_command(["gmail", "get", email_id])


def extract_play_number(subject):
    """Extract play number from subject line"""
    # Format: "One Play a Day #737 - ..." or "One Play a Day - 737"
    match = re.search(r'(?:#|-)?\s*(\d+)', subject)
    if match:
        return int(match.group(1))
    return None


def extract_email_date(html):
    """Extract date from email headers or content"""
    # Try to find Date header in the HTML
    date_match = re.search(r'Date:\s*([^\n]+)', html)
    if date_match:
        try:
            date_str = date_match.group(1).strip()
            # Parse various date formats
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            return dt.strftime("%Y-%m-%d")
        except:
            pass
    
    # Fallback to today
    return datetime.now().strftime("%Y-%m-%d")


def extract_title(html):
    """Extract play title from email content"""
    # Look for bold text that's likely the title
    # Usually after "This week's play:" or similar
    
    # Try to find content between specific patterns
    patterns = [
        r'<b[^>]*>(.*?2025.*?)</b>',  # Bold text with year
        r'<strong[^>]*>(.*?2025.*?)</strong>',
        r'<b[^>]*>(.*?2024.*?)</b>',
        r'<strong[^>]*>(.*?2024.*?)</strong>',
        r'<b[^>]*>(.*?2023.*?)</b>',
        r'<strong[^>]*>(.*?2023.*?)</strong>',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html, re.IGNORECASE | re.DOTALL)
        if matches:
            title = matches[0]
            # Clean up HTML tags
            title = re.sub(r'<[^>]+>', '', title)
            title = title.strip()
            if len(title) > 20 and len(title) < 200:
                return title
    
    return "Untitled Play"


def extract_play_details(html):
    """Extract down & distance, personnel, formation"""
    details = {
        "down_and_distance": "",
        "personnel": "",
        "formation": ""
    }
    
    # Look for pattern like "Down & Distance: 2nd & 6"
    dd_match = re.search(r'Down\s*&\s*Distance[:\s]*([^\n<]+)', html, re.IGNORECASE)
    if dd_match:
        details["down_and_distance"] = dd_match.group(1).strip()
    
    # Personnel
    pers_match = re.search(r'Personnel[:\s]*([^\n<]+)', html, re.IGNORECASE)
    if pers_match:
        details["personnel"] = pers_match.group(1).strip()
    
    # Formation
    form_match = re.search(r'Formation[:\s]*([^\n<]+)', html, re.IGNORECASE)
    if form_match:
        details["formation"] = form_match.group(1).strip()
    
    return details


def extract_media_urls(html):
    """Extract GIF and diagram URLs from email"""
    # Find all image URLs
    all_images = re.findall(r'https://[^"\s]+\.(?:gif|jpg|jpeg|png)', html, re.IGNORECASE)
    
    # Filter out header/logo images
    filtered = [
        url for url in all_images 
        if "Email-Header" not in url and "TeamWorks" not in url
    ]
    
    # Split before the divider if present
    divider_pos = html.find('fd-divider')
    if divider_pos > 0:
        html_before_divider = html[:divider_pos]
        filtered = re.findall(r'https://[^"\s]+\.(?:gif|jpg|jpeg|png)', html_before_divider, re.IGNORECASE)
        filtered = [
            url for url in filtered 
            if "Email-Header" not in url and "TeamWorks" not in url
        ]
    
    # Separate GIFs (angles) from static images (diagram)
    gifs = [url for url in filtered if url.lower().endswith('.gif')]
    diagrams = [url for url in filtered if not url.lower().endswith('.gif')]
    
    return {
        "angles": gifs,
        "diagram": diagrams[0] if diagrams else None
    }


def download_file(url, output_path):
    """Download a file from URL"""
    try:
        subprocess.run(
            ["curl", "-s", "-L", "-o", str(output_path), url],
            check=True
        )
        logger.info(f"Downloaded {output_path.name}")
        return True
    except subprocess.CalledProcessError:
        logger.error(f"Failed to download {url}")
        return False


def convert_gif_to_mp4(gif_path, mp4_path):
    """Convert GIF to MP4 using ffmpeg"""
    try:
        subprocess.run([
            "/usr/bin/ffmpeg",
            "-i", str(gif_path),
            "-movflags", "faststart",
            "-pix_fmt", "yuv420p",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            str(mp4_path),
            "-y"
        ], check=True, capture_output=True)
        logger.info(f"Converted {gif_path.name} to {mp4_path.name}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to convert {gif_path}: {e.stderr.decode()}")
        return False


def process_media(play_number, media_urls):
    """Download and convert media files"""
    result = {
        "angles": [],
        "diagram": None
    }
    
    # Process angle GIFs
    for i, gif_url in enumerate(media_urls["angles"], start=1):
        angle_num = i
        gif_filename = f"{play_number}_angle{angle_num}.gif"
        mp4_filename = f"{play_number}_angle{angle_num}.mp4"
        
        gif_path = ORIGINALS_DIR / gif_filename
        mp4_path = MEDIA_DIR / mp4_filename
        
        # Download GIF
        if download_file(gif_url, gif_path):
            # Convert to MP4
            if convert_gif_to_mp4(gif_path, mp4_path):
                result["angles"].append(f"media/{mp4_filename}")
        
        time.sleep(0.5)  # Rate limiting
    
    # Process diagram
    if media_urls["diagram"]:
        diagram_url = media_urls["diagram"]
        ext = Path(urlparse(diagram_url).path).suffix or ".jpg"
        diagram_filename = f"{play_number}_diagram{ext}"
        diagram_path = MEDIA_DIR / diagram_filename
        
        if download_file(diagram_url, diagram_path):
            result["diagram"] = f"media/{diagram_filename}"
        
        time.sleep(0.5)
    
    return result


def load_plays_json():
    """Load existing plays.json"""
    if PLAYS_JSON.exists():
        with open(PLAYS_JSON) as f:
            return json.load(f)
    return []


def save_plays_json(plays):
    """Save plays.json"""
    # Sort by play_number descending
    plays.sort(key=lambda p: p["play_number"], reverse=True)
    
    with open(PLAYS_JSON, 'w') as f:
        json.dump(plays, f, indent=2)
    
    logger.info(f"Saved {len(plays)} plays to {PLAYS_JSON}")


def extract_play_from_email(email_id, subject):
    """Extract a single play from an email"""
    play_number = extract_play_number(subject)
    if not play_number:
        logger.warning(f"Could not extract play number from: {subject}")
        return None
    
    logger.info(f"Processing Play #{play_number}")
    
    # Get email content
    html = get_email_content(email_id)
    if not html:
        logger.error(f"Failed to fetch email content for Play #{play_number}")
        return None
    
    try:
        # Extract data
        date = extract_email_date(html)
        title = extract_title(html)
        details = extract_play_details(html)
        media_urls = extract_media_urls(html)
        
        logger.info(f"  Title: {title}")
        logger.info(f"  Found {len(media_urls['angles'])} angles")
        
        # Download and convert media
        media = process_media(play_number, media_urls)
        
        if not media["angles"]:
            logger.warning(f"No angles extracted for Play #{play_number}")
            return None
        
        # Build play object
        play = {
            "play_number": play_number,
            "date": date,
            "title": title,
            "angles": media["angles"],
            "play_details": details,
            "play_diagram": media["diagram"] or ""
        }
        
        return play
        
    except Exception as e:
        logger.error(f"Error processing Play #{play_number}: {e}", exc_info=True)
        return None


def main():
    parser = argparse.ArgumentParser(description="Extract One Play a Day emails")
    parser.add_argument("--max", type=int, default=50, help="Maximum emails to fetch")
    parser.add_argument("--dry-run", action="store_true", help="Don't save changes")
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("One Play a Day - Email Extraction")
    logger.info("=" * 60)
    
    # Load existing plays
    existing_plays = load_plays_json()
    existing_numbers = {p["play_number"] for p in existing_plays}
    logger.info(f"Loaded {len(existing_plays)} existing plays")
    
    # Search emails
    emails = search_emails(args.max)
    if not emails:
        logger.error("No emails found")
        return 1
    
    # Process each email
    new_plays = []
    for email in emails:
        email_id = email.get("id")
        subject = email.get("subject", "")
        
        play_number = extract_play_number(subject)
        if play_number and play_number in existing_numbers:
            logger.info(f"Play #{play_number} already exists, skipping")
            continue
        
        play = extract_play_from_email(email_id, subject)
        if play:
            new_plays.append(play)
            existing_numbers.add(play["play_number"])
        
        time.sleep(1)  # Rate limiting
    
    # Merge and save
    if new_plays:
        logger.info(f"\nExtracted {len(new_plays)} new plays")
        all_plays = existing_plays + new_plays
        
        if not args.dry_run:
            save_plays_json(all_plays)
            logger.info("✅ Extraction complete!")
        else:
            logger.info("DRY RUN - Changes not saved")
    else:
        logger.info("No new plays extracted")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
