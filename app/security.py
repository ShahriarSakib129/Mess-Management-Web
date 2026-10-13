import hashlib
import hmac
import json
import secrets
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import abort, current_app, g, has_request_context, redirect, request, url_for
from werkzeug.security import check_password_hash

from . import db
from .models import AccountingPeriod, AuditLog, LoginSession, ManagerAssignment, User


_attempts = defaultdict(deque)


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_current_user():
    if hasattr(g, "current_user"):
        return g.current_user
    token = request.cookies.get("webdev_app_session")
    if not token:
        g.current_user = None
        return None
    session = LoginSession.query.filter_by(token_hash=_hash_token(token), revoked_at=None).first()
    now = datetime.now(timezone.utc)
    expires_at = session.expires_at.replace(tzinfo=timezone.utc) if session and session.expires_at.tzinfo is None else (session.expires_at if session else now)
    if not session or expires_at <= now or not session.user.is_active:
        g.current_user = None
        return None
    g.current_session = session
    g.current_user = session.user
    return g.current_user


def login_user(response, user, remember=False):
    raw = secrets.token_urlsafe(40)
    expiry = datetime.now(timezone.utc) + timedelta(days=30 if remember else 1)
    db.session.add(LoginSession(token_hash=_hash_token(raw), user_id=user.id, expires_at=expiry))
    db.session.commit()
    response.set_cookie(
        "webdev_app_session", raw, max_age=int((expiry - datetime.now(timezone.utc)).total_seconds()),
        httponly=True, secure=current_app.config["SESSION_COOKIE_SECURE"], samesite="None", path="/",
    )
    return response


def logout_user(response):
    session = getattr(g, "current_session", None)
    if session:
        session.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
    response.delete_cookie("webdev_app_session", path="/")
    return response


def csrf_token():
    if hasattr(g, "csrf_token_value"):
        return g.csrf_token_value
    g.csrf_token_value = request.cookies.get("csrf_token") or secrets.token_urlsafe(24)
    return g.csrf_token_value


def validate_csrf():
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    cookie = request.cookies.get("csrf_token")
    if not supplied or not cookie or not hmac.compare_digest(supplied, cookie):
        abort(400, description="Your form expired. Refresh the page and try again.")


def auth_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("main.login", next="/dashboard"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @auth_required
        def wrapped(*args, **kwargs):
            if get_current_user().role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def manager_required(view):
    @wraps(view)
    @auth_required
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if user.role == "admin":
            return view(*args, **kwargs)
        period = AccountingPeriod.query.filter_by(status="open").order_by(AccountingPeriod.start_date.desc()).first()
        assignment = ManagerAssignment.query.filter_by(period_id=period.id if period else 0, user_id=user.id, status="active").first()
        if user.role != "manager" or not assignment:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def login_allowed(identifier):
    now = datetime.now(timezone.utc).timestamp()
    bucket = _attempts[identifier]
    while bucket and bucket[0] < now - 300:
        bucket.popleft()
    if len(bucket) >= 10:
        return False
    bucket.append(now)
    return True


def audit_event(action, actor_id=None, entity_type=None, entity_id=None, metadata=None):
    entry = AuditLog(
        actor_id=actor_id, action=action, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        metadata_json=metadata or {}, ip_address=request.remote_addr if has_request_context() else None,
    )
    db.session.add(entry)
    return entry


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="A JSON object is required.")
    return data


def parse_decimal(value, field, minimum="0"):
    from decimal import Decimal, InvalidOperation
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError):
        abort(400, description=f"{field} must be a valid number.")
    if result < Decimal(minimum):
        abort(400, description=f"{field} must be at least {minimum}.")
    return result
