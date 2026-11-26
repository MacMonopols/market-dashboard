#!/bin/bash
cd /Users/chris/market-dashboard
# Get code changes made elsewhere (cloud sessions, GitHub Actions data runs).
# -X theirs settles the usual conflict on live_data.js, which fetch_data.py
# regenerates right after; on any other failure the app still starts.
echo "[$(date)] git pull" >> /tmp/market-dashboard.log
git pull --no-rebase --no-edit -X theirs >> /tmp/market-dashboard.log 2>&1 \
  || echo "[$(date)] ⚠ git pull failed — running with the local code" >> /tmp/market-dashboard.log
python3 fetch_data.py >> /tmp/market-dashboard.log 2>&1
open index.html
