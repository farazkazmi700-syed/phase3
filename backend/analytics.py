"""
analytics.py — Phase 3 Analytics System (FR14–FR22)

Blueprint exposing three routes:
  GET  /analytics               → render the analytics dashboard page
  GET  /api/analytics/data      → return full computed JSON payload
"""

import re
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, render_template

from .db import get_db
from .utils import current_user, current_user_id, now_iso, require_login

analytics_bp = Blueprint("analytics", __name__)

# ---------------------------------------------------------------------------
# FR15: canonical topic domains mapped from the raw topic_label keywords.
# The first matching keyword wins; Machine Learning is the fallback.
# ---------------------------------------------------------------------------
TOPIC_MAP = [
    ("Machine Learning",  ["machine learning", "ml", "regression", "classification",
                           "clustering", "supervised", "unsupervised", "sklearn",
                           "scikit", "random forest", "gradient", "xgboost"]),
    ("Deep Learning",     ["deep learning", "neural", "cnn", "rnn", "lstm", "transformer",
                           "attention", "pytorch", "tensorflow", "keras", "backprop",
                           "activation", "epoch", "batch", "embedding", "bert", "gpt"]),
    ("Healthcare AI",     ["healthcare", "medical", "diagnosis", "patient", "clinical",
                           "disease", "drug", "hospital", "ehr", "radiology",
                           "treatment", "symptom", "cancer", "health"]),
    ("Power Systems",     ["power", "energy", "grid", "electricity", "voltage",
                           "load forecasting", "renewable", "solar", "wind",
                           "battery", "inverter", "transformer", "scada"]),
    ("E-commerce AI",     ["ecommerce", "e-commerce", "recommendation", "product",
                           "shopping", "cart", "checkout", "price", "inventory",
                           "customer", "fraud", "personalisation", "personaliz"]),
]
TOPIC_DOMAINS = tuple(domain for domain, _ in TOPIC_MAP)
TOPIC_PATTERNS = tuple(
    (
        domain,
        tuple(
            re.compile(rf"(?<!\w){re.escape(keyword)}s?(?!\w)", re.IGNORECASE)
            for keyword in keywords
        ),
    )
    for domain, keywords in TOPIC_MAP
)

PHASES = ("Start", "Middle", "End")


# ---------------------------------------------------------------------------
# FR14: Data retrieval
# ---------------------------------------------------------------------------

def fetch_session_data(user_id: str) -> list[dict]:
    """
    FR14: Retrieve every assistant message together with its feedback for the
    given user.  Returns a list of plain dicts so they can be processed and
    serialised without depending on sqlite3.Row.
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT
            m.id            AS message_id,
            m.session_id,
            m.content,
            m.topic_label,
                        (
                                SELECT u.content
                                FROM messages u
                                WHERE u.session_id = m.session_id
                                    AND u.user_id = m.user_id
                                    AND u.role = 'user'
                                    AND u.rowid < m.rowid
                                ORDER BY u.rowid DESC
                                LIMIT 1
                        ) AS user_message,
            m.created_at,
            m.response_time_ms,
            f.rating,
            f.correctness,
            f.length_type
        FROM   messages m
        LEFT   JOIN feedback f ON f.message_id = m.id
        WHERE  m.user_id = ?
          AND  m.role    = 'assistant'
        ORDER  BY m.created_at ASC
        """,
        (user_id,),
    ).fetchall()

    return [dict(r) for r in rows]


