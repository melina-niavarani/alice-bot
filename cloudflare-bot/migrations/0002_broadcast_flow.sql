-- Each incoming update commits its draft, replies and campaign atomically.
CREATE TABLE IF NOT EXISTS bot_revision (
  id INTEGER PRIMARY KEY CHECK(id=1),
  version INTEGER NOT NULL
);
INSERT OR IGNORE INTO bot_revision(id,version) VALUES(1,0);
CREATE TABLE IF NOT EXISTS bot_events (
  event_key TEXT PRIMARY KEY,
  created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS campaign_meta (
  campaign INTEGER PRIMARY KEY,
  draft_key TEXT NOT NULL UNIQUE,
  notified INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS delivery_errors (
  outbox_id INTEGER PRIMARY KEY,
  reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS delivery_lock (
  id INTEGER PRIMARY KEY CHECK(id=1),
  owner TEXT NOT NULL DEFAULT '',
  expires INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO delivery_lock(id) VALUES(1);
