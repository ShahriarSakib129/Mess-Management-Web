import csv
import io
import secrets
from datetime import date, datetime, timezone
from decimal import Decimal

from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, db_health
from .accounting import active_period, dashboard_summary, member_summary, snapshot_period
from .models import (
    AccountingPeriod, AuditLog, Expense, ExpenseCategory, Meal, MealCorrectionRequest,
    ManagerAssignment, MessSetting, Notification, Payment, User,
)
from .security import (
    audit_event, auth_required, get_current_user, json_body, login_allowed,
    login_user, logout_user, manager_required, parse_decimal, role_required,
    validate_csrf,
)

bp = Blueprint("main", __name__)


@bp.after_app_request
def set_csrf_cookie(response):
    if not request.cookies.get("csrf_token"):
        from .security import csrf_token
        response.set_cookie("csrf_token", csrf_token(), httponly=False, secure=current_app.config["SESSION_COOKIE_SECURE"], samesite="None", path="/")
    return response


@bp.before_app_request
def protect_state_changes():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.endpoint not in {"main.login", "main.health"}:
        validate_csrf()


@bp.get("/health")
def health():
    result = db_health()
    return jsonify({"service": "messmate", **result}), 200 if result["status"] == "ok" else 503


@bp.get("/manus-routes.json")
def route_manifest():
    return jsonify({"routes": [
        {"path": "/", "title": "Login"}, {"path": "/dashboard", "title": "Dashboard"},
        {"path": "/member/statement", "title": "Account statement"}, {"path": "/member/meals", "title": "Meal history"},
        {"path": "/member/bazar", "title": "Bazar records"}, {"path": "/member/payments", "title": "Payment history"},
        {"path": "/notifications", "title": "Notifications"}, {"path": "/manager/meals", "title": "Meal entry"},
        {"path": "/manager/bazar", "title": "Bazar entry"}, {"path": "/manager/cashbook", "title": "Cashbook"},
        {"path": "/manager/handover", "title": "Manager handover"}, {"path": "/admin/members", "title": "Member management"},
        {"path": "/admin/manager", "title": "Manager assignment"}, {"path": "/admin/closing", "title": "Monthly closing"},
        {"path": "/admin/audit", "title": "Audit logs"}, {"path": "/reports/export.csv", "title": "Export report"},
    ]})


