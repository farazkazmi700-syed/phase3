import uuid
from datetime import datetime

from flask import Blueprint, jsonify, render_template

from .db import get_db
from .utils import current_user, current_user_id, json_payload, now_iso, require_login

feedback_bp = Blueprint("feedback", __name__)


@feedback_bp.route("/feedback")
@require_login
def feedback_page():
    """Render the feedback page for general or message-specific feedback."""
    return render_template("feedback.html", user=current_user())


@feedback_bp.route("/api/feedback", methods=["POST"])
@require_login
def submit_feedback():
    """FR12: save required response feedback before the user can continue chatting."""
    data = json_payload()
    message_id = data.get("message_id")
    session_id = data.get("session_id")
    rating = data.get("rating")
    correctness = data.get("correctness")
    length_type = data.get("length_type") or data.get("length_rating")
    comment = data.get("comment")

    db = get_db()
    if not message_id or not session_id:
        db.execute(
            """
            INSERT INTO general_feedback
            (id, user_id, rating, correctness, length_type, comment, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                str(uuid.uuid4()),
                current_user_id(),
                rating,
                correctness,
                length_type,
                comment,
                now_iso(),
            ),
        )
        db.commit()
        return jsonify({"success": True, "scope": "general"})

    # FR12: message feedback is mandatory and must include all required fields.
    if rating not in (1, 2, 3, 4):
        return jsonify({"error": "Rating from 1 to 4 is required."}), 400
    if correctness not in ("Correct", "Partial", "Incorrect"):
        return jsonify({"error": "Correctness must be Correct, Partial, or Incorrect."}), 400
    if length_type not in ("Short", "To the Point", "Lengthy"):
        return jsonify({"error": "Length type must be Short, To the Point, or Lengthy."}), 400

    message = db.execute(
        """
        SELECT id FROM messages
        WHERE id = ? AND session_id = ? AND user_id = ? AND role = 'assistant'
        """,
        (message_id, session_id, current_user_id()),
    ).fetchone()

    if not message:
        return jsonify({"error": "Assistant message not found."}), 404

    existing = db.execute(
        "SELECT id FROM feedback WHERE message_id = ? AND user_id = ?",
        (message_id, current_user_id()),
    ).fetchone()

    if existing:
        db.execute(
            "UPDATE feedback SET rating = ?, correctness = ?, length_type = ?, comment = ? WHERE message_id = ? AND user_id = ?",
            (rating, correctness, length_type, comment, message_id, current_user_id()),
        )
    else:
        db.execute(
            "INSERT INTO feedback (id, message_id, session_id, user_id, rating, correctness, length_type, comment, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), message_id, session_id, current_user_id(), rating, correctness, length_type, comment, now_iso()),
        )

    db.commit()
    return jsonify({"success": True})


@feedback_bp.route("/feedback/submit", methods=["POST"])
@require_login
def submit_feedback_frontend():
    """Alias endpoint for frontend feedback submission."""
    return submit_feedback()


