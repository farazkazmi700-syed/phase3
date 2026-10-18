import sqlite3

from flask import g

from .config import Config


def configure_connection(db):
    """Apply SQLite settings that must be enabled for every connection."""
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    return db


def get_db():
    """Open or reuse the SQLite database connection for the current request."""
    if "db" not in g:
        g.db = configure_connection(
            sqlite3.connect(Config.DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        )
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(error=None):
    """Close the SQLite database connection when the request ends."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the app tables needed for users, chats, and feedback."""
    db = configure_connection(sqlite3.connect(Config.DATABASE_PATH))
    db.execute("PRAGMA journal_mode = WAL")
    cursor = db.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id              TEXT PRIMARY KEY,
            google_id       TEXT UNIQUE NOT NULL,
            email           TEXT UNIQUE NOT NULL,
            name            TEXT,
            picture_url     TEXT,
            created_at      TEXT NOT NULL
        )
        """
    )

    # FR7: chat_sessions stores one unique conversation container per chat.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            title       TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    # FR7/FR11: messages are scoped by session_id and store each interaction's
    # user/model text, timestamp, topic label, and response timing metadata.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL,
            user_id     TEXT NOT NULL,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            topic_label TEXT,
            created_at  TEXT NOT NULL,
            request_started_at  TEXT,
            response_received_at TEXT,
            response_time_ms     INTEGER,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id              TEXT PRIMARY KEY,
            message_id      TEXT NOT NULL UNIQUE,
            session_id      TEXT NOT NULL,
            user_id         TEXT NOT NULL,
            rating          INTEGER,
            correctness     TEXT,
            length_type     TEXT,
            comment         TEXT,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES messages(id),
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    # FR22: analytics_summaries stores one permanent record per signed-in session.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_summaries (
            id               TEXT PRIMARY KEY,
            user_id          TEXT NOT NULL,
            session_id       TEXT NOT NULL,
            overall_accuracy REAL,
            avg_rating       REAL,
            correct_count    INTEGER,
            partial_count    INTEGER,
            incorrect_count  INTEGER,
            total_messages   INTEGER,
            created_at       TEXT NOT NULL
        )
        """
    )

    db.commit()

    # Remove deprecated feedback stores from existing local databases.
    cursor.execute("DROP TABLE IF EXISTS logout_feedback")
    cursor.execute("DROP TABLE IF EXISTS general_feedback")
    cursor.execute("DROP TABLE IF EXISTS general_feedback_starts")

    # Existing databases need a table rebuild because SQLite cannot add a
    # foreign-key constraint to an existing table with ALTER TABLE.
    feedback_fks = {
        (row[2], row[3])
        for row in cursor.execute("PRAGMA foreign_key_list(feedback)").fetchall()
    }
    required_fks = {
        ("message_id", "messages"),
        ("session_id", "chat_sessions"),
        ("user_id", "users"),
    }
    if not required_fks.issubset(feedback_fks):
        cursor.execute("ALTER TABLE feedback RENAME TO feedback_old")
        cursor.execute(
            """
            CREATE TABLE feedback (
                id              TEXT PRIMARY KEY,
                message_id      TEXT NOT NULL UNIQUE,
                session_id      TEXT NOT NULL,
                user_id         TEXT NOT NULL,
                rating          INTEGER,
                correctness     TEXT,
                length_type     TEXT,
                comment         TEXT,
                created_at      TEXT NOT NULL,
                FOREIGN KEY (message_id) REFERENCES messages(id),
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO feedback
            (id, message_id, session_id, user_id, rating, correctness,
             length_type, comment, created_at)
            SELECT id, message_id, session_id, user_id, rating, correctness,
                   length_type, comment, created_at
            FROM feedback_old
            """
        )
        cursor.execute("DROP TABLE feedback_old")
    db.commit()

    # Keep old local databases compatible with the current feedback form.
    feedback_columns = [row[1] for row in cursor.execute("PRAGMA table_info(feedback)").fetchall()]
    if "comment" not in feedback_columns:
        cursor.execute("ALTER TABLE feedback ADD COLUMN comment TEXT")
        db.commit()

    # Enforce one feedback row per assistant message at the database level.
    # If a legacy database contains duplicates, retain the newest row first.
    cursor.execute(
        """
        DELETE FROM feedback
        WHERE rowid NOT IN (
            SELECT MAX(rowid)
            FROM feedback
            GROUP BY message_id
        )
        """
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_feedback_message_id_unique "
        "ON feedback(message_id)"
    )
    db.commit()

    # FR10: keep old message tables compatible with response-time tracking.
    message_columns = [row[1] for row in cursor.execute("PRAGMA table_info(messages)").fetchall()]
    if "request_started_at" not in message_columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN request_started_at TEXT")
    if "response_received_at" not in message_columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN response_received_at TEXT")
    if "response_time_ms" not in message_columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN response_time_ms INTEGER")
    # FR11: topic_label lets every stored user/model interaction be grouped by topic.
    if "topic_label" not in message_columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN topic_label TEXT")
    db.commit()

    db.close()
