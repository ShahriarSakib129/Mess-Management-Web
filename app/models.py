from datetime import datetime, timezone

from . import db


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class User(TimestampMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    mess_id = db.Column(db.String(40), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=True)
    phone = db.Column(db.String(30))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member", index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    joined_on = db.Column(db.Date, nullable=False)
    left_on = db.Column(db.Date)
    opening_balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    notes = db.Column(db.Text)


class MessSetting(TimestampMixin, db.Model):
    __tablename__ = "mess_settings"
    id = db.Column(db.Integer, primary_key=True)
    mess_name = db.Column(db.String(160), nullable=False)
    logo_url = db.Column(db.String(500))
    address = db.Column(db.String(300))
    contact = db.Column(db.String(100))
    currency = db.Column(db.String(10), nullable=False, default="BDT")
    timezone = db.Column(db.String(64), nullable=False, default="Asia/Dhaka")
    default_meal_price = db.Column(db.Numeric(12, 2), default=0)
    allow_decimal_meals = db.Column(db.Boolean, nullable=False, default=True)
    common_expense_method = db.Column(db.String(20), nullable=False, default="equal")
    meal_expense_categories = db.Column(db.Text, default="")


class AccountingPeriod(TimestampMixin, db.Model):
    __tablename__ = "accounting_periods"
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(80), nullable=False)
    start_date = db.Column(db.Date, nullable=False, index=True)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    common_expense_method = db.Column(db.String(20), nullable=False, default="equal")
    meal_rate_snapshot = db.Column(db.Numeric(12, 4))
    closed_at = db.Column(db.DateTime(timezone=True))
    closed_by = db.Column(db.Integer, db.ForeignKey("users.id"))


class ManagerAssignment(TimestampMixin, db.Model):
    __tablename__ = "manager_assignments"
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("accounting_periods.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")
    appointed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    period = db.relationship("AccountingPeriod", backref="manager_assignments")
    user = db.relationship("User", foreign_keys=[user_id])
    __table_args__ = (db.UniqueConstraint("period_id", "user_id", name="uq_manager_period_user"),)


class ExpenseCategory(TimestampMixin, db.Model):
    __tablename__ = "expense_categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    meal_related = db.Column(db.Boolean, nullable=False, default=False)
    common_expense = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Meal(TimestampMixin, db.Model):
    __tablename__ = "meals"
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("accounting_periods.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    meal_date = db.Column(db.Date, nullable=False, index=True)
    breakfast = db.Column(db.Numeric(8, 2), nullable=False, default=0)
    lunch = db.Column(db.Numeric(8, 2), nullable=False, default=0)
    dinner = db.Column(db.Numeric(8, 2), nullable=False, default=0)
    guest = db.Column(db.Numeric(8, 2), nullable=False, default=0)
    special = db.Column(db.Numeric(8, 2), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="confirmed")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    edit_reason = db.Column(db.String(255))
    period = db.relationship("AccountingPeriod", backref="meals")
    user = db.relationship("User", foreign_keys=[user_id])
    __table_args__ = (db.UniqueConstraint("period_id", "user_id", "meal_date", name="uq_meal_period_user_date"),)

    @property
    def quantity(self):
        return sum((self.breakfast or 0, self.lunch or 0, self.dinner or 0, self.guest or 0, self.special or 0))


class MealCorrectionRequest(TimestampMixin, db.Model):
    __tablename__ = "meal_correction_requests"
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("accounting_periods.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    meal_date = db.Column(db.Date, nullable=False)
    requested_values = db.Column(db.JSON, nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    reviewed_at = db.Column(db.DateTime(timezone=True))
    user = db.relationship("User", foreign_keys=[user_id])


class Expense(TimestampMixin, db.Model):
    __tablename__ = "expenses"
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("accounting_periods.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("expense_categories.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    quantity = db.Column(db.Numeric(12, 2), default=1)
    unit_price = db.Column(db.Numeric(12, 2))
    purchase_date = db.Column(db.Date, nullable=False, index=True)
    vendor = db.Column(db.String(160))
    notes = db.Column(db.Text)
    receipt_key = db.Column(db.String(500))
    paid_by = db.Column(db.String(20), nullable=False, default="manager")
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_at = db.Column(db.DateTime(timezone=True))
    rejection_reason = db.Column(db.String(500))
    category = db.relationship("ExpenseCategory")
    period = db.relationship("AccountingPeriod", backref="expenses")
    creator = db.relationship("User", foreign_keys=[created_by])


class Deposit(TimestampMixin, db.Model):
    __tablename__ = "deposits"
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("accounting_periods.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    deposit_date = db.Column(db.Date, nullable=False)
    method = db.Column(db.String(30), nullable=False)
    reference = db.Column(db.String(120), unique=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    verified_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    verified_at = db.Column(db.DateTime(timezone=True))


class Payment(TimestampMixin, db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("accounting_periods.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    method = db.Column(db.String(30), nullable=False)
    reference = db.Column(db.String(120), unique=True, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    verified_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    verified_at = db.Column(db.DateTime(timezone=True))
    reversal_reason = db.Column(db.String(500))
    user = db.relationship("User", foreign_keys=[user_id])


class Refund(TimestampMixin, db.Model):
    __tablename__ = "refunds"
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("accounting_periods.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    refund_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="approved")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class MemberBalanceAdjustment(TimestampMixin, db.Model):
    __tablename__ = "member_balance_adjustments"
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("accounting_periods.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    direction = db.Column(db.String(10), nullable=False, default="credit")
    reason = db.Column(db.String(500), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class MonthlyStatement(TimestampMixin, db.Model):
    __tablename__ = "monthly_statements"
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("accounting_periods.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    meal_qty = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    meal_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    common_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    member_charges = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    verified_payments = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    refunds = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    opening_balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    net_balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    locked = db.Column(db.Boolean, nullable=False, default=False)
    __table_args__ = (db.UniqueConstraint("period_id", "user_id", name="uq_statement_period_user"),)


class MonthlyClosing(TimestampMixin, db.Model):
    __tablename__ = "monthly_closings"
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("accounting_periods.id"), nullable=False, unique=True)
    checklist = db.Column(db.JSON, nullable=False, default=dict)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="draft")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_at = db.Column(db.DateTime(timezone=True))


class CashbookEntry(TimestampMixin, db.Model):
    __tablename__ = "cashbook_entries"
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("accounting_periods.id"), nullable=False)
    entry_date = db.Column(db.Date, nullable=False)
    entry_type = db.Column(db.String(30), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    direction = db.Column(db.String(10), nullable=False)
    reference = db.Column(db.String(120))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class Announcement(TimestampMixin, db.Model):
    __tablename__ = "announcements"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    body = db.Column(db.Text, nullable=False)
    published = db.Column(db.Boolean, nullable=False, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class Notification(TimestampMixin, db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    body = db.Column(db.Text, nullable=False)
    kind = db.Column(db.String(30), nullable=False, default="system")
    is_read = db.Column(db.Boolean, nullable=False, default=False)


class AuditLog(TimestampMixin, db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(120), nullable=False, index=True)
    entity_type = db.Column(db.String(80))
    entity_id = db.Column(db.String(80))
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    ip_address = db.Column(db.String(64))


class LoginSession(db.Model):
    __tablename__ = "login_sessions"
    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True))
    user = db.relationship("User")
