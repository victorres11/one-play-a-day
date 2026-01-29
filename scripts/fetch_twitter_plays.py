#!/usr/bin/env python3
"""
One Play a Day - Twitter/X Play Fetcher
Fetches play videos from @CoachDanCasey's Twitter and adds them to plays.json
"""

import json
import subprocess
import sys
import re
import os
from pathlib import Path
from datetime import datetime
import logging
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
PLAYS_JSON = APP_DIR / "plays.json"

# R2 Configuration
R2_BUCKET = "opad-media"
R2_PUBLIC_URL = "https://pub-ac439fcb4c2f43a19d0737740b2f013f.r2.dev"
CF_TOKEN_PATH = Path.home() / ".clawdbot" / "credentials" / "cloudflare_api_token"
CF_ACCOUNT_PATH = Path.home() / ".clawdbot" / "credentials" / "cloudflare_account_id"

# Twitter account to monitor
TWITTER_HANDLE = "CoachDanCasey"

# Keywords that suggest a tweet is a play (case-insensitive)
PLAY_KEYWORDS = [
    'counter', 'rpo', 'running', 'pass', 'sweep', 'trap', 'option',
    'zone', 'power', 'draw', 'screen', 'bootleg', 'play-action',
    'iso', 'dive', 'toss', 'stretch', 'gap', 'man', 'coverage',
    'blitz', 'front', 'motion', 'shift', 'formation', 'personnel',
    'packers', 'cowboys', 'chiefs', 'niners', '49ers', 'raiders',
    'dolphins', 'bills', 'eagles', 'steelers', 'broncos', 'patriots',
    'michigan', 'ohio state', 'alabama', 'georgia', 'clemson', 'texas',
    'usc', 'oklahoma', 'lsu', 'notre dame', 'penn state', 'oregon',
    '1970', '1971', '1972', '1973', '1974', '1975', '1976', '1977', '1978', '1979',
    '1980', '1981', '1982', '1983', '1984', '1985', '1986', '1987', '1988', '1989',
    '1990', '1991', '1992', '1993', '1994', '1995', '1996', '1997', '1998', '1999',
    '2000', '2001', '2002', '2003', '2004', '2005', '2006', '2007', '2008', '2009',
    '2010', '2011', '2012', '2013', '2014', '2015', '2016', '2017', '2018', '2019',
    '2020', '2021', '2022', '2023', '2024', '2025', '2026',
]

# Ensure directories exist
MEDIA_DIR.mkdir(exist_ok=True)


def run_bird_command(args):
    """Run a bird CLI command and return output"""
    cmd = ["bird"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=True,
            timeout=30
        )
        return result.stdout.decode('utf-8', errors='replace')
    except subprocess.CalledProcessError as e:
        logger.error(f"bird command failed: {' '.join(cmd)}")
        logger.error(f"Error: {e.stderr.decode('utf-8', errors='replace')}")
        return None
    except subprocess.TimeoutExpired:
        logger.error(f"bird command timed out: {' '.join(cmd)}")
        return None


def fetch_recent_tweets(count=10):
    """Fetch recent tweets from Coach Dan Casey"""
    logger.info(f"Fetching {count} recent tweets from @{TWITTER_HANDLE}...")
    
    output = run_bird_command([
        "user-tweets", f"@{TWITTER_HANDLE}",
        "-n", str(count),
        "--json"
    ])
    
    if not output:
        return []
    
    try:
        tweets = json.loads(output)
        logger.info(f"Found {len(tweets)} tweets")
        return tweets
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse tweets: {e}")
        return []


def is_play_tweet(tweet):
    """Check if a tweet looks like a football play"""
    text = tweet.get("text", "").lower()
    
    # Must have video media
    media = tweet.get("media", [])
    has_video = any(m.get("type") == "video" for m in media)
    if not has_video:
        return False
    
    # Check for play-related keywords
    for keyword in PLAY_KEYWORDS:
        if keyword.lower() in text:
            return True
    
    return False


def extract_title(tweet):
    """Extract play title from tweet text"""
    text = tweet.get("text", "")
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text).strip()
    # Clean up
    text = text.replace('\n', ' ').strip()
    return text if text else "Untitled Play"


def get_tweet_id(tweet):
    """Extract tweet ID"""
    # Try different possible fields
    tweet_id = tweet.get("id") or tweet.get("rest_id") or tweet.get("id_str")
    if tweet_id:
        return str(tweet_id)
    
    # Try extracting from URL if present
    url = tweet.get("url", "")
    match = re.search(r'/status/(\d+)', url)
    if match:
        return match.group(1)
    
    return None


def get_video_url(tweet):
    """Extract video URL from tweet media"""
    media = tweet.get("media", [])
    for m in media:
        if m.get("type") == "video":
            return m.get("videoUrl")
    return None


