"""Create (or update) a dedicated E2E test user inside the IRIS app container.

Run: docker compose run --rm app python app/e2e_test_user.py
The user 'e2e_test' is placed in the Administrators group (full permissions)
so it can manage cases and incident data.
"""
from app import db, bc
from app.models.authorization import User, Group, Organisation
from app.datamgmt.manage.manage_users_db import add_user_to_group, add_user_to_organisation


USERNAME = "e2e_test"
PASSWORD = "E2eTestPassw0rd!"


def main():
    user = User.query.filter(User.user == USERNAME).first()
    if user is None:
        user = User(
            user=USERNAME,
            name="E2E Test User",
            email="e2e_test@localhost",
            password=bc.generate_password_hash(PASSWORD.encode("utf8")).decode("utf8"),
            active=True,
        )
        user.api_key = "e2e-test-key" + "0" * 40
        db.session.add(user)
        db.session.commit()
        print(f"[e2e] created user '{USERNAME}'")
    else:
        user.password = bc.generate_password_hash(PASSWORD.encode("utf8")).decode("utf8")
        user.active = True
        db.session.commit()
        print(f"[e2e] updated password for existing user '{USERNAME}'")

    # Ensure membership in the Administrators group + default organisation
    admin_group = Group.query.filter(Group.group_name == "Administrators").first()
    if admin_group:
        add_user_to_group(user_id=user.id, group_id=admin_group.group_id)
    org = Organisation.query.first()
    if org:
        add_user_to_organisation(user_id=user.id, org_id=org.org_id)

    print(f"[e2e] done. login={USERNAME} password={PASSWORD}")


if __name__ == "__main__":
    from app import app as _app
    with _app.app_context():
        main()
