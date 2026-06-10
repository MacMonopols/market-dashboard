#!/bin/bash
# Täglich 18:00: Daten holen und auf GitHub Pages pushen
set -e
cd /Users/chris/Desktop/market-dashboard

echo "[$(date)] Starte Update..." >> /tmp/market-dashboard-cron.log

python3 fetch_data.py >> /tmp/market-dashboard-cron.log 2>&1

git add live_data.js
git commit -m "data: $(date '+%Y-%m-%d %H:%M')" >> /tmp/market-dashboard-cron.log 2>&1
git push origin main >> /tmp/market-dashboard-cron.log 2>&1

echo "[$(date)] Update abgeschlossen." >> /tmp/market-dashboard-cron.log
