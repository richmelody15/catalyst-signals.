#!/bin/bash
export USE_IQ_OPTION=False
export USE_POCKET_OPTION=False
export NEWS_FILTER_ENABLED=False
export ENTRY_CONFIRM_ENABLED=False
export TELEGRAM_TOKEN=""
export TELEGRAM_CHAT_ID=""
export IQ_EMAIL="demo@example.com"
export IQ_PASSWORD="demo"
export PO_EMAIL="demo@example.com"
export PO_PASSWORD="demo"

cd /home/z/my-project/download
exec python catalyst_final.py
