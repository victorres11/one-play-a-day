#!/usr/bin/env python3
"""
OPAD Play Concept Auto-Tagger
Uses LLM to analyze play titles and suggest tags.
"""

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Use OpenAI SDK (gpt-4o-mini is cheap and fast for bulk)
try:
    from openai import OpenAI
except ImportError:
    print("Installing openai SDK...")
    os.system("pip install openai")
    from openai import OpenAI

PLAYS_FILE = Path(__file__).parent.parent / "plays.json"
OUTPUT_FILE = Path(__file__).parent.parent / "plays_tagged.json"
PROGRESS_FILE = Path(__file__).parent / "tagger_progress.json"

# Tag taxonomy for football concepts
TAG_TAXONOMY = """
## Run Concepts
- **OZ** (Outside Zone) - stretch runs, wide zone
- **IZ** (Inside Zone) - tight zone, mid zone
- **Power** - gap scheme with pulling guard
- **Counter** - misdirection gap scheme
- **Duo** - double team scheme
- **Iso** - isolation blocks
- **Trap** - trap blocks
- **Draw** - delayed handoff
- **Option** - QB reads defender (triple option, midline, speed option)
- **QB Run** - designed QB runs (scrambles, keepers, sneaks)

## Pass Concepts  
- **Screen** - WR screen, RB screen, tunnel screen, slip screen
- **PA** (Play Action) - fake run to pass
- **RPO** (Run-Pass Option) - run with pass read
- **Boot** - bootleg/rollout
- **Quick Game** - slant, hitch, out, quick passes
- **Vertical** - deep shots, go routes
- **Mesh** - crossing routes
- **Shallow** - shallow cross patterns
- **Flood** - flooding a zone (hi-lo reads)
- **Spot** - spot concept routes
- **Smash** - corner/hitch combo
- **Curl/Flat** - curl and flat combo
- **Mills** - mills concept
- **Drive** - drive concept
- **Scissors** - scissors routes

## Situational
- **RZ** (Red Zone) - inside the 20
- **GL** (Goal Line) - near the goal line
- **2PT** - two-point conversion
- **3rd Down** - obvious passing situation
- **Short Yardage** - 3rd/4th & short

## Special/Other
- **Trick** - trick plays, flea flicker, hook & ladder
- **Gadget** - unconventional plays
- **Motion** - jet motion, orbit motion, shift
- **Heavy** - jumbo personnel, extra OL
- **Empty** - empty backfield
- **Bunch** - bunch formations
- **Trips** - trips formations
"""

TAG_LIST = [
    "OZ", "IZ", "Power", "Counter", "Duo", "Iso", "Trap", "Draw", "Option", "QB Run",
    "Screen", "PA", "RPO", "Boot", "Quick Game", "Vertical", "Mesh", "Shallow", 
    "Flood", "Spot", "Smash", "Curl/Flat", "Mills", "Drive", "Scissors",
    "RZ", "GL", "2PT", "3rd Down", "Short Yardage",
    "Trick", "Gadget", "Motion", "Heavy", "Empty", "Bunch", "Trips"
]

def get_tags_for_play(client, title: str, play_details: dict) -> dict:
    """Send play to LLM for tag suggestions."""
    
    context = ""
    if play_details:
        if play_details.get("down_and_distance"):
            context += f"Down/Distance: {play_details['down_and_distance']}\n"
        if play_details.get("personnel"):
            context += f"Personnel: {play_details['personnel']}\n"
        if play_details.get("formation"):
            context += f"Formation: {play_details['formation']}\n"
    
    prompt = f"""Analyze this football play and suggest relevant tags.

Play Title: {title}
{context}

Available tags:
{', '.join(TAG_LIST)}

Return a JSON object with:
- "tags": list of 1-5 most relevant tags from the list above
- "confidence": "high", "medium", or "low"
- "run_or_pass": "run", "pass", or "rpo"
- "reasoning": brief explanation (1 sentence)

Only use tags from the provided list. Be conservative - only tag concepts clearly indicated.

Return ONLY valid JSON, no other text."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Parse JSON from response
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        
        result = json.loads(response_text)
        return result
        
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return {"tags": [], "confidence": "low", "run_or_pass": "unknown", "reasoning": "Parse error"}
    except Exception as e:
        print(f"  API error: {e}")
        return None

def load_progress() -> dict:
    """Load progress from previous run."""
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"processed": [], "results": {}}

def save_progress(progress: dict):
    """Save progress for resume."""
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))

def main():
    print("🏈 OPAD Play Concept Auto-Tagger")
    print("=" * 50)
    
    # Load plays
    plays = json.loads(PLAYS_FILE.read_text())
    print(f"Loaded {len(plays)} plays from {PLAYS_FILE}")
    
    # Load progress
    progress = load_progress()
    processed_ids = set(progress["processed"])
    print(f"Previously processed: {len(processed_ids)} plays")
    
    # Initialize client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: No OPENAI_API_KEY found")
        sys.exit(1)
    
    client = OpenAI(api_key=api_key)
    
    # Process plays
    to_process = [p for p in plays if p["id"] not in processed_ids]
    print(f"Plays to process: {len(to_process)}")
    
    if not to_process:
        print("All plays already processed!")
        return
    
    start_time = time.time()
    
    for i, play in enumerate(to_process):
        play_id = play["id"]
        title = play["title"]
        details = play.get("play_details", {})
        
        print(f"\n[{i+1}/{len(to_process)}] Play #{play_id}: {title[:60]}...")
        
        result = get_tags_for_play(client, title, details)
        
        if result:
            progress["results"][play_id] = result
            progress["processed"].append(play_id)
            print(f"  Tags: {result.get('tags', [])} ({result.get('confidence', 'unknown')})")
            print(f"  Type: {result.get('run_or_pass', 'unknown')}")
            
            # Save progress every 10 plays
            if (i + 1) % 10 == 0:
                save_progress(progress)
                print(f"  [Progress saved: {len(progress['processed'])} total]")
        
        # Rate limiting - Sonnet is fast but let's be gentle
        time.sleep(0.5)
    
    # Final save
    save_progress(progress)
    
    # Merge results into plays
    print("\n" + "=" * 50)
    print("Merging tags into plays...")
    
    tagged_count = 0
    for play in plays:
        play_id = play["id"]
        if play_id in progress["results"]:
            result = progress["results"][play_id]
            play["auto_tags"] = result.get("tags", [])
            play["tag_confidence"] = result.get("confidence", "low")
            play["run_or_pass"] = result.get("run_or_pass", "unknown")
            tagged_count += 1
    
    # Save tagged plays
    OUTPUT_FILE.write_text(json.dumps(plays, indent=2))
    print(f"Saved {tagged_count} tagged plays to {OUTPUT_FILE}")
    
    elapsed = time.time() - start_time
    print(f"\nCompleted in {elapsed:.1f}s ({elapsed/len(to_process):.2f}s per play)")
    
    # Stats
    all_tags = []
    for r in progress["results"].values():
        all_tags.extend(r.get("tags", []))
    
    from collections import Counter
    tag_counts = Counter(all_tags)
    print("\nTop tags:")
    for tag, count in tag_counts.most_common(15):
        print(f"  {tag}: {count}")

if __name__ == "__main__":
    main()
