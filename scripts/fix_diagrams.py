#!/usr/bin/env python3
"""
Fix diagram URLs in plays.json by re-fetching emails and extracting the correct diagram.
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

HEADER_LOGO_PATTERN = "87a13924-ec12-4c27-83d4-3c07bc431fe0"


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
        output = result.stdout.decode('utf-8', errors='replace')
        return output
    except subprocess.CalledProcessError as e:
        logger.error(f"gog command failed: {' '.join(cmd)}")
        try:
            error_msg = e.stderr.decode('utf-8', errors='replace')
            logger.error(f"Error: {error_msg}")
        except Exception:
            pass
        return None


def get_email_content(email_id):
    """Fetch full email content"""
    logger.info(f"Fetching email {email_id}...")
    return run_gog_command(["gmail", "get", email_id])


def extract_play_number(subject):
    """Extract play number from subject line"""
    match = re.search(r'(?:#|-)?\s*(\d+)', subject)
    if match:
        return int(match.group(1))
    return None


def search_email(query, max_results=5):
    output = run_gog_command([
        "gmail", "search",
        query,
        "--max", str(max_results),
        "--json"
    ])

    if not output:
        return []

    try:
        data = json.loads(output)
        return data.get("threads", []) or data.get("messages", [])
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse search results: {e}")
        return []


def search_email_by_title(title, play_number=None):
    """Search for a specific play's email by title, falling back to play number."""
    title = (title or "").strip()
    if title:
        title_snippet = re.sub(r'\s+', ' ', title)[:120]
        query = f'from:dan@coachdancasey.com subject:"One Play a Day" "{title_snippet}"'
        emails = search_email(query, max_results=5)
        if emails:
            return emails[0]

    if play_number is not None:
        query = f'from:dan@coachdancasey.com subject:"One Play a Day" subject:"{play_number}"'
        emails = search_email(query, max_results=5)
        for email in emails:
            subject = email.get("subject", "")
            num = extract_play_number(subject)
            if num == play_number:
                return email
        return emails[0] if emails else None

    return None


def extract_media_urls_skip_header_footer(html):
    """Extract GIF and diagram URLs from email, skipping header/footer images."""
    all_images = re.findall(r'https://[^"\s>]+\.(?:gif|jpg|jpeg|png)', html, re.IGNORECASE)

    SKIP_PATTERNS = [
        HEADER_LOGO_PATTERN,
        "assets/social/",
        "Email-Header",
        "TeamWorks",
        "flodesk.com/assets/",
    ]

    # Trim footer content
    footer_markers = [
        "fd-divider",
        "fd-footer",
        "footer",
        "unsubscribe",
    ]
    cut_pos = None
    for marker in footer_markers:
        pos = html.find(marker)
        if pos > 0:
            cut_pos = pos if cut_pos is None else min(cut_pos, pos)
    if cut_pos:
        html = html[:cut_pos]

    filtered = [
        url for url in re.findall(r'https://[^"\s>]+\.(?:gif|jpg|jpeg|png)', html, re.IGNORECASE)
        if not any(skip in url for skip in SKIP_PATTERNS)
    ]

    gifs = [url for url in filtered if url.lower().endswith('.gif')]
    static_images = [url for url in filtered if not url.lower().endswith('.gif')]

    diagram = None
    if static_images:
        # Prefer explicit screenshot-style filenames
        for img in static_images:
            if any(token in img.lower() for token in ["cleanshot", "screenshot", "diagram"]):
                diagram = img
                break

        if not diagram:
            # Prefer the first static image after the last GIF
            if gifs:
                last_gif = None
                for url in filtered:
                    if url.lower().endswith('.gif'):
                        last_gif = url
                if last_gif:
                    after_last_gif = False
                    for url in filtered:
                        if url == last_gif:
                            after_last_gif = True
                            continue
                        if after_last_gif and not url.lower().endswith('.gif'):
                            diagram = url
                            break

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


def load_plays_json():
    """Load existing plays.json"""
    if PLAYS_JSON.exists():
        with open(PLAYS_JSON) as f:
            return json.load(f)
    return []


def save_plays_json(plays):
    """Save plays.json"""
    plays.sort(key=lambda p: p["play_number"], reverse=True)
    with open(PLAYS_JSON, 'w') as f:
        json.dump(plays, f, indent=2)
    logger.info(f"Saved {len(plays)} plays to {PLAYS_JSON}")


def get_email_id_from_play(play):
    for key in ["email_id", "gmail_id", "source_email_id", "message_id", "source_email"]:
        value = play.get(key)
        if value:
            return value
    return None


def refresh_diagram_for_play(play):
    play_number = play.get("play_number")
    title = play.get("title", "")
    email_id = get_email_id_from_play(play)

    if email_id:
        html = get_email_content(email_id)
    else:
        email = search_email_by_title(title, play_number=play_number)
        if not email:
            logger.warning(f"  Could not find email for Play #{play_number}")
            return False
        html = get_email_content(email.get("id"))

    if not html:
        logger.warning(f"  Could not fetch email content for Play #{play_number}")
        return False

    media_urls = extract_media_urls_skip_header_footer(html)
    diagram_url = media_urls.get("diagram")
    if not diagram_url:
        logger.warning(f"  No diagram found for Play #{play_number}")
        return False

    ext = Path(urlparse(diagram_url).path).suffix or ".jpg"
    diagram_filename = f"{play_number}_diagram{ext}"
    diagram_path = MEDIA_DIR / diagram_filename

    if not download_file(diagram_url, diagram_path):
        return False

    r2_key = f"media/{diagram_filename}"
    if upload_to_r2(diagram_path, r2_key):
        play["play_diagram"] = f"{R2_PUBLIC_URL}/{r2_key}"
    else:
        play["play_diagram"] = f"media/{diagram_filename}"

    return True


def main():
    parser = argparse.ArgumentParser(description="Fix diagram URLs in plays.json")
    parser.add_argument("--dry-run", action="store_true", help="Don't save changes")
    parser.add_argument("--batch", type=int, default=0, help="Process only N plays (0=all)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("One Play a Day - Fix Diagrams")
    logger.info("=" * 60)

    plays = load_plays_json()
    if not plays:
        logger.error("No plays found")
        return 1

    to_fix = [p for p in plays if HEADER_LOGO_PATTERN in (p.get("play_diagram") or "")]
    if args.batch > 0:
        to_fix = to_fix[:args.batch]

    logger.info(f"Loaded {len(plays)} plays")
    logger.info(f"Plays needing diagram fix: {len(to_fix)}")

    if not to_fix:
        logger.info("Nothing to do")
        return 0

    updated = 0
    failed = 0

    for i, play in enumerate(to_fix, start=1):
        play_number = play.get("play_number")
        title = play.get("title", "")
        logger.info(f"\n[{i}/{len(to_fix)}] Fixing Play #{play_number} - {title[:60]}")

        if refresh_diagram_for_play(play):
            updated += 1
            logger.info(f"  ✅ Updated diagram for Play #{play_number}")
            if not args.dry_run:
                save_plays_json(plays)
        else:
            failed += 1
            logger.info(f"  ❌ Failed to update diagram for Play #{play_number}")

        if updated > 0 and updated % 20 == 0:
            logger.info(f"\n📊 Progress: {updated} updated, {failed} failed")

        time.sleep(0.5)

    logger.info("")
    logger.info("=" * 60)
    logger.info("FIX SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Updated: {updated}")
    logger.info(f"Failed: {failed}")
    logger.info("✅ Fix complete!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
