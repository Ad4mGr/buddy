PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    discord_id      TEXT PRIMARY KEY,
    username        TEXT NOT NULL,
    timezone        TEXT NOT NULL DEFAULT 'UTC',
    freeze_tokens   INTEGER NOT NULL DEFAULT 3,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS goals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id          TEXT NOT NULL REFERENCES users(discord_id) ON DELETE CASCADE,
    server_id           TEXT NOT NULL,
    title               TEXT NOT NULL,
    description         TEXT,
    category            TEXT NOT NULL DEFAULT 'other',
    frequency           TEXT NOT NULL DEFAULT 'daily',
    interval_days       INTEGER NOT NULL DEFAULT 1,
    checkin_hour        INTEGER NOT NULL DEFAULT 21,
    start_date          DATE NOT NULL DEFAULT (date('now')),
    end_date            DATE,
    status              TEXT NOT NULL DEFAULT 'active',
    stake_miss_count    INTEGER,
    stake_role_id       TEXT,
    stake_public_shame  INTEGER NOT NULL DEFAULT 0,
    created_at          DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS streaks (
    goal_id             INTEGER PRIMARY KEY REFERENCES goals(id) ON DELETE CASCADE,
    current_streak      INTEGER NOT NULL DEFAULT 0,
    longest_streak      INTEGER NOT NULL DEFAULT 0,
    last_checkin_date   DATE,
    updated_at          DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS checkins (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id     INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    discord_id  TEXT NOT NULL REFERENCES users(discord_id) ON DELETE CASCADE,
    status      TEXT NOT NULL,
    note        TEXT,
    checked_at  DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id         INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    discord_id      TEXT NOT NULL REFERENCES users(discord_id) ON DELETE CASCADE,
    scheduled_for   DATETIME NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS server_config (
    server_id                   TEXT PRIMARY KEY,
    accountability_channel_id   TEXT,
    digest_channel_id           TEXT,
    shame_pings_enabled         INTEGER NOT NULL DEFAULT 0,
    digest_day                  TEXT NOT NULL DEFAULT 'sunday',
    digest_hour                 INTEGER NOT NULL DEFAULT 9,
    created_at                  DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cheers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    checkin_id      INTEGER NOT NULL REFERENCES checkins(id) ON DELETE CASCADE,
    cheerer_id      TEXT NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS milestones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id         INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    streak_count    INTEGER NOT NULL,
    celebrated_at   DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_goals_discord_id ON goals(discord_id);
CREATE INDEX IF NOT EXISTS idx_goals_server_id ON goals(server_id);
CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
CREATE INDEX IF NOT EXISTS idx_checkins_goal_id ON checkins(goal_id);
CREATE INDEX IF NOT EXISTS idx_checkins_checked_at ON checkins(checked_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_status ON scheduled_jobs(status);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_scheduled_for ON scheduled_jobs(scheduled_for);
CREATE INDEX IF NOT EXISTS idx_cheers_checkin_id ON cheers(checkin_id);
CREATE INDEX IF NOT EXISTS idx_milestones_goal_id ON milestones(goal_id);
