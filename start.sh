#!/bin/bash
python -m playwright install chromium
gunicorn --bind 0.0.0.0:$PORT council_api_v4:app
