import argparse
import os
from datetime import date

from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import User


def main():
    parser = argparse.ArgumentParser(description="Create the first MessMate admin without a hardcoded password.")
    parser.add_argument("--mess-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--email")
    parser.add_argument("--secret", required=True, help="Must match ADMIN_BOOTSTRAP_SECRET")
    args = parser.parse_args()
    configured = os.getenv("ADMIN_BOOTSTRAP_SECRET")
    if not configured or args.secret != configured:
        raise SystemExit("Bootstrap secret rejected.")
    app = create_app({"DEMO_MODE": False})
    with app.app_context():
        if User.query.filter_by(role="admin").first():
            raise SystemExit("An admin already exists; bootstrap is one-time.")
        if User.query.filter_by(mess_id=args.mess_id).first():
            raise SystemExit("That Mess ID already exists.")
        db.session.add(User(mess_id=args.mess_id.strip().lower(), full_name=args.name.strip(), email=args.email, password_hash=generate_password_hash(args.password), role="admin", joined_on=date.today(), is_active=True))
        db.session.commit()
        print(f"Created admin account {args.mess_id}.")


if __name__ == "__main__":
    main()
