#!/bin/bash
# GIF to MP4 Conversion Script
# Converts all *_angle1.gif and *_angle2.gif files to MP4 format
# Keeps originals as backup and reports size savings

set -e

MEDIA_DIR="media"
ORIGINALS_DIR="media/originals"
TOTAL_GIF_SIZE=0
TOTAL_MP4_SIZE=0

# Create originals backup directory
mkdir -p "$ORIGINALS_DIR"

echo "🏈 One Play a Day - GIF to MP4 Conversion"
echo "=========================================="
echo ""

# Find all angle GIF files
GIF_FILES=$(find "$MEDIA_DIR" -maxdepth 1 -type f \( -name "*_angle1.gif" -o -name "*_angle2.gif" \) | sort)

if [ -z "$GIF_FILES" ]; then
    echo "❌ No GIF files found in $MEDIA_DIR"
    exit 1
fi

echo "Found GIF files to convert:"
echo "$GIF_FILES" | sed 's/^/  - /'
echo ""

# Process each GIF
for gif_file in $GIF_FILES; do
    filename=$(basename "$gif_file")
    basename="${filename%.gif}"
    mp4_file="$MEDIA_DIR/${basename}.mp4"
    
    # Get original size
    gif_size=$(stat -c%s "$gif_file" 2>/dev/null || stat -f%z "$gif_file" 2>/dev/null)
    TOTAL_GIF_SIZE=$((TOTAL_GIF_SIZE + gif_size))
    
    echo "Converting: $filename"
    
    # Convert GIF to MP4 with web-optimized settings
    ffmpeg -i "$gif_file" \
        -movflags faststart \
        -pix_fmt yuv420p \
        -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
        -y \
        "$mp4_file" \
        -loglevel error
    
    # Get new size
    mp4_size=$(stat -c%s "$mp4_file" 2>/dev/null || stat -f%z "$mp4_file" 2>/dev/null)
    TOTAL_MP4_SIZE=$((TOTAL_MP4_SIZE + mp4_size))
    
    # Calculate savings
    savings=$((gif_size - mp4_size))
    savings_pct=$((savings * 100 / gif_size))
    
    echo "  ✅ $filename → ${basename}.mp4"
    echo "     GIF: $(numfmt --to=iec-i --suffix=B $gif_size) → MP4: $(numfmt --to=iec-i --suffix=B $mp4_size)"
    echo "     Saved: $(numfmt --to=iec-i --suffix=B $savings) ($savings_pct%)"
    echo ""
    
    # Move original to backup
    mv "$gif_file" "$ORIGINALS_DIR/"
done

# Final report
echo "=========================================="
echo "✨ Conversion Complete!"
echo ""
echo "Total GIF size:  $(numfmt --to=iec-i --suffix=B $TOTAL_GIF_SIZE)"
echo "Total MP4 size:  $(numfmt --to=iec-i --suffix=B $TOTAL_MP4_SIZE)"
echo "Total saved:     $(numfmt --to=iec-i --suffix=B $((TOTAL_GIF_SIZE - TOTAL_MP4_SIZE)))"
echo "Overall savings: $(( (TOTAL_GIF_SIZE - TOTAL_MP4_SIZE) * 100 / TOTAL_GIF_SIZE ))%"
echo ""
echo "Original GIFs backed up to: $ORIGINALS_DIR"