@bp.route("/", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        identifier = (request.form.get("mess_id") or "").strip().lower()
        password = request.form.get("password") or ""
        if not login_allowed(identifier):
            flash("Too many attempts. Please wait a few minutes before trying again.", "error")
            return render_template("login.html"), 429
        user = User.query.filter(or_(User.mess_id == identifier, User.email == identifier)).first()
        if not user or not user.is_active or not check_password_hash(user.password_hash, password):
            flash("We could not match that Mess ID and password.", "error")
            return render_template("login.html"), 401
        response = redirect(request.args.get("next") if request.args.get("next", "").startswith("/") else url_for("main.dashboard"))
        audit_event("login", actor_id=user.id, entity_type="user", entity_id=user.id)
        db.session.commit()
        return login_user(response, user, remember=request.form.get("remember") == "on")
    return render_template("login.html")


@bp.get("/logout")
def logout():
    response = redirect(url_for("main.login"))
    return logout_user(response)


@bp.get("/dashboard")
@auth_required
def dashboard():
    user = get_current_user()
    period = active_period()
    if not period:
        abort(500)
    summary = dashboard_summary(period)
    personal = member_summary(user, period)
    manager_assignment = ManagerAssignment.query.filter_by(period_id=period.id, status="active").first()
    notifications = Notification.query.filter_by(user_id=user.id, is_read=False).order_by(Notification.created_at.desc()).limit(4).all()
    recent_expenses = Expense.query.filter_by(period_id=period.id).order_by(Expense.purchase_date.desc()).limit(5).all()
    recent_meals = Meal.query.filter_by(period_id=period.id, user_id=user.id).order_by(Meal.meal_date.desc()).limit(7).all()
    pending_payments = Payment.query.filter_by(period_id=period.id, user_id=user.id, status="pending").count()
    return render_template("dashboard.html", section="dashboard", period=period, summary=summary, personal=personal, assignment=manager_assignment, notifications=notifications, recent_expenses=recent_expenses, recent_meals=recent_meals, pending_payments=pending_payments)


@bp.get("/member/statement")
@auth_required
def statement():
    user = get_current_user()
    period = active_period()
    summary = member_summary(user, period)
    payments = Payment.query.filter_by(period_id=period.id, user_id=user.id).order_by(Payment.payment_date.desc()).all()
    return render_template("statement.html", section="statement", period=period, summary=summary, payments=payments)


@bp.route("/member/meals", methods=["GET", "POST"])
@auth_required
def member_meals():
    user = get_current_user()
    period = active_period()
    if request.method == "POST":
        meal_date = date.fromisoformat(request.form.get("meal_date"))
        reason = (request.form.get("reason") or "").strip()
        if not reason:
            flash("Please explain the correction you are requesting.", "error")
        else:
            correction = MealCorrectionRequest(period_id=period.id, user_id=user.id, meal_date=meal_date, reason=reason, requested_values={"breakfast": request.form.get("breakfast", "0"), "lunch": request.form.get("lunch", "0"), "dinner": request.form.get("dinner", "0")})
            db.session.add(correction)
            audit_event("meal_correction_requested", actor_id=user.id, entity_type="meal_correction", entity_id=correction.id, metadata={"date": str(meal_date)})
            db.session.commit()
            flash("Correction request sent to the manager for review.", "success")
    meals = Meal.query.filter_by(period_id=period.id, user_id=user.id).order_by(Meal.meal_date.desc()).all()
    requests = MealCorrectionRequest.query.filter_by(period_id=period.id, user_id=user.id).order_by(MealCorrectionRequest.created_at.desc()).all()
    return render_template("meals.html", section="meals", period=period, meals=meals, requests=requests, can_manage=False)


@bp.get("/member/bazar")
@auth_required
def member_bazar():
    period = active_period()
    expenses = Expense.query.filter_by(period_id=period.id, status="approved").order_by(Expense.purchase_date.desc()).all()
    return render_template("bazar.html", section="bazar", period=period, expenses=expenses, can_manage=False, categories=ExpenseCategory.query.filter_by(is_active=True).all())


@bp.route("/member/payments", methods=["GET", "POST"])
@auth_required
def member_payments():
    user = get_current_user()
    period = active_period()
    if request.method == "POST":
        amount = parse_decimal(request.form.get("amount"), "Amount", "0.01")
        reference = (request.form.get("reference") or "").strip()
        if not reference or Payment.query.filter_by(reference=reference).first():
            flash("A unique payment reference is required; duplicate references are blocked.", "error")
        else:
            payment = Payment(period_id=period.id, user_id=user.id, amount=amount, method=request.form.get("method", "cash"), reference=reference, payment_date=date.fromisoformat(request.form.get("payment_date")), status="pending", created_by=user.id)
            db.session.add(payment)
            audit_event("payment_submitted", actor_id=user.id, entity_type="payment", entity_id=payment.id, metadata={"amount": str(amount)})
            db.session.commit()
            flash("Payment submitted for verification. It will count after an authorized user confirms it.", "success")
    payments = Payment.query.filter_by(period_id=period.id, user_id=user.id).order_by(Payment.payment_date.desc()).all()
    return render_template("payments.html", section="payments", period=period, payments=payments)


@bp.get("/notifications")
@auth_required
def notifications():
    user = get_current_user()
    items = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).all()
    for item in items:
        item.is_read = True
    db.session.commit()
    return render_template("notifications.html", section="notifications", items=items)


@bp.route("/manager/meals", methods=["GET", "POST"])
@manager_required
def manager_meals():
    user = get_current_user()
    period = active_period()
    if request.method == "POST":
        member_id = int(request.form.get("user_id"))
        meal_date = date.fromisoformat(request.form.get("meal_date"))
        target = User.query.get_or_404(member_id)
        meal = Meal.query.filter_by(period_id=period.id, user_id=target.id, meal_date=meal_date).first()
        values = {key: parse_decimal(request.form.get(key, "0"), key) for key in ("breakfast", "lunch", "dinner", "guest", "special")}
        if not meal:
            meal = Meal(period_id=period.id, user_id=target.id, meal_date=meal_date, created_by=user.id)
            db.session.add(meal)
        for key, value in values.items():
            setattr(meal, key, value)
        meal.status = "confirmed"
        meal.edit_reason = (request.form.get("edit_reason") or "Daily manager entry").strip()
        audit_event("meal_saved", actor_id=user.id, entity_type="meal", entity_id=meal.id, metadata={"member_id": target.id, "date": str(meal_date), "reason": meal.edit_reason})
        db.session.commit()
        flash(f"Meal record saved for {target.full_name}.", "success")
    members = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    meals = Meal.query.filter_by(period_id=period.id).order_by(Meal.meal_date.desc()).limit(80).all()
    corrections = MealCorrectionRequest.query.filter_by(period_id=period.id, status="pending").order_by(MealCorrectionRequest.created_at.asc()).all()
    return render_template("manager_meals.html", section="manager-meals", period=period, members=members, meals=meals, corrections=corrections)


