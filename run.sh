#!/bin/bash
cd ~/Projects/amazon-invoice-downloader
uv run amazon-invoice-downloader "$@"
echo ""
echo "📂 Sortiere PDFs in Buchhaltungsordner..."
./sort-to-buchhaltung.sh
