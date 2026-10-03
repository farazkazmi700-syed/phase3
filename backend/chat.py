import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, session

from .db import get_db
from .llm import LocalLlamaError, build_llm_messages, query_llama
from .utils import current_user, current_user_id, json_payload, now_iso, require_login

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/chat")
@require_login
def chat():
    """Render the chat page without loading saved conversations."""
    return render_template(
        "chat.html",
        user=current_user(),
        username=session.get("username"),
    )


def session_title(first_message: str | None = None) -> str:
    """Return a short title for a chat session."""
    if not first_message:
        return "New Chat"
    return first_message[:40] + ("..." if len(first_message) > 40 else "")


def topic_label_from_message(message: str) -> str:
    """FR11: create a compact topic label stored with each interaction."""
    words = [
        word.strip(".,!?;:()[]{}\"'").lower()
        for word in message.split()
        if word.strip(".,!?;:()[]{}\"'")
    ]
    if not words:
        return "general"
    return " ".join(words[:4])[:60]


def create_chat_session(db, first_message: str | None = None) -> tuple[str, str]:
    """FR7: create a unique private session for one independent conversation."""
    session_id = str(uuid.uuid4())
    timestamp = now_iso()
    db.execute(
        "INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
        (session_id, current_user_id(), session_title(first_message), timestamp, timestamp),
    )
    return session_id, timestamp


def rename_session_from_first_message(db, session_id: str, first_message: str) -> None:
    """FR7: replace the temporary title once the session receives its first turn."""
    existing_messages = db.execute(
        "SELECT COUNT(*) AS total FROM messages WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if existing_messages and existing_messages["total"] == 0:
        db.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
            (session_title(first_message), now_iso(), session_id),
        )


def user_owns_session(session_id: str) -> bool:
    """FR7: validate that the active browser conversation belongs to this user."""
    row = get_db().execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, current_user_id()),
    ).fetchone()
    return row is not None


def load_session_context(db, session_id: str):
    """FR8: load all previous turns so the assistant can continue the conversation."""
    return db.execute(
        """
        SELECT role, content
        FROM messages
        WHERE session_id = ?
        ORDER BY created_at ASC
        """,
        (session_id,),
    ).fetchall()


def session_has_pending_feedback(db, session_id: str) -> bool:
    """FR12/FR13: detect whether chat input must stay blocked for feedback."""
    row = db.execute(
        """
        SELECT messages.id
        FROM messages
        LEFT JOIN feedback ON feedback.message_id = messages.id
        WHERE messages.session_id = ?
          AND messages.user_id = ?
          AND messages.role = 'assistant'
          AND feedback.id IS NULL
        LIMIT 1
        """,
        (session_id, current_user_id()),
    ).fetchone()
    return row is not None


@chat_bp.route("/chat/session/new", methods=["POST"])
@require_login
def new_chat_session():
    """FR7: generate a unique session ID before the first chat message is sent."""
    db = get_db()
    session_id, timestamp = create_chat_session(db)
    db.commit()
    return jsonify({
        "session_id": session_id,
        "created_at": timestamp,
    })


@chat_bp.route("/chat/send", methods=["POST"])
@require_login
def send_message_frontend():
    """FR8: append a turn and answer using the full active session history."""
    payload = json_payload()
    content = payload.get("content", "").strip()
    session_id = payload.get("session_id")
    if not content:
        return jsonify({"error": "Message content is required."}), 400

    db = get_db()
    if session_id:
        if not user_owns_session(session_id):
            return jsonify({"error": "Conversation not found."}), 404
        # FR13: reject new input until feedback for the previous response exists.
        if session_has_pending_feedback(db, session_id):
            return jsonify({"error": "Please submit feedback for the previous response before sending another message."}), 428
        timestamp = now_iso()
        rename_session_from_first_message(db, session_id, content)
    else:
        # Backward compatibility: clients that do not pre-create a session still
        # get an isolated UUID conversation on their first message.
        session_id, timestamp = create_chat_session(db, content)

    # FR11: derive a topic label from the user's query and store it with both
    # the user message and the model response for this interaction.
    topic_label = topic_label_from_message(content)
    user_msg_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO messages
        (id, session_id, user_id, role, content, topic_label, created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (user_msg_id, session_id, current_user_id(), "user", content, topic_label, timestamp),
    )

    # FR8: include every topic and turn from this session so users can move
    # naturally between topics without losing previous conversational context.
    context_rows = load_session_context(db, session_id)

    try:
        # FR10: capture the request timestamp immediately before calling LLaMA 3.
        request_started_at = datetime.now(timezone.utc)
        # FR9: send the session context to LLaMA 3 and wait for its generated reply.
        assistant_content = query_llama(build_llm_messages(context_rows))
        # FR10: capture the response timestamp immediately after LLaMA 3 returns.
        response_received_at = datetime.now(timezone.utc)
    except LocalLlamaError as exc:
        db.rollback()
        return jsonify({"error": str(exc)}), 502

    # FR10: response time is calculated from the response and request timestamps.
    response_time_ms = round((response_received_at - request_started_at).total_seconds() * 1000)
    request_ts = request_started_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    reply_ts = response_received_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    assistant_msg_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO messages
        (id, session_id, user_id, role, content, topic_label, created_at, request_started_at, response_received_at, response_time_ms)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            assistant_msg_id,
            session_id,
            current_user_id(),
            "assistant",
            assistant_content,
            topic_label,
            reply_ts,
            request_ts,
            reply_ts,
            response_time_ms,
        ),
    )
    db.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (reply_ts, session_id))
    db.commit()

    # FR9/FR10: return the generated response and timing data to the browser.
    return jsonify({
        "session_id": session_id,
        "user_message_id": user_msg_id,
        "message_id": assistant_msg_id,
        "response": assistant_content,
        "timestamp": reply_ts,
        "request_started_at": request_ts,
        "response_received_at": reply_ts,
        "response_time_ms": response_time_ms,
        "topic_label": topic_label,
    })
