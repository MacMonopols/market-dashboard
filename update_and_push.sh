#!/bin/bash
cd /Users/chris/Desktop/market-dashboard
echo "[$(date)] Starte Update..." >> /tmp/market-dashboard-cron.log
python3 fetch_data.py >> /tmp/market-dashboard-cron.log 2>&1
echo "[$(date)] Update abgeschlossen." >> /tmp/market-dashboard-cron.log