def download_video(url, output_path):
    """Download a video from URL"""
    try:
        subprocess.run(
            ["curl", "-sL", "-o", str(output_path), url],
            check=True,
            timeout=60
        )
        logger.info(f"Downloaded {output_path.name}")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.error(f"Failed to download video: {e}")
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
        ], check=True, capture_output=True, env=env, timeout=60)
        logger.info(f"Uploaded {local_path.name} → R2: {r2_key}")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.error(f"Failed to upload to R2: {e}")
        return False


def load_plays_json():
    """Load existing plays.json"""
    if PLAYS_JSON.exists():
        with open(PLAYS_JSON) as f:
            return json.load(f)
    return []


def save_plays_json(plays):
    """Save plays.json, sorted by ID"""
    # Sort: numeric IDs first (descending), then string IDs (descending)
    def sort_key(p):
        pid = p.get("id", str(p.get("play_number", 0)))
        if pid.startswith("x-"):
            # Twitter plays: sort by tweet ID descending
            return (1, -int(pid[2:]))
        else:
            # Email plays: sort by play number descending
            try:
                return (0, -int(pid))
            except ValueError:
                return (2, pid)
    
    plays.sort(key=sort_key)
    
    with open(PLAYS_JSON, 'w') as f:
        json.dump(plays, f, indent=2)
    
    logger.info(f"Saved {len(plays)} plays to {PLAYS_JSON}")


def get_existing_ids(plays):
    """Get set of existing play IDs"""
    ids = set()
    for p in plays:
        # Check both id and play_number
        if "id" in p:
            ids.add(str(p["id"]))
        if "play_number" in p:
            ids.add(str(p["play_number"]))
        # Also check for twitter IDs without prefix
        pid = p.get("id", "")
        if pid.startswith("x-"):
            ids.add(pid[2:])  # Add raw tweet ID too
    return ids


def process_tweet(tweet, existing_ids):
    """Process a single tweet and return play dict if successful"""
    tweet_id = get_tweet_id(tweet)
    if not tweet_id:
        logger.warning("Could not extract tweet ID")
        return None
    
    play_id = f"x-{tweet_id}"
    
    # Check if already exists
    if play_id in existing_ids or tweet_id in existing_ids:
        logger.info(f"Tweet {tweet_id} already in database, skipping")
        return None
    
    # Check if it's a play tweet
    if not is_play_tweet(tweet):
        logger.info(f"Tweet {tweet_id} doesn't look like a play, skipping")
        return None
    
    title = extract_title(tweet)
    video_url = get_video_url(tweet)
    
    if not video_url:
        logger.warning(f"No video URL found for tweet {tweet_id}")
        return None
    
    logger.info(f"Processing tweet {tweet_id}: {title[:50]}...")
    
    # Download video
    video_filename = f"x-{tweet_id}.mp4"
    video_path = MEDIA_DIR / video_filename
    
    if not download_video(video_url, video_path):
        return None
    
    # Upload to R2
    r2_key = f"media/{video_filename}"
    if upload_to_r2(video_path, r2_key):
        video_url_final = f"{R2_PUBLIC_URL}/{r2_key}"
    else:
        video_url_final = f"media/{video_filename}"
    
    # Build play object
    play = {
        "id": play_id,
        "source": "twitter",
        "title": title,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "angles": [video_url_final],
        "play_details": {
            "down_and_distance": "",
            "personnel": "",
            "formation": ""
        },
        "play_diagram": "",
        "twitter_url": f"https://x.com/{TWITTER_HANDLE}/status/{tweet_id}"
    }
    
    return play


def main():
    logger.info("=" * 60)
    logger.info("One Play a Day - Twitter/X Play Fetcher")
    logger.info("=" * 60)
    
    # Load existing plays
    plays = load_plays_json()
    existing_ids = get_existing_ids(plays)
    logger.info(f"Loaded {len(plays)} existing plays")
    
    # Fetch recent tweets
    tweets = fetch_recent_tweets(count=15)
    if not tweets:
        logger.info("No tweets found")
        return 0
    
    # Process each tweet
    new_plays = 0
    skipped = 0
    
    for tweet in tweets:
        play = process_tweet(tweet, existing_ids)
        if play:
            plays.append(play)
            existing_ids.add(play["id"])
            new_plays += 1
            
            # Save incrementally
            save_plays_json(plays)
            logger.info(f"✅ Added play: {play['title'][:50]}")
        else:
            skipped += 1
        
        time.sleep(0.5)  # Rate limiting
    
    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("FETCH SUMMARY")
    logger.info("=" * 60)
    logger.info(f"New plays added: {new_plays}")
    logger.info(f"Skipped: {skipped}")
    logger.info(f"Total plays in database: {len(plays)}")
    logger.info("✅ Fetch complete!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
