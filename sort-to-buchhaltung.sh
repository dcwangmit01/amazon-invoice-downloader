#!/bin/bash
BASE="/Users/koenigroland/Library/CloudStorage/SynologyDrive-praxis/Projekte/claude/Buchhaltung"
SRC="$HOME/Projects/amazon-invoice-downloader/downloads"

count=0
for pdf in "$SRC"/*.pdf; do
    [ -f "$pdf" ] || continue
    filename=$(basename "$pdf")
    year="${filename:0:4}"
    if [[ "$year" =~ ^20[2-3][0-9]$ ]]; then
        dest="$BASE/$year/amazon"
        mkdir -p "$dest"
        cp -n "$pdf" "$dest/"
        echo "✅ $filename → $dest/"
        ((count++))
    else
        echo "⚠️  $filename — Jahr '$year' nicht erkannt, übersprungen"
    fi
done
echo ""
echo "Fertig! $count PDFs sortiert."
