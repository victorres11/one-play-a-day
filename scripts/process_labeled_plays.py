#!/usr/bin/env python3
"""
One Play a Day - Process Labeled Emails
Processes unread emails with the 'one-play-a-day' Gmail label.
Extracts plays and adds them to plays.json, then marks emails as read.
"""

import json
import subprocess
import sys
import logging
from pathlib import Path

# Import from the main extraction script
from extract_plays import (
    extract_play_number,
    extract_play_from_email,
    load_plays_json,
    save_plays_json,
    logger
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


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
        except:
            pass
        return None


def search_labeled_emails():
    """Search for unread emails with the one-play-a-day label"""
    logger.info("Searching for unread emails in 'one-play-a-day' label...")
    
    output = run_gog_command([
        "gmail", "search",
        "label:one-play-a-day is:unread",
        "--max", "50",
        "--json"
    ])
    
    if not output:
        return []
    
    try:
        data = json.loads(output)
        emails = data.get("threads", []) or data.get("messages", [])
        logger.info(f"Found {len(emails)} unread emails with label")
        return emails
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse search results: {e}")
        return []


def mark_email_read(thread_id):
    """Mark an email thread as read"""
    logger.info(f"Marking thread {thread_id} as read...")
    result = run_gog_command([
        "gmail", "thread", "modify", thread_id,
        "--remove", "UNREAD"
    ])
    return result is not None


def main():
    logger.info("=" * 60)
    logger.info("One Play a Day - Process Labeled Emails")
    logger.info("=" * 60)
    
    # Load existing plays
    existing_plays = load_plays_json()
    existing_numbers = {p.get("play_number") or p.get("id") for p in existing_plays}
    logger.info(f"Loaded {len(existing_plays)} existing plays")
    
    # Search for labeled emails
    emails = search_labeled_emails()
    if not emails:
        logger.info("No unread emails to process")
        return 0
    
    # Process each email
    new_plays = 0
    skipped = 0
    failed = 0
    processed_threads = []
    
    for email in emails:
        email_id = email.get("id")
        subject = email.get("subject", "")
        
        play_number = extract_play_number(subject)
        if not play_number:
            logger.warning(f"Could not extract play number from: {subject}")
            failed += 1
            processed_threads.append(email_id)  # Still mark as read
            continue
        
        if play_number in existing_numbers:
            logger.info(f"Play #{play_number} already exists, skipping extraction")
            skipped += 1
            processed_threads.append(email_id)
            continue
        
        # Extract and process the play
        play = extract_play_from_email(email_id, subject)
        if play:
            # Save incrementally
            current_plays = load_plays_json()
            current_numbers = {p["play_number"] for p in current_plays}
            if play["play_number"] not in current_numbers:
                current_plays.append(play)
                save_plays_json(current_plays)
                logger.info(f"✅ Added Play #{play_number}")
                new_plays += 1
                existing_numbers.add(play_number)
            
            processed_threads.append(email_id)
        else:
            logger.error(f"Failed to extract Play #{play_number}")
            failed += 1
            processed_threads.append(email_id)  # Mark as read anyway
    
    # Mark all processed emails as read
    logger.info(f"\nMarking {len(processed_threads)} emails as read...")
    for thread_id in processed_threads:
        mark_email_read(thread_id)
    
    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("PROCESSING SUMMARY")
    logger.info("=" * 60)
    logger.info(f"New plays added: {new_plays}")
    logger.info(f"Already existed: {skipped}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Emails marked read: {len(processed_threads)}")
    
    final_plays = load_plays_json()
    logger.info(f"Total plays in database: {len(final_plays)}")
    logger.info("✅ Processing complete!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
