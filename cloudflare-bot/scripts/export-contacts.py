"""Export current local members and registered destinations to a private D1 SQL file."""

import argparse
import sqlite3
from pathlib import Path


def quote(value):
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error("local SQLite database not found")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error("output already exists; choose a fresh private path")
    with sqlite3.connect(args.source) as db, args.output.open("x", encoding="utf-8") as out:
        out.write("-- Alice member and destination migration. Keep this file private.\n")
        for row in db.execute("SELECT platform,chat,name,subscribed,news_opt_out,interest,created FROM members"):
            out.write("INSERT OR REPLACE INTO members(platform,chat,name,subscribed,news_opt_out,interest,created) VALUES (" + ",".join(map(quote, row)) + ");\n")
        for platform, table in (("telegram", "destinations"), ("bale", "bale_destinations")):
            for chat, title, active in db.execute(f"SELECT chat,title,active FROM {table}"):
                # The old database has no kind column. Bale destinations are
                # channels in the current setup; Telegram destinations are groups.
                kind = "channel" if platform == "bale" else "group"
                out.write("INSERT OR REPLACE INTO destinations(platform,chat,title,kind,active) VALUES (" + ",".join(map(quote, (platform, chat, title, kind, active))) + ");\n")


if __name__ == "__main__":
    main()
