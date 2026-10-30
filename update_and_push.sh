#!/bin/bash
cd /Users/chris/market-dashboard || { echo "[$(date)] ERROR: repo directory not found" >> /tmp/market-dashboard-cron.log; exit 1; }

echo "[$(date)] Starte Update..." >> /tmp/market-dashboard-cron.log

git pull --ff-only >> /tmp/market-dashboard-cron.log 2>&1
if [ $? -ne 0 ]; then
  echo "[$(date)] ERROR: git pull failed (local repo diverged from origin) - aborting to avoid push conflict" >> /tmp/market-dashboard-cron.log
  exit 1
fi

python3 fetch_data.py >> /tmp/market-dashboard-cron.log 2>&1

echo "[$(date)] Update abgeschlossen." >> /tmp/market-dashboard-cron.log
