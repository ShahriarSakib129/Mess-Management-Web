import os
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text


db = SQLAlchemy()


def create_app(test_config=None):
    database_uri, engine_options = _database_config()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "change-me-in-production"),
        SQLALCHEMY_DATABASE_URI=database_uri,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS=engine_options,
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        SESSION_COOKIE_NAME="flask_state",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        SESSION_COOKIE_SAMESITE="None",
        PERMANENT_SESSION_LIFETIME=86400,
        MESS_TIMEZONE="Asia/Dhaka",
        CURRENCY="BDT",
        CURRENCY_SYMBOL="৳",
        DEMO_MODE=os.getenv("DEMO_MODE", "0") == "1",
        AUTO_CREATE_SCHEMA=True,
    )
    if test_config:
        app.config.update(test_config)
        if "COOKIE_SECURE" in test_config:
            app.config["SESSION_COOKIE_SECURE"] = bool(test_config["COOKIE_SECURE"])
        if "SQLALCHEMY_DATABASE_URI" in test_config and "SQLALCHEMY_ENGINE_OPTIONS" not in test_config:
            app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

    db.init_app(app)

    from .routes import bp
    app.register_blueprint(bp)

    @app.context_processor
    def inject_globals():
        from .models import MessSetting
        from .security import csrf_token, get_current_user
        setting = MessSetting.query.first()
        return {
            "current_user": get_current_user(),
            "csrf_token": csrf_token(),
            "mess_name": setting.mess_name if setting else "MessMate",
            "currency_symbol": app.config["CURRENCY_SYMBOL"],
            "current_year": datetime.now(timezone.utc).year,
        }

    @app.template_filter("money")
    def money_filter(value):
        try:
            return f"{Decimal(value or 0):,.2f}"
        except Exception:
            return "0.00"

    @app.template_filter("qty")
    def qty_filter(value):
        try:
            return f"{Decimal(value or 0):,.2f}".rstrip("0").rstrip(".")
        except Exception:
            return "0"

    @app.template_filter("datefmt")
    def datefmt_filter(value):
        return value.strftime("%d %b %Y") if value else "—"

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("error.html", code=400, title="Request could not be processed", message=str(error.description)), 400

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("error.html", code=403, title="Access restricted", message="You do not have permission to view or change this record."), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("error.html", code=404, title="Page not found", message="The page you requested is not available."), 404

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template("error.html", code=500, title="Something went wrong", message="The error was recorded safely. Please try again."), 500

    with app.app_context():
        from . import models  # noqa: F401
        if app.config.get("AUTO_CREATE_SCHEMA", True):
            db.create_all()
            _ensure_seed_data(app)

    return app


def _database_config():
    url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")
    if url:
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://"):]
        elif url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        elif url.startswith("mysql://"):
            url = "mysql+pymysql://" + url[len("mysql://"):]
        options = {"pool_pre_ping": True}
        if url.startswith("mysql+pymysql://"):
            parts = urlsplit(url)
            query = parse_qs(parts.query, keep_blank_values=True)
            ssl_value = query.pop("ssl", None)
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), parts.fragment))
            if ssl_value and ssl_value[0].lower() not in {"0", "false", "no", "off"}:
                # The managed DSN only advertises `ssl=true`; PyMySQL needs a
                # truthy dictionary to negotiate TLS. CA verification can be
                # supplied by a deployment-specific DSN when available.
                options["connect_args"] = {"ssl": {"check_hostname": False}}
        return url, options
    return "sqlite:///messmate-dev.db", {"pool_pre_ping": True}


def _ensure_seed_data(app):
    from werkzeug.security import generate_password_hash
    from .models import (
        AccountingPeriod, Expense, ExpenseCategory, ManagerAssignment, Meal,
        MessSetting, Notification, Payment, User,
    )
    from .security import audit_event

    if MessSetting.query.first() is None:
        db.session.add(MessSetting(
            mess_name="Green View Mess", address="Dhaka, Bangladesh", currency="BDT",
            timezone="Asia/Dhaka",
            meal_expense_categories="Food and groceries,Vegetables and fruits,Meat and fish,Rice and cooking essentials",
        ))

    categories = [
        ("Food and groceries", True, False), ("Vegetables and fruits", True, False),
        ("Meat and fish", True, False), ("Rice and cooking essentials", True, False),
        ("Gas and cooking fuel", False, True), ("Electricity", False, True),
        ("Water", False, True), ("Internet", False, True), ("Cleaning supplies", False, True),
        ("Household essentials", False, True), ("Repairs and maintenance", False, True),
        ("Other expenses", False, False),
    ]
    for name, meal_related, common in categories:
        if not ExpenseCategory.query.filter_by(name=name).first():
            db.session.add(ExpenseCategory(name=name, meal_related=meal_related, common_expense=common))

    if AccountingPeriod.query.first() is None:
        today = date.today()
        period = AccountingPeriod(
            label=today.strftime("%B %Y"), start_date=today.replace(day=1),
            end_date=today, status="open", common_expense_method="equal",
        )
        db.session.add(period)
        db.session.flush()
    else:
        period = AccountingPeriod.query.order_by(AccountingPeriod.start_date.desc()).first()

    if app.config.get("DEMO_MODE") and User.query.count() == 0:
        admin = User(mess_id="admin", full_name="Ayesha Rahman", email="admin@messmate.local", role="admin", password_hash=generate_password_hash("DemoAdmin!2026"), is_active=True, joined_on=date.today())
        manager = User(mess_id="manager", full_name="Tanvir Hossain", email="manager@messmate.local", role="manager", password_hash=generate_password_hash("DemoManager!2026"), is_active=True, joined_on=date.today())
        member = User(mess_id="member", full_name="Nusrat Jahan", email="member@messmate.local", role="member", password_hash=generate_password_hash("DemoMember!2026"), is_active=True, joined_on=date.today())
        db.session.add_all([admin, manager, member])
        db.session.flush()
        db.session.add(ManagerAssignment(period_id=period.id, user_id=manager.id, start_date=period.start_date, end_date=period.end_date, status="active", appointed_by=admin.id))
        db.session.add_all([
            Meal(period_id=period.id, user_id=manager.id, meal_date=date.today(), breakfast=1, lunch=1, dinner=1, status="confirmed", created_by=manager.id),
            Meal(period_id=period.id, user_id=member.id, meal_date=date.today(), breakfast=1, lunch=1, dinner=0, status="confirmed", created_by=manager.id),
            Expense(period_id=period.id, category_id=ExpenseCategory.query.filter_by(name="Food and groceries").first().id, title="Weekly groceries", amount=Decimal("4200.00"), purchase_date=date.today(), paid_by="manager", status="approved", created_by=manager.id, approved_by=admin.id, approved_at=datetime.now(timezone.utc)),
            Payment(period_id=period.id, user_id=member.id, amount=Decimal("1500.00"), method="bKash", reference="DEMO-1500", payment_date=date.today(), status="verified", created_by=member.id, verified_by=admin.id, verified_at=datetime.now(timezone.utc)),
            Notification(user_id=member.id, title="Welcome to MessMate", body="Your current month account is ready to review.", kind="announcement"),
        ])
        audit_event("demo_seed", actor_id=admin.id, metadata={"users": 3})
    db.session.commit()


def db_health():
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}
    except Exception as exc:
        db.session.rollback()
        return {"status": "degraded", "database": "unavailable", "detail": type(exc).__name__}
