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

# R2 Configuration
R2_BUCKET = "opad-media"
R2_PUBLIC_URL = "https://pub-ac439fcb4c2f43a19d0737740b2f013f.r2.dev"
CF_TOKEN_PATH = Path.home() / ".clawdbot" / "credentials" / "cloudflare_api_token"
CF_ACCOUNT_PATH = Path.home() / ".clawdbot" / "credentials" / "cloudflare_account_id"

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
    
    # Method 1: Look for preheader span (most reliable)
    preheader_match = re.search(r'<span[^>]*class="preheader"[^>]*>(.*?)</span>', html, re.IGNORECASE | re.DOTALL)
    if preheader_match:
        title = preheader_match.group(1).strip()
        # Clean up whitespace
        title = re.sub(r'\s+', ' ', title).strip()
        if len(title) > 10 and len(title) < 200:
            return title
    
    # Method 2: Look for data-paragraph="true" div
    para_match = re.search(r'<div[^>]*data-paragraph="true"[^>]*>(.*?)</div>', html, re.IGNORECASE | re.DOTALL)
    if para_match:
        title = para_match.group(1).strip()
        title = re.sub(r'<[^>]+>', '', title)  # Remove any nested HTML
        title = re.sub(r'\s+', ' ', title).strip()
        if len(title) > 10 and len(title) < 200:
            return title
    
    # Method 3: Fallback - look for bold text with year
    patterns = [
        r'<b[^>]*>(.*?20\d{2}.*?)</b>',
        r'<strong[^>]*>(.*?20\d{2}.*?)</strong>',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html, re.IGNORECASE | re.DOTALL)
        if matches:
            title = matches[0]
            title = re.sub(r'<[^>]+>', '', title)
            title = re.sub(r'\s+', ' ', title).strip()
            if len(title) > 10 and len(title) < 200:
                return title
    
    return "Untitled Play"


def clean_html_text(text):
    """Clean HTML entities and tags from text"""
    if not text:
        return ""
    # Decode HTML entities
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    text = text.replace('&nbsp;', ' ')
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_play_details(html):
    """Extract down & distance, personnel, formation"""
    details = {
        "down_and_distance": "",
        "personnel": "",
        "formation": ""
    }
    
    # New format: single line with | separators
    # "Down & Distance: 2nd & 10 | Personnel: 11p | Formation: Dual Rt"
    
    # Down & Distance - stop at | or < or end of content
    dd_match = re.search(
        r'Down\s*(?:&amp;|&)\s*Distance[:\s]*</strong>\s*([^|<\n]+)',
        html, re.IGNORECASE
    )
    if not dd_match:
        # Fallback: simpler pattern
        dd_match = re.search(
            r'Down\s*(?:&amp;|&)\s*Distance[:\s]*([^|<\n]+)',
            html, re.IGNORECASE
        )
    if dd_match:
        details["down_and_distance"] = clean_html_text(dd_match.group(1))
    
    # Personnel - stop at | or < or end of content
    # Format: "<strong>Personnel</strong>: 11p" - note the colon AFTER the closing tag
    pers_match = re.search(
        r'Personnel\s*</strong>\s*:?\s*([^|<\n]+)',
        html, re.IGNORECASE
    )
    if not pers_match:
        pers_match = re.search(
            r'Personnel[:\s]*([^|<\n]+)',
            html, re.IGNORECASE
        )
    if pers_match:
        val = clean_html_text(pers_match.group(1))
        # Remove leading colon if present
        details["personnel"] = val.lstrip(': ')
    
    # Formation - may be at end of line, stop at < or newline
    form_match = re.search(
        r'Formation[:\s]*</strong>\s*([^<\n]+)',
        html, re.IGNORECASE
    )
    if not form_match:
        form_match = re.search(
            r'Formation[:\s]*([^<\n|]+)',
            html, re.IGNORECASE
        )
    if form_match:
        details["formation"] = clean_html_text(form_match.group(1))
    
    return details


