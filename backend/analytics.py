"""
analytics.py — Phase 3 Analytics System (FR14–FR22)

Blueprint exposing three routes:
  GET  /analytics               → render the analytics dashboard page
  GET  /api/analytics/data      → return full computed JSON payload
"""

import re
import json

from flask import Blueprint, jsonify, render_template, request

from .db import get_db
from .utils import current_user, current_user_id, now_iso, require_login

analytics_bp = Blueprint("analytics", __name__)

# ---------------------------------------------------------------------------
# FR15: the only valid topic domains, mapped from user-message keywords.
# Every message is assigned to a subject domain, including unmatched messages.
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
                           "battery", "inverter", "scada"]),
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

def fetch_session_data(user_id: str, session_id: str | None = None) -> list[dict]:
    """
    FR14: Retrieve assistant messages with their interaction's stored user
    topic and associated feedback, scoped to the supplied user. Returns plain
    dictionaries for analytics processing and JSON serialization.
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT
            m.id            AS message_id,
            m.session_id,
            m.content,
            COALESCE(user_message.topic_label, m.topic_label) AS topic_label,
            m.created_at,
            m.response_time_ms,
            f.rating,
            f.correctness,
            f.length_type
        FROM   messages m
        LEFT   JOIN feedback f ON f.message_id = m.id
        LEFT   JOIN messages user_message
               ON user_message.session_id = m.session_id
              AND user_message.user_id = m.user_id
              AND user_message.role = 'user'
              AND user_message.created_at <= m.created_at
              AND user_message.rowid = (
                  SELECT MAX(prior_user.rowid)
                  FROM messages prior_user
                  WHERE prior_user.session_id = m.session_id
                    AND prior_user.user_id = m.user_id
                    AND prior_user.role = 'user'
                    AND prior_user.created_at <= m.created_at
              )
        WHERE  m.user_id = ?
          AND  m.role    = 'assistant'
          AND  (? IS NULL OR m.session_id = ?)
        ORDER  BY m.created_at ASC, m.rowid ASC
        """,
        (user_id, session_id, session_id),
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
    FR15: Map a user message to one canonical domain.
    Matching is case-insensitive whole-keyword scoring; the strongest match wins.
    Messages without a keyword match are assigned to the most relevant subject
    domain by default, ensuring there is no uncategorized category.
    """
    if not label:
        return "Machine Learning"

    best_domain = "Machine Learning"
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

    # Augment each response with its interaction topic and phase label.
    for session_rows in sessions.values():
        total = len(session_rows)
        for idx, row in enumerate(session_rows):
            stored_topic = row.get("topic_label")
            row["topic"] = stored_topic if stored_topic in TOPIC_DOMAINS else classify_topic(row.get("content"))
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
    phase_stats: dict[str, dict] = {
        phase: {"acc_sum": 0.0, "rated": 0, "count": 0}
        for phase in PHASES
    }
    for row in all_rows:
        p = row["phase"]
        phase_stats[p]["count"] += 1
        acc = reply_accuracy(row)
        if acc is not None:
            phase_stats[p]["acc_sum"] += acc
            phase_stats[p]["rated"]   += 1

    phase_accuracy = {
        p: round((phase_stats[p]["acc_sum"] / phase_stats[p]["rated"] * 100), 1)
        if phase_stats[p]["rated"] else 0.0
        for p in PHASES
    }
    phase_rated = {p: phase_stats[p]["rated"] for p in PHASES}

    # ---- FR17: response time statistics ----------------------------------
    timed_rows = [r for r in all_rows if r.get("response_time_ms") is not None]
    times = [r["response_time_ms"] for r in timed_rows]
    response_time_stats = {
        "min":    min(times) if times else 0,
        "max":    max(times) if times else 0,
        "avg":    round(sum(times) / len(times), 1) if times else 0,
        "count":  len(times),
        # Preserve gaps for replies without a measured response time.
        "series": [r.get("response_time_ms") for r in all_rows],
        "labels": [r["created_at"] for r in all_rows],
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
            "correctness": row.get("correctness") or "—",
            "accuracy":    round(reply_accuracy(row) * 100, 0) if reply_accuracy(row) is not None else None,
            "rating":      row.get("rating"),
            "length":      row.get("length_type") or "—",
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
            "rated_count":  len(s_rated),
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
        "avg_rating_count":     len(ratings),
        # ---- FR18: correctness counts ------------------------------------
        "correct_count":        correct_count,
        "partial_count":        partial_count,
        "incorrect_count":      incorrect_count,
        "rated_count":          rated_count,
        # ---- FR17: metric tables & graph data ----------------------------
        "topic_accuracy":       topic_accuracy,
        "accuracy_rated_count": len(rated_rows),
        "phase_accuracy":       phase_accuracy,
        "phase_rated":          phase_rated,
        "phase_counts":         {p: phase_stats[p]["count"] for p in PHASES},
        "response_time_stats":  response_time_stats,
        "rating_distribution":  rating_dist,
        "rating_count":         len(ratings),
        "length_distribution":  length_dist,
        "length_count":         len(lengths),
        # ---- FR20: per-reply series for charts ---------------------------
        "reply_accuracy_series": reply_accuracy_series,
        # ---- FR21: session insights --------------------------------------
        "session_insights":     session_insights,
    }


def build_analytics_payload(user_id: str, session_id: str | None = None) -> dict:
    """Combine raw data retrieval and metric computation into one payload."""
    rows    = fetch_session_data(user_id, session_id)
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
    """FR14–FR21: Return full analytics or data for one owned session."""
    try:
        session_id = request.args.get("session_id") or None
        if session_id:
            owned_session = get_db().execute(
                "SELECT 1 FROM chat_sessions WHERE id = ? AND user_id = ?",
                (session_id, current_user_id()),
            ).fetchone()
            if not owned_session:
                return jsonify({"error": "Session not found."}), 404
        payload = build_analytics_payload(current_user_id(), session_id)
        return jsonify(payload)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def save_final_analytics_summary(user_id: str, session_id: str) -> str:
    """Persist one summary for the ended chat session, if it has responses."""
    db = get_db()
    session = db.execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    ).fetchone()
    if not session:
        raise ValueError("Chat session not found for analytics summary.")

    existing = db.execute(
        "SELECT session_id FROM analytics_summaries WHERE user_id = ? AND session_id = ?",
        (user_id, session_id),
    ).fetchone()
    if existing:
        return existing["session_id"]

    payload = build_analytics_payload(user_id, session_id)
    if payload["total_messages"] == 0:
        return session_id

    db.execute(
        """
        INSERT OR IGNORE INTO analytics_summaries
        (session_id, user_id, overall_accuracy, avg_rating,
         correct_count, partial_count, incorrect_count, total_messages,
         topic_breakdown, phase_breakdown, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            session_id,
            user_id,
            payload["overall_accuracy"],
            payload["avg_rating"],
            payload["correct_count"],
            payload["partial_count"],
            payload["incorrect_count"],
            payload["total_messages"],
            json.dumps(payload["topic_accuracy"]),
            json.dumps(payload["phase_accuracy"]),
            now_iso(),
        ),
    )
    db.commit()
    return session_id
