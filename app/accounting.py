from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func

from . import db
from .models import AccountingPeriod, Expense, Meal, Payment, Refund, User


MONEY = Decimal("0.01")
RATE = Decimal("0.0001")


def money(value):
    return Decimal(value or 0).quantize(MONEY, rounding=ROUND_HALF_UP)


def rate(value):
    return Decimal(value or 0).quantize(RATE, rounding=ROUND_HALF_UP)


def active_period():
    return AccountingPeriod.query.order_by(AccountingPeriod.start_date.desc()).first()


def meal_total(period):
    rows = Meal.query.filter_by(period_id=period.id, status="confirmed").all()
    return sum((Decimal(row.quantity or 0) for row in rows), Decimal("0"))


def expense_totals(period):
    approved = Expense.query.filter_by(period_id=period.id, status="approved").all()
    meal_cost = sum((Decimal(e.amount or 0) for e in approved if e.category and e.category.meal_related), Decimal("0"))
    common_cost = sum((Decimal(e.amount or 0) for e in approved if e.category and e.category.common_expense), Decimal("0"))
    other_cost = sum((Decimal(e.amount or 0) for e in approved if e.category and not e.category.meal_related and not e.category.common_expense), Decimal("0"))
    return {"meal_cost": money(meal_cost), "common_cost": money(common_cost), "other_cost": money(other_cost), "total": money(meal_cost + common_cost + other_cost)}


def meal_rate(period):
    total_meals = meal_total(period)
    if total_meals <= 0:
        return None
    return rate(expense_totals(period)["meal_cost"] / total_meals)


def member_summary(user, period):
    meal_rows = Meal.query.filter_by(period_id=period.id, user_id=user.id, status="confirmed").all()
    qty = sum((Decimal(row.quantity or 0) for row in meal_rows), Decimal("0"))
    totals = expense_totals(period)
    current_rate = meal_rate(period)
    meal_cost = money(qty * current_rate) if current_rate is not None else Decimal("0.00")
    active_members = User.query.filter_by(is_active=True).count() or 1
    if period.common_expense_method == "equal":
        common_cost = money(totals["common_cost"] / active_members)
    elif period.common_expense_method == "proportional":
        all_meals = meal_total(period)
        common_cost = money((totals["common_cost"] * qty / all_meals)) if all_meals else Decimal("0.00")
    else:
        common_cost = Decimal("0.00")
    verified_payments = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter_by(period_id=period.id, user_id=user.id, status="verified").scalar() or 0
    refunds = db.session.query(func.coalesce(func.sum(Refund.amount), 0)).filter_by(period_id=period.id, user_id=user.id, status="approved").scalar() or 0
    total_cost = money(meal_cost + common_cost)
    opening = money(user.opening_balance)
    payments = money(verified_payments)
    refund_total = money(refunds)
    net = money(opening + payments + refund_total - total_cost)
    return {
        "meal_qty": qty, "meal_cost": meal_cost, "common_cost": common_cost,
        "member_charges": Decimal("0.00"), "total_cost": total_cost,
        "verified_payments": payments, "refunds": refund_total,
        "opening_balance": opening, "net_balance": net,
        "rate": current_rate,
    }


def dashboard_summary(period):
    totals = expense_totals(period)
    total_meals = meal_total(period)
    active_members = User.query.filter_by(is_active=True).count()
    verified_deposits = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter_by(period_id=period.id, status="verified").scalar() or 0
    return {"total_meals": total_meals, "active_members": active_members, "verified_deposits": money(verified_deposits), "rate": meal_rate(period), **totals}


def snapshot_period(period):
    if period.status == "closed":
        return
    for user in User.query.filter_by(is_active=True).all():
        summary = member_summary(user, period)
        from .models import MonthlyStatement
        statement = MonthlyStatement.query.filter_by(period_id=period.id, user_id=user.id).first()
        if not statement:
            statement = MonthlyStatement(period_id=period.id, user_id=user.id)
            db.session.add(statement)
        for key in ("meal_qty", "meal_cost", "common_cost", "member_charges", "total_cost", "verified_payments", "refunds", "opening_balance", "net_balance"):
            setattr(statement, key, summary[key])
        statement.locked = True
    period.meal_rate_snapshot = meal_rate(period)
    period.status = "closed"
    db.session.commit()
