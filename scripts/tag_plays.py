#!/usr/bin/env python3
"""
Play Type Tagging Script - PROTOTYPE
Extracts tags from play titles using pattern matching.

Future enhancement: Add AI classification for uncertain cases.
"""

import json
import re
from pathlib import Path
from collections import Counter

# Path to plays
PLAYS_JSON = Path(__file__).parent.parent / "plays.json"

# Tag patterns (keyword -> tag)
# More specific patterns should come before general ones
TAG_PATTERNS = {
    # Run Concepts
    r"counter": "run:counter",
    r"iso\b": "run:iso",
    r"power": "run:power",
    r"duo\b": "run:duo",
    r"zone read": "run:zone-read",
    r"inside zone|iz\b": "run:inside-zone",
    r"outside zone|oz\b": "run:outside-zone",
    r"toss": "run:toss",
    r"sweep": "run:sweep",
    r"draw\b": "run:draw",
    r"trap\b": "run:trap",
    r"pin.?&?.?pull": "run:pin-pull",
    r"midline": "run:midline",
    r"option": "run:option",
    r"wham": "run:wham",
    r"gt counter": "run:gt-counter",
    r"buck\b": "run:buck",
    
    # Pass Concepts
    r"flood": "pass:flood",
    r"dagger": "pass:dagger",
    r"mesh\b": "pass:mesh",
    r"shallow": "pass:shallow",
    r"four.?verts|4.?verts|verticals": "pass:four-verts",
    r"smash": "pass:smash",
    r"levels": "pass:levels",
    r"sail\b": "pass:sail",
    r"pylon": "pass:pylon",
    r"post.?wheel": "pass:post-wheel",
    r"curl\b": "pass:curl",
    r"snag\b": "pass:snag",
    r"stick\b": "pass:stick",
    r"choice\b": "pass:choice",
    r"scissors": "pass:scissors",
    r"corner\b": "pass:corner",
    r"wheel\b": "pass:wheel",
    r"leak\b": "pass:te-leak",
    
    # Play Action
    r"pa\b|play.?action": "play-action",
    r"boot\b": "boot",
    r"naked\b": "naked-boot",
    
    # Screens
    r"tunnel\s+screen": "screen:tunnel",
    r"slip\s+screen": "screen:slip",
    r"swing\s+screen": "screen:swing",
    r"filter\s+screen": "screen:filter",
    r"screen": "screen",
    
    # RPO
    r"rpo\b": "rpo",
    
    # Trick Plays
    r"flea\s*flicker": "trick:flea-flicker",
    r"hook\s*(&|and)?\s*ladder": "trick:hook-ladder",
    r"reverse": "trick:reverse",
    r"philly\s*special": "trick:philly-special",
    r"fake\s*punt": "trick:fake-punt",
    r"trick": "trick",
    
    # Situation
    r"red\s*zone": "situation:red-zone",
    r"goal\s*line|1st\s*&\s*goal|2nd\s*&\s*goal|3rd\s*&\s*goal": "situation:goal-line",
    r"3rd\s*(&|and)\s*(long|short|\d+)": "situation:3rd-down",
    r"4th\s*(&|and)\s*\d+": "situation:4th-down",
    
    # Formation
    r"empty\b": "formation:empty",
    r"trips\b": "formation:trips",
    r"bunch\b": "formation:bunch",
    r"quads\b": "formation:quads",
    r"cluster": "formation:cluster",
    r"unbalanced": "formation:unbalanced",
    r"tackle\s*over": "formation:tackle-over",
    r"4.?strong|four.?strong": "formation:four-strong",
    
    # Personnel
    r"11p\b|11\s*personnel": "personnel:11",
    r"12p\b|12\s*personnel": "personnel:12",
    r"13p\b|13\s*personnel": "personnel:13",
    r"21p\b|21\s*personnel": "personnel:21",
    r"22p\b|22\s*personnel": "personnel:22",
}

def extract_year(title: str) -> str | None:
    """Extract year from play title."""
    match = re.search(r'\b(20\d{2})\b', title)
    return match.group(1) if match else None


def extract_team(title: str) -> str | None:
    """Extract team name from play title."""
    # Pattern: "YYYY TeamName running/throwing/..."
    match = re.match(r'^(?:\d{4}\s+)?([A-Za-z][A-Za-z\s\-\.]+?)\s+(?:running|throwing|using|lining|faking|motioning)', title, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def extract_tags(title: str) -> list[str]:
    """Extract tags from play title using pattern matching."""
    tags = []
    title_lower = title.lower()
    
    for pattern, tag in TAG_PATTERNS.items():
        if re.search(pattern, title_lower):
            if tag not in tags:
                tags.append(tag)
    
    return tags


def analyze_plays(plays: list[dict]) -> dict:
    """Analyze plays and generate statistics."""
    year_counts = Counter()
    team_counts = Counter()
    tag_counts = Counter()
    untagged = []
    
    for play in plays:
        title = play.get("title", "")
        
        # Extract year
        year = extract_year(title)
        if year:
            year_counts[year] += 1
        
        # Extract team
        team = extract_team(title)
        if team:
            team_counts[team] += 1
        
        # Extract tags
        tags = extract_tags(title)
        if tags:
            for tag in tags:
                tag_counts[tag] += 1
        else:
            if title and title != "Untitled Play":
                untagged.append(title)
    
    return {
        "years": dict(year_counts.most_common()),
        "teams": dict(team_counts.most_common(30)),
        "tags": dict(tag_counts.most_common()),
        "untagged_count": len(untagged),
        "untagged_sample": untagged[:10],
        "total_plays": len(plays),
    }


def main():
    """Run analysis on plays.json."""
    if not PLAYS_JSON.exists():
        print(f"Error: {PLAYS_JSON} not found")
        return 1
    
    with open(PLAYS_JSON) as f:
        plays = json.load(f)
    
    print(f"Analyzing {len(plays)} plays...\n")
    
    results = analyze_plays(plays)
    
    print("=== YEARS ===")
    for year, count in results["years"].items():
        print(f"  {year}: {count}")
    
    print("\n=== TOP TEAMS (30) ===")
    for team, count in list(results["teams"].items())[:30]:
        print(f"  {team}: {count}")
    
    print("\n=== TAGS ===")
    for tag, count in results["tags"].items():
        print(f"  {tag}: {count}")
    
    print(f"\n=== COVERAGE ===")
    print(f"  Total plays: {results['total_plays']}")
    print(f"  Untagged: {results['untagged_count']}")
    print(f"  Coverage: {100 - (results['untagged_count'] / results['total_plays'] * 100):.1f}%")
    
    if results["untagged_sample"]:
        print("\n=== UNTAGGED SAMPLE (need patterns) ===")
        for title in results["untagged_sample"]:
            print(f"  - {title}")
    
    return 0


if __name__ == "__main__":
    exit(main())
