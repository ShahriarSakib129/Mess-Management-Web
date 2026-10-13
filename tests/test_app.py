from decimal import Decimal

import pytest

from app import create_app, db
from app.accounting import member_summary, meal_rate
from app.models import AccountingPeriod, Expense, ExpenseCategory, Meal, Payment, User


@pytest.fixture()
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "COOKIE_SECURE": False,
        "DEMO_MODE": True,
        "AUTO_CREATE_SCHEMA": True,
    })
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, mess_id, password):
    response = client.post("/", data={"mess_id": mess_id, "password": password}, follow_redirects=True)
    assert response.status_code == 200
    return response


def csrf(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    return client.get_cookie("csrf_token").value


def test_login_logout_and_dashboard(client):
    response = login(client, "member", "DemoMember!2026")
    assert b"Account snapshot" in response.data
    logout = client.get("/logout", follow_redirects=True)
    assert b"Welcome back" in logout.data


def test_invalid_credentials_are_rejected(client):
    response = client.post("/", data={"mess_id": "member", "password": "wrong"})
    assert response.status_code == 401
    assert b"could not match" in response.data


def test_member_cannot_open_admin_route(client):
    login(client, "member", "DemoMember!2026")
    assert client.get("/admin/members").status_code == 403
    assert client.get("/manager/meals").status_code == 403


def test_manager_can_open_meals_and_admin_can_open_admin(client):
    login(client, "manager", "DemoManager!2026")
    assert client.get("/manager/meals").status_code == 200
    client.get("/logout")
    login(client, "admin", "DemoAdmin!2026")
    assert client.get("/admin/members").status_code == 200
    assert client.get("/admin/manager").status_code == 200


def test_decimal_rate_and_member_balance(app):
    with app.app_context():
        period = AccountingPeriod.query.first()
        member = User.query.filter_by(mess_id="member").first()
        manager = User.query.filter_by(mess_id="manager").first()
        category = ExpenseCategory.query.filter_by(name="Food and groceries").first()
        db.session.add(Meal(period_id=period.id, user_id=member.id, meal_date=period.end_date.replace(day=2), breakfast=Decimal("1.5"), lunch=Decimal("1"), dinner=Decimal("0"), created_by=manager.id))
        db.session.add(Expense(period_id=period.id, category_id=category.id, title="Approved test food", amount=Decimal("300.00"), purchase_date=period.end_date, status="approved", created_by=manager.id, approved_by=manager.id))
        db.session.commit()
        assert meal_rate(period) == Decimal("600.0000")
        summary = member_summary(member, period)
        assert summary["meal_cost"] == Decimal("2700.00")
        assert summary["net_balance"] == Decimal("-1200.00")


def test_duplicate_payment_reference_is_blocked(client, app):
    login(client, "member", "DemoMember!2026")
    token = csrf(client)
    data = {"amount": "500", "payment_date": "2026-10-13", "method": "cash", "reference": "DUP-1", "csrf_token": token}
    first = client.post("/member/payments", data=data)
    second = client.post("/member/payments", data=data)
    assert first.status_code == 200
    assert second.status_code == 200
    with app.app_context():
        assert Payment.query.filter_by(reference="DUP-1").count() == 1


def test_admin_closing_locks_period(client, app):
    login(client, "admin", "DemoAdmin!2026")
    token = csrf(client)
    response = client.post("/admin/closing", data={"csrf_token": token}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert AccountingPeriod.query.first().status == "closed"
