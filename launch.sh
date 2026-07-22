#!/bin/bash
cd /Users/chris/market-dashboard
python3 fetch_data.py >> /tmp/market-dashboard.log 2>&1
open index.html