def fetch_session_list(user_id: str) -> list[dict]:
    """Return basic info for each session owned by the user."""
    db = get_db()
    rows = db.execute(
        """
        SELECT id, title, created_at, updated_at
        FROM   chat_sessions
        WHERE  user_id = ?
        ORDER  BY created_at DESC
        """,
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# FR15: Topic classification
# ---------------------------------------------------------------------------

def classify_topic(label: str | None) -> str:
    """
    FR15: Map a raw topic_label string to one of the five canonical domains.
    Matching is case-insensitive whole-keyword scoring; the strongest match wins.
    Returns 'Machine Learning' if no keyword matches.
    """
    if not label:
        return TOPIC_DOMAINS[0]

    best_domain = TOPIC_DOMAINS[0]
    best_score = 0
    for domain, patterns in TOPIC_PATTERNS:
        score = sum(pattern.search(label) is not None for pattern in patterns)
        if score > best_score:
            best_domain = domain
            best_score = score
    return best_domain


# ---------------------------------------------------------------------------
# FR16: Session segmentation
# ---------------------------------------------------------------------------

def segment_phase(index: int, total: int) -> str:
    """
    FR16: Divide messages within a session into Start / Middle / End thirds.
    index  – 0-based position of the message within the session.
    total  – total number of assistant messages in the session.
    """
    if total <= 1:
        return "Start"
    third = total / 3
    if index < third:
        return "Start"
    if index < 2 * third:
        return "Middle"
    return "End"


# ---------------------------------------------------------------------------
# FR17 / FR18 / FR19: Metric computation
# ---------------------------------------------------------------------------

def compute_metrics(rows: list[dict]) -> dict:
    """
    FR17/FR18/FR19: Compute all analytics metrics from the flat list of rows
    returned by fetch_session_data().

    Returns a nested dict consumed directly by the frontend JSON payload.
    """
    # ---- per-session grouping so we can apply phase segmentation (FR16) ----
    sessions: dict[str, list[dict]] = {}
    for row in rows:
        sessions.setdefault(row["session_id"], []).append(row)

    # Augment each row with its classified topic and phase label.
    for session_rows in sessions.values():
        total = len(session_rows)
        for idx, row in enumerate(session_rows):
            row["topic"] = classify_topic(row.get("user_message") or row.get("topic_label"))
            row["phase"] = segment_phase(idx, total)

    # Flatten back to a single list for aggregate calculations.
    all_rows = [row for session_rows in sessions.values() for row in session_rows]

    # ---- FR18: correctness counts ----------------------------------------
    correct_count   = sum(1 for r in all_rows if r.get("correctness") == "Correct")
    partial_count   = sum(1 for r in all_rows if r.get("correctness") == "Partial")
    incorrect_count = sum(1 for r in all_rows if r.get("correctness") == "Incorrect")
    rated_count     = correct_count + partial_count + incorrect_count

    # Accuracy per reply: weight Correct=1, Partial=0.5, Incorrect=0.
    def reply_accuracy(row: dict) -> float | None:
        c = row.get("correctness")
        if c == "Correct":   return 1.0
        if c == "Partial":   return 0.5
        if c == "Incorrect": return 0.0
        return None  # no feedback yet

    # FR17: overall accuracy percentage (only rated replies)
    rated_rows    = [r for r in all_rows if reply_accuracy(r) is not None]
    overall_acc   = (
        round(
            (sum(reply_accuracy(r) for r in rated_rows) / len(rated_rows)) * 100, 1
        ) if rated_rows else 0.0
    )
    overall_correctness_pct = round(
        (correct_count / rated_count * 100) if rated_count else 0.0, 1
    )

    # ---- FR17: accuracy per topic ----------------------------------------
    topic_stats: dict[str, dict] = {
        domain: {"count": 0, "acc_sum": 0.0, "rated": 0}
        for domain in TOPIC_DOMAINS
    }
    for row in all_rows:
        t = row["topic"]
        if t not in topic_stats:
            topic_stats[t] = {"count": 0, "acc_sum": 0.0, "rated": 0}
        topic_stats[t]["count"] += 1
        acc = reply_accuracy(row)
        if acc is not None:
            topic_stats[t]["acc_sum"] += acc
            topic_stats[t]["rated"]   += 1

    topic_accuracy = {
        t: {
            "count": v["count"],
            "accuracy": round((v["acc_sum"] / v["rated"] * 100), 1) if v["rated"] else 0.0,
            "rated": v["rated"],
        }
        for t, v in topic_stats.items()
    }

    # ---- FR17: accuracy per phase ----------------------------------------
    phase_stats: dict[str, dict] = {}
    for row in all_rows:
        p = row["phase"]
        if p not in phase_stats:
            phase_stats[p] = {"acc_sum": 0.0, "rated": 0, "count": 0}
        phase_stats[p]["count"] += 1
        acc = reply_accuracy(row)
        if acc is not None:
            phase_stats[p]["acc_sum"] += acc
            phase_stats[p]["rated"]   += 1

    phase_accuracy = {
        p: round((phase_stats[p]["acc_sum"] / phase_stats[p]["rated"] * 100), 1)
        if phase_stats[p]["rated"] else 0.0
        for p in PHASES
        if p in phase_stats
    }
    # Ensure all three phases exist in output (even with 0.0) for the chart.
    for p in PHASES:
        phase_accuracy.setdefault(p, 0.0)

    # ---- FR17: response time statistics ----------------------------------
    times = [r["response_time_ms"] for r in all_rows if r.get("response_time_ms") is not None]
    response_time_stats = {
        "min":    min(times) if times else 0,
        "max":    max(times) if times else 0,
        "avg":    round(sum(times) / len(times), 1) if times else 0,
        "count":  len(times),
        # Per-reply list for the trend line graph (FR20).
        "series": [r.get("response_time_ms") or 0 for r in all_rows],
    }

    # ---- FR17: rating averages -------------------------------------------
    ratings = [r["rating"] for r in all_rows if r.get("rating") is not None]
    rating_dist = {str(i): ratings.count(i) for i in range(1, 5)}
    avg_rating  = round(sum(ratings) / len(ratings), 2) if ratings else 0.0

    # ---- FR17: length distribution ---------------------------------------
    lengths = [r.get("length_type") for r in all_rows if r.get("length_type")]
    length_dist = {
        "Short":        lengths.count("Short"),
        "To the Point": lengths.count("To the Point"),
        "Lengthy":      lengths.count("Lengthy"),
    }

    # ---- per-reply accuracy list for bar chart (FR20) --------------------
    reply_accuracy_series = [
        {
            "index":       i + 1,
            "session_id":  row["session_id"][:8],
            "topic":       row["topic"],
            "phase":       row["phase"],
            "correctness": row.get("correctness", "—"),
            "accuracy":    round((reply_accuracy(row) or 0) * 100, 0),
            "rating":      row.get("rating"),
            "length":      row.get("length_type", "—"),
            "response_ms": row.get("response_time_ms"),
            "timestamp":   row.get("created_at"),
        }
        for i, row in enumerate(all_rows)
    ]

    # ---- session-level insights ------------------------------------------
    session_insights = []
    for session_id, session_rows in sessions.items():
        s_rated = [r for r in session_rows if reply_accuracy(r) is not None]
        s_acc   = (
            round(
                sum(reply_accuracy(r) for r in s_rated) / len(s_rated) * 100, 1
            ) if s_rated else None
        )
        s_ratings = [r["rating"] for r in session_rows if r.get("rating")]
        session_insights.append({
            "session_id":   session_id[:8],
            "full_id":      session_id,
            "message_count": len(session_rows),
            "topics":       list({r["topic"] for r in session_rows}),
            "accuracy":     s_acc,
            "avg_rating":   round(sum(s_ratings) / len(s_ratings), 2) if s_ratings else None,
            "created_at":   session_rows[0].get("created_at") if session_rows else None,
        })

    return {
        # ---- summary KPIs ------------------------------------------------
        "total_sessions":       len(sessions),
        "total_messages":       len(all_rows),
        "overall_accuracy":     overall_acc,
        "overall_correctness_pct": overall_correctness_pct,
        "avg_rating":           avg_rating,
        # ---- FR18: correctness counts ------------------------------------
        "correct_count":        correct_count,
        "partial_count":        partial_count,
        "incorrect_count":      incorrect_count,
        "rated_count":          rated_count,
        # ---- FR17: metric tables & graph data ----------------------------
        "topic_accuracy":       topic_accuracy,
        "phase_accuracy":       phase_accuracy,
        "response_time_stats":  response_time_stats,
        "rating_distribution":  rating_dist,
        "length_distribution":  length_dist,
        # ---- FR20: per-reply series for charts ---------------------------
        "reply_accuracy_series": reply_accuracy_series,
        # ---- FR21: session insights --------------------------------------
        "session_insights":     session_insights,
    }


def build_analytics_payload(user_id: str) -> dict:
    """Combine raw data retrieval and metric computation into one payload."""
    rows    = fetch_session_data(user_id)
    metrics = compute_metrics(rows)
    return metrics


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@analytics_bp.route("/analytics")
@require_login
def analytics_page():
    """FR21: Render the analytics dashboard page."""
    return render_template("analytics.html", user=current_user())


@analytics_bp.route("/api/analytics/data")
@require_login
def analytics_data():
    """FR14–FR21: Return the full analytics JSON payload for the dashboard."""
    try:
        payload = build_analytics_payload(current_user_id())
        return jsonify(payload)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def save_final_analytics_summary(user_id: str, session_id: str) -> str:
    """Permanently save one account summary for a signed-in session."""
    db = get_db()
    existing = db.execute(
        "SELECT id FROM analytics_summaries WHERE user_id = ? AND session_id = ?",
        (user_id, session_id),
    ).fetchone()
    if existing:
        return existing["id"]

    payload = build_analytics_payload(user_id)
    summary_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO analytics_summaries
        (id, user_id, session_id, overall_accuracy, avg_rating,
         correct_count, partial_count, incorrect_count,
         total_messages, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            summary_id,
            user_id,
            session_id,
            payload["overall_accuracy"],
            payload["avg_rating"],
            payload["correct_count"],
            payload["partial_count"],
            payload["incorrect_count"],
            payload["total_messages"],
            now_iso(),
        ),
    )
    db.commit()
    return summary_id
