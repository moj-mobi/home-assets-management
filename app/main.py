from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import partial
from pathlib import Path
from urllib.parse import quote
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.config import Settings
from app.db import build_engine, build_session_factory, session_dependency
from app.models import Asset, LocalUser
from app.security import DUMMY_HASH, MAX_FAILED_LOGINS, constant_time_equal, hash_session_id, lockout_deadline, logger, new_csrf_token, new_session_id, utcnow, verify_password

BASE_DIR = Path(__file__).resolve().parent


def safe_next(value):
    return value if value and value.startswith("/") and not value.startswith("//") else "/"


def ensure_csrf(request):
    if not request.session.get("csrf"):
        request.session["csrf"] = new_csrf_token()
    return request.session["csrf"]


def valid_csrf(request, supplied):
    valid = constant_time_equal(request.session.get("csrf"), supplied)
    if not valid:
        logger.warning("security_event=csrf_rejected")
    return valid


def create_app(settings=None):
    settings = settings or Settings.from_env()
    settings.ensure_directories()
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    get_db = partial(session_dependency, factory)
    templates = Jinja2Templates(directory=BASE_DIR / "templates")

    @asynccontextmanager
    async def lifespan(_):
        yield
        engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings, app.state.engine, app.state.session_factory = settings, engine, factory
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    @app.middleware("http")
    async def authentication(request, call_next):
        path = request.url.path
        if path in {"/health", "/login"} or path.startswith("/static/"):
            return await call_next(request)
        uid, sid = request.session.get("uid"), request.session.get("sid")
        valid = False
        if uid and sid:
            with factory() as db:
                user = db.get(LocalUser, uid)
                last_seen = float(request.session.get("last_seen", 0))
                active = utcnow().timestamp() - last_seen <= settings.session_max_age_seconds
                valid = bool(user and user.is_active and active and constant_time_equal(user.session_id_hash, hash_session_id(sid)))
                if valid:
                    request.session["last_seen"] = utcnow().timestamp()
        if not valid:
            request.session.clear()
            if path.startswith("/api/") or "application/json" in request.headers.get("accept", ""):
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            return RedirectResponse(f"/login?next={quote(path)}", status_code=303)
        return await call_next(request)

    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, session_cookie="ham_session", max_age=settings.session_max_age_seconds, same_site="lax", https_only=settings.secure_cookies)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))

    @app.get("/health", include_in_schema=False)
    def health():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, next: str = "/", db: Session = Depends(get_db)):
        initialized = db.scalar(select(LocalUser.id).limit(1)) is not None
        return templates.TemplateResponse(request, "login.html", {"csrf_token": ensure_csrf(request), "next_path": safe_next(next), "initialized": initialized})

    @app.post("/login", response_class=HTMLResponse)
    def login(request: Request, username: str = Form(max_length=100), password: str = Form(max_length=1000), csrf_token: str = Form(default=""), next_path: str = Form(default="/"), db: Session = Depends(get_db)):
        if not valid_csrf(request, csrf_token):
            return templates.TemplateResponse(request, "login.html", {"error": "Neveljavna zahteva.", "csrf_token": ensure_csrf(request), "next_path": safe_next(next_path), "initialized": True}, status_code=403)
        user = db.scalar(select(LocalUser).where(LocalUser.username == username))
        password_ok = verify_password(user.password_hash if user else DUMMY_HASH, password)
        now = utcnow()
        locked = bool(user and user.locked_until and user.locked_until > now)
        if not user or not user.is_active or not password_ok or locked:
            if user and user.is_active and not locked:
                user.failed_login_count += 1
                if user.failed_login_count >= MAX_FAILED_LOGINS:
                    user.locked_until = lockout_deadline()
                    logger.warning("security_event=login_locked")
                db.commit()
            logger.warning("security_event=login_failed")
            return templates.TemplateResponse(request, "login.html", {"error": "Prijava ni uspela ali je začasno blokirana.", "csrf_token": ensure_csrf(request), "next_path": safe_next(next_path), "initialized": True}, status_code=401)
        sid = new_session_id()
        user.session_id_hash, user.failed_login_count, user.locked_until, user.last_login_at = hash_session_id(sid), 0, None, now
        db.commit()
        request.session.clear()
        request.session.update({"uid": user.id, "sid": sid, "csrf": new_csrf_token(), "last_seen": now.timestamp()})
        logger.info("security_event=login_success")
        return RedirectResponse(safe_next(next_path), status_code=303)

    @app.post("/logout")
    def logout(request: Request, csrf_token: str = Form(default=""), db: Session = Depends(get_db)):
        if not valid_csrf(request, csrf_token):
            return HTMLResponse("Neveljavna zahteva.", status_code=403)
        user = db.get(LocalUser, request.session.get("uid"))
        if user:
            user.session_id_hash = None
            db.commit()
        request.session.clear()
        logger.info("security_event=logout")
        return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, db: Session = Depends(get_db)):
        assets = db.scalars(select(Asset).order_by(Asset.created_at.desc())).all()
        return templates.TemplateResponse(request, "index.html", {"assets": assets, "csrf_token": ensure_csrf(request)})

    @app.post("/assets", response_class=HTMLResponse)
    def add_asset(request: Request, csrf_token: str = Form(default=""), name: str = Form(min_length=1, max_length=200), category: str = Form(default="", max_length=100), purchase_date: str = Form(default=""), purchase_price: str = Form(default=""), notes: str = Form(default="", max_length=5000), db: Session = Depends(get_db)):
        if not valid_csrf(request, csrf_token):
            return HTMLResponse("Neveljavna zahteva.", status_code=403)
        try:
            parsed_date = date.fromisoformat(purchase_date) if purchase_date else None
            parsed_price = Decimal(purchase_price) if purchase_price else None
        except (ValueError, InvalidOperation):
            return templates.TemplateResponse(request, "asset_form.html", {"error": "Datum ali cena nista v veljavnem formatu.", "csrf_token": ensure_csrf(request)}, status_code=422)
        asset = Asset(name=name.strip(), category=category.strip() or None, purchase_date=parsed_date, purchase_price=parsed_price, notes=notes.strip() or None)
        db.add(asset)
        db.commit()
        return templates.TemplateResponse(request, "asset_row.html", {"asset": asset})

    return app


app = create_app()