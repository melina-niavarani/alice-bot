#!/bin/sh
cd "$(dirname "$0")" || exit 1
if [ -x /opt/anaconda3/bin/python3 ]; then
  exec /opt/anaconda3/bin/python3 bot.py
fi
exec python3 bot.py
