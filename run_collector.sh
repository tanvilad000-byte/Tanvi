#!/bin/bash
cd /home/hp/trading-data-engine
/home/hp/trading-data-engine/.venv/bin/python -m src.news_collector >> logs/collector.log 2>&1
