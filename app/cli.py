import getpass

from sqlalchemy import select

from app.config import Settings
from app.db import build_engine, build_session_factory
from app.models import LocalUser
from app.security import MIN_PASSWORD_LENGTH, hash_password


def set_password() -> int:
    settings = Settings.from_env()
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    username = input("Uporabniško ime: ").strip()
    if not 3 <= len(username) <= 100:
        print("Uporabniško ime mora imeti od 3 do 100 znakov.")
        return 1
    password = getpass.getpass("Geslo: ")
    confirmation = getpass.getpass("Ponovite geslo: ")
    if password != confirmation:
        print("Gesli se ne ujemata.")
        return 1
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Geslo mora imeti najmanj {MIN_PASSWORD_LENGTH} znakov.")
        return 1
    with factory() as db:
        users = db.scalars(select(LocalUser).order_by(LocalUser.id)).all()
        if len(users) > 1:
            raise RuntimeError("Database contains more than one local user")
        user = users[0] if users else None
        if user is None:
            user = LocalUser(username=username, password_hash=hash_password(password))
            db.add(user)
        else:
            user.username = username
            user.password_hash = hash_password(password)
            user.is_active = True
            user.failed_login_count = 0
            user.locked_until = None
            user.session_id_hash = None
        db.commit()
    engine.dispose()
    print("Lokalni uporabnik je varno nastavljen; vse obstoječe seje so razveljavljene.")
    return 0


if __name__ == "__main__":
    raise SystemExit(set_password())