@bp.route("/manager/bazar", methods=["GET", "POST"])
@manager_required
def manager_bazar():
    user = get_current_user()
    period = active_period()
    if request.method == "POST":
        category_id = int(request.form.get("category_id"))
        amount = parse_decimal(request.form.get("amount"), "Total price", "0.01")
        expense = Expense(period_id=period.id, category_id=category_id, title=request.form.get("title", "").strip(), amount=amount, quantity=parse_decimal(request.form.get("quantity", "1"), "Quantity", "0.01"), unit_price=parse_decimal(request.form.get("unit_price", amount), "Unit price", "0.01"), purchase_date=date.fromisoformat(request.form.get("purchase_date")), vendor=request.form.get("vendor", "").strip(), notes=request.form.get("notes", "").strip(), paid_by=request.form.get("paid_by", "manager"), status="approved" if user.role == "admin" else "pending", created_by=user.id)
        if not expense.title:
            flash("An expense title is required.", "error")
        else:
            db.session.add(expense)
            audit_event("expense_created", actor_id=user.id, entity_type="expense", entity_id=expense.id, metadata={"amount": str(amount)})
            db.session.commit()
            flash("Bazar expense recorded and queued for approval." if expense.status == "pending" else "Bazar expense approved and included in the current period.", "success")
    expenses = Expense.query.filter_by(period_id=period.id).order_by(Expense.purchase_date.desc()).all()
    return render_template("bazar.html", section="manager-bazar", period=period, expenses=expenses, can_manage=True, categories=ExpenseCategory.query.filter_by(is_active=True).all())


@bp.get("/manager/cashbook")
@manager_required
def cashbook():
    from .models import CashbookEntry
    period = active_period()
    entries = CashbookEntry.query.filter_by(period_id=period.id).order_by(CashbookEntry.entry_date.desc()).all()
    balance = sum((Decimal(e.amount or 0) if e.direction == "in" else -Decimal(e.amount or 0) for e in entries), Decimal("0"))
    return render_template("cashbook.html", section="cashbook", period=period, entries=entries, balance=balance)


@bp.get("/manager/handover")
@manager_required
def handover():
    period = active_period()
    assignment = ManagerAssignment.query.filter_by(period_id=period.id, status="active").first()
    summary = dashboard_summary(period)
    pending = Expense.query.filter_by(period_id=period.id, status="pending").count()
    return render_template("handover.html", section="handover", period=period, assignment=assignment, summary=summary, pending=pending)


@bp.route("/admin/members", methods=["GET", "POST"])
@role_required("admin")
def members():
    admin = get_current_user()
    if request.method == "POST":
        mess_id = request.form.get("mess_id", "").strip().lower()
        if not mess_id or User.query.filter_by(mess_id=mess_id).first():
            flash("Mess ID is required and must be unique.", "error")
        else:
            temp_password = request.form.get("password") or secrets.token_urlsafe(10)
            member = User(mess_id=mess_id, full_name=request.form.get("full_name", "").strip(), email=request.form.get("email", "").strip() or None, phone=request.form.get("phone", "").strip(), password_hash=generate_password_hash(temp_password), role=request.form.get("role", "member"), joined_on=date.fromisoformat(request.form.get("joined_on") or date.today().isoformat()), opening_balance=parse_decimal(request.form.get("opening_balance", "0"), "Opening balance"))
            if not member.full_name:
                flash("Full name is required.", "error")
            else:
                db.session.add(member)
                audit_event("member_created", actor_id=admin.id, entity_type="user", entity_id=member.id, metadata={"mess_id": mess_id, "role": member.role})
                db.session.commit()
                flash(f"Member created. Temporary password: {temp_password}", "success")
    users = User.query.order_by(User.is_active.desc(), User.full_name).all()
    return render_template("admin_members.html", section="members", users=users)


@bp.route("/admin/manager", methods=["GET", "POST"])
@role_required("admin")
def manager_assignment():
    admin = get_current_user()
    period = active_period()
    if request.method == "POST":
        user = User.query.get_or_404(int(request.form.get("user_id")))
        existing = ManagerAssignment.query.filter_by(period_id=period.id).first()
        if existing and existing.user_id != user.id:
            flash("This accounting period already has a manager. Close or explicitly replace the assignment first.", "error")
        else:
            if not existing:
                existing = ManagerAssignment(period_id=period.id, user_id=user.id, start_date=period.start_date, end_date=period.end_date, status="active", appointed_by=admin.id)
                db.session.add(existing)
            user.role = "manager"
            audit_event("manager_assigned", actor_id=admin.id, entity_type="manager_assignment", entity_id=existing.id, metadata={"user_id": user.id, "period_id": period.id})
            db.session.commit()
            flash(f"{user.full_name} is assigned as manager for {period.label}.", "success")
    assignment = ManagerAssignment.query.filter_by(period_id=period.id).first()
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    history = ManagerAssignment.query.order_by(ManagerAssignment.start_date.desc()).limit(12).all()
    return render_template("admin_manager.html", section="manager", period=period, assignment=assignment, users=users, history=history)


