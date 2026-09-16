#!/bin/bash
cd /home/hp/trading-data-engine
/home/hp/trading-data-engine/.venv/bin/python -m src.market_collector >> logs/market_collector.log 2>&1