def extract_media_urls(html):
    """Extract GIF and diagram URLs from email"""
    # Find all image URLs
    all_images = re.findall(r'https://[^"\s]+\.(?:gif|jpg|jpeg|png)', html, re.IGNORECASE)
    
    # Known header logo patterns to skip
    SKIP_PATTERNS = [
        "87a13924-ec12-4c27-83d4-3c07bc431fe0",  # One Play a Day header logo
        "assets/social/",  # Social media icons
        "Email-Header",
        "TeamWorks",
        "flodesk.com/assets/",  # Flodesk system assets
    ]
    
    # Filter out header/logo/social images
    filtered = [
        url for url in all_images 
        if not any(skip in url for skip in SKIP_PATTERNS)
    ]
    
    # Split before the divider if present (footer content)
    divider_pos = html.find('fd-divider')
    if divider_pos > 0:
        html_before_divider = html[:divider_pos]
        filtered = re.findall(r'https://[^"\s]+\.(?:gif|jpg|jpeg|png)', html_before_divider, re.IGNORECASE)
        filtered = [
            url for url in filtered 
            if not any(skip in url for skip in SKIP_PATTERNS)
        ]
    
    # Separate GIFs (angles) from static images
    gifs = [url for url in filtered if url.lower().endswith('.gif')]
    static_images = [url for url in filtered if not url.lower().endswith('.gif')]
    
    # The diagram is typically a static image that appears AFTER the GIFs
    # or contains "CleanShot" in the filename (screenshot of the diagram)
    diagram = None
    if static_images:
        # Prefer images with "CleanShot" or similar screenshot indicators
        for img in static_images:
            if 'cleanshot' in img.lower() or 'screenshot' in img.lower():
                diagram = img
                break
        # Otherwise take the first static image that's not the header
        if not diagram:
            diagram = static_images[0]
    
    return {
        "angles": gifs,
        "diagram": diagram
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


def upload_to_r2(local_path, r2_key):
    """Upload a file to Cloudflare R2"""
    if not CF_TOKEN_PATH.exists() or not CF_ACCOUNT_PATH.exists():
        logger.warning("R2 credentials not found, skipping upload")
        return False
    
    env = os.environ.copy()
    env["CLOUDFLARE_API_TOKEN"] = CF_TOKEN_PATH.read_text().strip()
    env["CLOUDFLARE_ACCOUNT_ID"] = CF_ACCOUNT_PATH.read_text().strip()
    
    try:
        subprocess.run([
            "wrangler", "r2", "object", "put",
            f"{R2_BUCKET}/{r2_key}",
            "--file", str(local_path),
            "--remote"
        ], check=True, capture_output=True, env=env)
        logger.info(f"Uploaded {local_path.name} → R2: {r2_key}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to upload {local_path.name} to R2: {e.stderr.decode('utf-8', errors='replace')}")
        return False


def process_media(play_number, media_urls):
    """Download, convert, and upload media files to R2"""
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
                # Upload to R2
                r2_key = f"media/{mp4_filename}"
                if upload_to_r2(mp4_path, r2_key):
                    result["angles"].append(f"{R2_PUBLIC_URL}/{r2_key}")
                else:
                    # Fallback to local path
                    result["angles"].append(f"media/{mp4_filename}")
        
        time.sleep(0.5)  # Rate limiting
    
    # Process diagram
    if media_urls["diagram"]:
        diagram_url = media_urls["diagram"]
        ext = Path(urlparse(diagram_url).path).suffix or ".jpg"
        diagram_filename = f"{play_number}_diagram{ext}"
        diagram_path = MEDIA_DIR / diagram_filename
        
        if download_file(diagram_url, diagram_path):
            # Upload to R2
            r2_key = f"media/{diagram_filename}"
            if upload_to_r2(diagram_path, r2_key):
                result["diagram"] = f"{R2_PUBLIC_URL}/{r2_key}"
            else:
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


def scan_local_media():
    """Scan local media directory and group files by play number"""
    plays_media = {}
    
    # Scan MP4 files
    for mp4_file in MEDIA_DIR.glob("*.mp4"):
        match = re.match(r'^(\d+)_angle(\d+)\.mp4$', mp4_file.name)
        if match:
            play_num = int(match.group(1))
            angle_num = int(match.group(2))
            if play_num not in plays_media:
                plays_media[play_num] = {"angles": [], "diagram": None}
            plays_media[play_num]["angles"].append((angle_num, mp4_file))
    
    # Sort angles by number
    for play_num in plays_media:
        plays_media[play_num]["angles"].sort(key=lambda x: x[0])
        plays_media[play_num]["angles"] = [f for _, f in plays_media[play_num]["angles"]]
    
    # Scan for diagrams
    for diagram_file in MEDIA_DIR.glob("*_diagram.*"):
        match = re.match(r'^(\d+)_diagram\.', diagram_file.name)
        if match:
            play_num = int(match.group(1))
            if play_num in plays_media:
                plays_media[play_num]["diagram"] = diagram_file
    
    return plays_media


def search_email_by_play_number(play_number):
    """Search for a specific play's email"""
    output = run_gog_command([
        "gmail", "search",
        f"from:dan@coachdancasey.com subject:'One Play a Day' subject:'{play_number}'",
        "--max", "5",
        "--json"
    ])
    
    if not output:
        return None
    
    try:
        data = json.loads(output)
        emails = data.get("threads", []) or data.get("messages", [])
        
        # Find exact match
        for email in emails:
            subject = email.get("subject", "")
            num = extract_play_number(subject)
            if num == play_number:
                return email
        
        return emails[0] if emails else None
    except json.JSONDecodeError:
        return None


def upload_local_media_mode(args):
    """Upload existing local media files to R2 and rebuild plays.json"""
    logger.info("=" * 60)
    logger.info("One Play a Day - Upload Local Media Mode")
    logger.info("=" * 60)
    
    # Scan local files
    local_media = scan_local_media()
    logger.info(f"Found {len(local_media)} plays with local media")
    
    # Load existing plays
    existing_plays = load_plays_json()
    existing_numbers = {p["play_number"] for p in existing_plays}
    logger.info(f"Already in plays.json: {len(existing_numbers)} plays")
    
    # Find plays that need processing
    to_process = sorted([p for p in local_media if p not in existing_numbers], reverse=True)
    logger.info(f"Plays to upload: {len(to_process)}")
    
    if not to_process:
        logger.info("Nothing to do!")
        return 0
    
    # Apply batch limit
    if args.batch > 0:
        to_process = to_process[:args.batch]
        logger.info(f"Batch limited to {len(to_process)} plays")
    
    uploaded_count = 0
    failed_count = 0
    
    for i, play_number in enumerate(to_process):
        media = local_media[play_number]
        logger.info(f"\n[{i+1}/{len(to_process)}] Processing Play #{play_number}")
        logger.info(f"  Local angles: {len(media['angles'])}")
        
        # Search email for metadata
        email = search_email_by_play_number(play_number)
        if not email:
            logger.warning(f"  Could not find email for Play #{play_number}, using defaults")
            title = "Untitled Play"
            date = datetime.now().strftime("%Y-%m-%d")
            details = {"down_and_distance": "", "personnel": "", "formation": ""}
        else:
            # Get full email content for metadata
            html = get_email_content(email.get("id"))
            if html:
                title = extract_title(html)
                date = extract_email_date(html)
                details = extract_play_details(html)
            else:
                title = "Untitled Play"
                date = datetime.now().strftime("%Y-%m-%d")
                details = {"down_and_distance": "", "personnel": "", "formation": ""}
        
        logger.info(f"  Title: {title}")
        
        # Upload angles to R2
        angle_urls = []
        for mp4_path in media["angles"]:
            r2_key = f"media/{mp4_path.name}"
            if upload_to_r2(mp4_path, r2_key):
                angle_urls.append(f"{R2_PUBLIC_URL}/{r2_key}")
            else:
                # Fallback to local
                angle_urls.append(f"media/{mp4_path.name}")
            time.sleep(0.3)  # Light rate limiting
        
        # Upload diagram if exists
        diagram_url = ""
        if media["diagram"]:
            diagram_path = media["diagram"]
            r2_key = f"media/{diagram_path.name}"
            if upload_to_r2(diagram_path, r2_key):
                diagram_url = f"{R2_PUBLIC_URL}/{r2_key}"
            else:
                diagram_url = f"media/{diagram_path.name}"
        
        if not angle_urls:
            logger.error(f"  No angles uploaded for Play #{play_number}")
            failed_count += 1
            continue
        
        # Build play object
        play = {
            "play_number": play_number,
            "date": date,
            "title": title,
            "angles": angle_urls,
            "play_details": details,
            "play_diagram": diagram_url
        }
        
        # Save incrementally
        if not args.dry_run:
            current_plays = load_plays_json()
            current_numbers = {p["play_number"] for p in current_plays}
            if play["play_number"] not in current_numbers:
                current_plays.append(play)
                save_plays_json(current_plays)
        
        uploaded_count += 1
        logger.info(f"  ✅ Uploaded ({uploaded_count} done, {len(to_process) - i - 1} remaining)")
        
        # Progress every 20
        if uploaded_count % 20 == 0:
            logger.info(f"\n📊 Progress: {uploaded_count}/{len(to_process)} uploaded, {failed_count} failed")
        
        time.sleep(0.5)  # Rate limiting between plays
    
    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("UPLOAD SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Uploaded: {uploaded_count}")
    logger.info(f"Failed: {failed_count}")
    
    final_plays = load_plays_json()
    logger.info(f"Total plays in database: {len(final_plays)}")
    logger.info("✅ Upload complete!")
    
    return 0


def refresh_details_mode(args):
    """Re-extract title and play_details from emails for existing plays"""
    logger.info("=" * 60)
    logger.info("One Play a Day - Refresh Details Mode")
    logger.info("=" * 60)
    
    # Load existing plays
    plays = load_plays_json()
    logger.info(f"Loaded {len(plays)} plays")
    
    if not plays:
        logger.error("No plays to refresh")
        return 1
    
    updated_count = 0
    failed_count = 0
    
    for i, play in enumerate(plays):
        play_number = play["play_number"]
        logger.info(f"\n[{i+1}/{len(plays)}] Refreshing Play #{play_number}")
        
        # Search for email
        email = search_email_by_play_number(play_number)
        if not email:
            logger.warning(f"  Could not find email for Play #{play_number}")
            failed_count += 1
            continue
        
        # Get email content
        html = get_email_content(email.get("id"))
        if not html:
            logger.warning(f"  Could not fetch email content")
            failed_count += 1
            continue
        
        # Re-extract details
        new_title = extract_title(html)
        new_details = extract_play_details(html)
        new_date = extract_email_date(html)
        
        # Update play
        old_title = play.get("title", "")
        old_details = play.get("play_details", {})
        
        play["title"] = new_title
        play["play_details"] = new_details
        play["date"] = new_date
        
        # Log changes
        if new_title != old_title:
            logger.info(f"  Title: {old_title[:50]} → {new_title[:50]}")
        if new_details != old_details:
            logger.info(f"  Details: D&D={new_details.get('down_and_distance', '')}, "
                       f"Pers={new_details.get('personnel', '')}, "
                       f"Form={new_details.get('formation', '')}")
        
        updated_count += 1
        
        # Progress every 20
        if updated_count % 20 == 0:
            logger.info(f"\n📊 Progress: {updated_count}/{len(plays)} refreshed")
            # Save incrementally
            if not args.dry_run:
                save_plays_json(plays)
        
        time.sleep(0.3)  # Rate limiting
    
    # Final save
    if not args.dry_run:
        save_plays_json(plays)
    
    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("REFRESH SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Updated: {updated_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info("✅ Refresh complete!")
    
    return 0


def main():
    parser = argparse.ArgumentParser(description="Extract One Play a Day emails")
    parser.add_argument("--max", type=int, default=50, help="Maximum emails to fetch from Gmail")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N emails (for sharding)")
    parser.add_argument("--batch", type=int, default=0, help="Process only N plays (0=all)")
    parser.add_argument("--dry-run", action="store_true", help="Don't save changes")
    parser.add_argument("--no-incremental", action="store_true", help="Disable incremental saves")
    parser.add_argument("--upload-local", action="store_true", help="Upload local media to R2 (skip download/convert)")
    parser.add_argument("--refresh-details", action="store_true", help="Re-extract title/details for existing plays")
    args = parser.parse_args()
    
    # Handle refresh-details mode
    if args.refresh_details:
        return refresh_details_mode(args)
    
    # Handle upload-local mode
    if args.upload_local:
        return upload_local_media_mode(args)
    
    logger.info("=" * 60)
    logger.info("One Play a Day - Email Extraction")
    logger.info(f"Config: max={args.max}, offset={args.offset}, batch={args.batch}")
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
    
    # Apply offset (skip first N emails)
    if args.offset > 0:
        logger.info(f"Skipping first {args.offset} emails (offset)")
        emails = emails[args.offset:]
    
    logger.info(f"Processing {len(emails)} emails after offset")
    
    # Process each email
    new_plays_count = 0
    processed_count = 0
    skipped_count = 0
    
    for i, email in enumerate(emails):
        # Check batch limit
        if args.batch > 0 and new_plays_count >= args.batch:
            logger.info(f"Batch limit ({args.batch}) reached, stopping")
            break
        
        email_id = email.get("id")
        subject = email.get("subject", "")
        
        play_number = extract_play_number(subject)
        if play_number and play_number in existing_numbers:
            logger.info(f"Play #{play_number} already exists, skipping")
            skipped_count += 1
            continue
        
        play = extract_play_from_email(email_id, subject)
        if play:
            new_plays_count += 1
            existing_numbers.add(play["play_number"])
            
            # Incremental save after each successful play
            if not args.dry_run and not args.no_incremental:
                # Reload to get any concurrent updates, add new play, save
                current_plays = load_plays_json()
                current_numbers = {p["play_number"] for p in current_plays}
                if play["play_number"] not in current_numbers:
                    current_plays.append(play)
                    save_plays_json(current_plays)
                    logger.info(f"💾 Saved incrementally ({len(current_plays)} total plays)")
            
            processed_count += 1
            
            # Progress report every 10 plays
            if new_plays_count % 10 == 0:
                logger.info(f"📊 Progress: {new_plays_count} new plays, {skipped_count} skipped, {i+1}/{len(emails)} emails")
        
        time.sleep(1)  # Rate limiting
    
    # Final summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("EXTRACTION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"New plays extracted: {new_plays_count}")
    logger.info(f"Already existed (skipped): {skipped_count}")
    logger.info(f"Emails processed: {processed_count + skipped_count}")
    
    final_plays = load_plays_json()
    logger.info(f"Total plays in database: {len(final_plays)}")
    logger.info("✅ Extraction complete!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