@bp.post("/admin/expense/<int:expense_id>/approve")
@role_required("admin")
def approve_expense(expense_id):
    admin = get_current_user()
    expense = Expense.query.get_or_404(expense_id)
    expense.status = "approved"
    expense.approved_by = admin.id
    expense.approved_at = datetime.now(timezone.utc)
    audit_event("expense_approved", actor_id=admin.id, entity_type="expense", entity_id=expense.id)
    db.session.commit()
    flash("Expense approved and included in official totals.", "success")
    return redirect(request.referrer or url_for("main.dashboard"))


@bp.post("/admin/payment/<int:payment_id>/verify")
@role_required("admin")
def verify_payment(payment_id):
    admin = get_current_user()
    payment = Payment.query.get_or_404(payment_id)
    if payment.status == "verified":
        flash("This payment has already been verified.", "warning")
    else:
        payment.status = "verified"
        payment.verified_by = admin.id
        payment.verified_at = datetime.now(timezone.utc)
        audit_event("payment_verified", actor_id=admin.id, entity_type="payment", entity_id=payment.id, metadata={"reference": payment.reference})
        db.session.commit()
        flash("Payment verified and added to the member ledger.", "success")
    return redirect(request.referrer or url_for("main.dashboard"))


@bp.route("/admin/closing", methods=["GET", "POST"])
@role_required("admin")
def closing():
    admin = get_current_user()
    period = active_period()
    if request.method == "POST":
        if period.status == "closed":
            flash("This period is already locked.", "warning")
        else:
            snapshot_period(period)
            audit_event("period_closed", actor_id=admin.id, entity_type="accounting_period", entity_id=period.id, metadata={"meal_rate": str(period.meal_rate_snapshot)})
            db.session.commit()
            flash("Monthly statements were snapshotted and the period is now locked.", "success")
    summary = dashboard_summary(period)
    pending_expenses = Expense.query.filter_by(period_id=period.id, status="pending").all()
    return render_template("closing.html", section="closing", period=period, summary=summary, pending_expenses=pending_expenses)


@bp.get("/admin/audit")
@role_required("admin")
def audit_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    return render_template("audit.html", section="audit", logs=logs)


@bp.get("/reports/export.csv")
@auth_required
def export_csv():
    user = get_current_user()
    period = active_period()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["MessMate statement", period.label, "User", user.full_name])
    writer.writerow(["Date", "Description", "Income/Credit", "Expense/Debit", "Running balance"])
    running = Decimal(user.opening_balance or 0)
    writer.writerow([period.start_date.isoformat(), "Opening balance", f"{running:.2f}", "", f"{running:.2f}"])
    for payment in Payment.query.filter_by(period_id=period.id, user_id=user.id, status="verified").order_by(Payment.payment_date).all():
        running += Decimal(payment.amount)
        writer.writerow([payment.payment_date.isoformat(), f"Verified payment · {payment.reference}", f"{payment.amount:.2f}", "", f"{running:.2f}"])
    summary = member_summary(user, period)
    running -= summary["total_cost"]
    writer.writerow([period.end_date.isoformat(), "Current period cost", "", f"{summary['total_cost']:.2f}", f"{running:.2f}"])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=messmate-{period.label.replace(' ', '-').lower()}.csv"})


@bp.post("/api/corrections/<int:request_id>/review")
@manager_required
def review_correction(request_id):
    manager = get_current_user()
    correction = MealCorrectionRequest.query.get_or_404(request_id)
    decision = json_body().get("decision")
    if decision not in {"approved", "rejected"}:
        abort(400, description="Decision must be approved or rejected.")
    correction.status = decision
    correction.reviewed_by = manager.id
    correction.reviewed_at = datetime.now(timezone.utc)
    audit_event("meal_correction_reviewed", actor_id=manager.id, entity_type="meal_correction", entity_id=correction.id, metadata={"decision": decision})
    db.session.commit()
    return jsonify({"ok": True, "status": correction.status})


@bp.post("/api/periods/close")
@role_required("admin")
def api_close_period():
    period = active_period()
    if period.status == "closed":
        return jsonify({"ok": False, "error": "period_locked"}), 409
    snapshot_period(period)
    audit_event("period_closed", actor_id=get_current_user().id, entity_type="accounting_period", entity_id=period.id)
    db.session.commit()
    return jsonify({"ok": True, "period_id": period.id, "status": period.status, "meal_rate": str(period.meal_rate_snapshot) if period.meal_rate_snapshot is not None else None})
