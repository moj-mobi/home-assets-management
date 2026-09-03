from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import partial
from pathlib import Path
from urllib.parse import quote, urlencode
from html import escape
import httpx
from fastapi import Depends, FastAPI, Form, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import Integer, and_, asc, cast, desc, func, or_, select, text
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.config import Settings
from app.ai_settings import AIKeyStore, check_key, valid_key_format
from app.db import build_engine, build_session_factory, session_dependency
from app.models import Asset, AssetValuationJob, Attachment, LocalUser
from app.asset_valuation import GeminiAssetValuator, VALUATION_DISCLAIMER, process_valuation_batch
from app.invoice_extraction import LocalInvoiceExtractor
from app.labels import LABEL_SIZES, PRINTERS, label_png, qr_png
from app.asset_ai import GeminiVisionAnalyzer
from app.security import DUMMY_HASH, MAX_FAILED_LOGINS, MIN_PASSWORD_LENGTH, constant_time_equal, hash_password, hash_session_id, lockout_deadline, logger, new_csrf_token, new_session_id, utcnow, verify_password

BASE_DIR = Path(__file__).resolve().parent
CONDITIONS = {"new", "used", "refurbished", "unknown"}
STATUSES = {"in_use", "loaned", "service", "sold", "gifted", "destroyed", "stored"}
DOCUMENT_TYPES = {"invoice", "warranty", "photo", "manual", "service", "other"}


def assign_inventory_number(db: Session, asset: Asset):
    if asset.inventory_number: return
    db.flush()
    asset.inventory_number = f"HAM-{asset.id:06d}"


def optional_date(value):
    return date.fromisoformat(value) if value else None


def optional_decimal(value):
    return Decimal(value) if value else None


def add_months(value, months):
    import calendar
    year, month = value.year + (value.month - 1 + months) // 12, (value.month - 1 + months) % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def file_kind(content):
    if content.startswith(b"%PDF-"): return "application/pdf", ".pdf"
    if content.startswith(b"\xff\xd8\xff"): return "image/jpeg", ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png", ".png"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP": return "image/webp", ".webp"
    return None, None


def age_label(asset, today=None):
    today, start = today or date.today(), asset.received_date or asset.purchase_date
    if not start: return "—"
    months = max(0, (today.year-start.year)*12 + today.month-start.month - (today.day < start.day))
    if months < 1: return "manj kot en mesec"
    years, rest = divmod(months, 12)
    if not years: return f"{months} mesecev" if months != 1 else "1 mesec"
    if not rest: return f"{years} leto" if years == 1 else f"{years} let"
    return f"{years} leto in {rest} mesece" if years == 1 else f"{years} let in {rest} mesece"


def warranty_label(asset, today=None):
    today = today or date.today()
    ends = [d for d in (asset.conformity_end, asset.warranty_end) if d]
    if not ends: return "Garancija ni evidentirana"
    end = max(ends); days = (end-today).days
    if days < 0:
        years = max(0, -days // 365)
        return f"Garancija potekla pred {years} leti" if years else f"Garancija potekla pred {-days} dnevi"
    if days <= 30: return f"Izteče čez {days} dni"
    return f"V garanciji – še {max(1, days//30)} mesecev"


STATUS_LABELS = {"in_use": "V uporabi", "loaned": "Posojeno", "service": "V servisu", "sold": "Prodano", "gifted": "Podarjeno", "destroyed": "Uničeno", "stored": "Shranjeno"}


def status_label(value): return STATUS_LABELS.get(value, value or "Ni podatka")
def sl_date(value): return value.strftime("%d. %m. %Y") if value else "Ni podatka"
def eur(value): return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €" if value is not None else "Ni podatka"
def query_without(request, *keys):
    kept = [(k, v) for k, v in request.query_params.multi_items() if k not in keys]
    query = urlencode(kept)
    return request.url.path + ("?" + query if query else "")


def form_context(db, **extra):
    assets = db.scalars(select(Asset)).all()
    values = lambda attr: sorted({getattr(a, attr) for a in assets if getattr(a, attr)})
    model_pairs = sorted({(a.manufacturer or "", a.model) for a in assets if a.model})
    return {"categories": values("category"), "locations": values("location"), "sellers": values("seller"), "manufacturers": values("manufacturer"), "models": values("model"), "model_pairs": model_pairs, **extra}


def populate_asset(asset, form):
    text_fields = ("name", "category", "manufacturer", "model", "serial_number", "seller", "product_url", "invoice_number", "order_number", "location", "warranty_provider", "warranty_number", "warranty_terms_url", "notes", "warranty_notes")
    for field in text_fields: setattr(asset, field, (form.get(field) or "").strip() or None)
    asset.name = (form.get("name") or "").strip()
    asset.purchase_condition = form.get("purchase_condition") if form.get("purchase_condition") in CONDITIONS else None
    asset.status = form.get("status") if form.get("status") in STATUSES else "in_use"
    asset.seller_type = form.get("seller_type") if form.get("seller_type") in {"business", "private", "gift", "unknown"} else None
    if asset.id is None: asset.currency = "EUR"
    for field in ("purchase_date", "received_date", "conformity_start", "conformity_end", "warranty_start", "warranty_end"): setattr(asset, field, optional_date(form.get(field)))
    asset.purchase_price = optional_decimal(form.get("purchase_price"))
    for field in ("conformity_months", "warranty_months"): setattr(asset, field, int(form[field]) if form.get(field) else None)
    asset.conformity_source = form.get("conformity_source") or "default"
    if asset.product_url and not asset.product_url.lower().startswith(("http://", "https://")):
        raise ValueError("URL")
    start = asset.received_date or asset.purchase_date
    if asset.conformity_months and not asset.conformity_start: asset.conformity_start = start
    if asset.conformity_months and asset.conformity_start and not asset.conformity_end: asset.conformity_end = add_months(asset.conformity_start, asset.conformity_months)
    if asset.warranty_months and not asset.warranty_start: asset.warranty_start = start
    if asset.warranty_months and asset.warranty_start and not asset.warranty_end: asset.warranty_end = add_months(asset.warranty_start, asset.warranty_months)
    if asset.conformity_source == "default" and asset.seller_type == "business" and asset.purchase_condition in {"new", "used"} and asset.conformity_months is None:
        asset.conformity_months, asset.conformity_source = 24, "default"
        asset.conformity_start = start
        if start: asset.conformity_end = add_months(start, 24)


def cleanup_staged(db, settings):
    cutoff = datetime.now() - timedelta(hours=24)
    staged = db.scalars(select(Attachment).where(Attachment.confirmed.is_(False), Attachment.uploaded_at < cutoff)).all()
    root = (settings.data_dir / "attachments").resolve()
    for attachment in staged:
        path = (root / attachment.stored_name).resolve()
        if root in path.parents: path.unlink(missing_ok=True)
        db.delete(attachment)
    if staged: db.commit()


def selected_asset_ids(values):
    return list(dict.fromkeys(int(value) for value in values if str(value).isdigit()))


MERGEABLE_FIELDS = (
    "category", "manufacturer", "model", "serial_number", "purchase_condition",
    "purchase_date", "received_date", "purchase_price", "currency", "seller",
    "seller_type", "purchase_country", "product_url", "invoice_number", "order_number",
    "location", "status", "conformity_months", "conformity_start", "conformity_end",
    "conformity_source", "warranty_provider", "warranty_months", "warranty_start",
    "warranty_end", "warranty_number", "warranty_terms_url", "warranty_notes",
)


async def store_upload(upload, document_type, settings, confirmed=False):
    content = await upload.read(settings.max_attachment_bytes + 1)
    if len(content) > settings.max_attachment_bytes: raise ValueError("Datoteka je prevelika.")
    mime, extension = file_kind(content)
    if not mime: raise ValueError("Dovoljeni so samo veljavni PDF, JPG in PNG dokumenti.")
    import uuid
    stored_name = f"{uuid.uuid4().hex}{extension}"
    root = (settings.data_dir / "attachments").resolve(); path = (root / stored_name).resolve()
    if root not in path.parents: raise ValueError("Neveljavna pot.")
    path.write_bytes(content)
    return Attachment(original_name=Path(upload.filename or "document").name[:255], stored_name=stored_name, document_type=document_type if document_type in DOCUMENT_TYPES else "other", mime_type=mime, size=len(content), confirmed=confirmed)


def safe_next(value):
    return value if value and value.startswith("/") and not value.startswith("//") else "/"


def ensure_csrf(request):
    if not request.session.get("csrf"):
        request.session["csrf"] = new_csrf_token()
    return request.session["csrf"]


def valid_csrf(request, supplied):
    valid = constant_time_equal(request.session.get("csrf"), supplied)
    if not valid:
        logger.warning("security_event=csrf_rejected session_cookie_present=%s session_token_present=%s submitted_token_present=%s", "ham_session" in request.cookies, bool(request.session.get("csrf")), bool(supplied))
    return valid


def create_app(settings=None):
    settings = settings or Settings.from_env()
    settings.ensure_directories()
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    get_db = partial(session_dependency, factory)
    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    templates.env.globals.update(age_label=age_label, warranty_label=warranty_label, status_label=status_label, sl_date=sl_date, eur=eur, query_without=query_without)
    extractor = LocalInvoiceExtractor()
    ai_keys = AIKeyStore(settings.data_dir, settings.gemini_api_key)
    vision = GeminiVisionAnalyzer(ai_keys.key, settings.gemini_model)
    valuator = GeminiAssetValuator(ai_keys.key, settings.gemini_model)
    valuation_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ham-valuations")

    @asynccontextmanager
    async def lifespan(_):
        with factory() as db:
            db.query(AssetValuationJob).filter(AssetValuationJob.status == "running").update({"status": "queued", "started_at": None})
            pending_batches = list(db.scalars(select(AssetValuationJob.batch_id).where(AssetValuationJob.status == "queued").distinct()))
            db.commit()
        for batch_id in pending_batches:
            valuation_executor.submit(process_valuation_batch, factory, valuator, batch_id)
        yield
        valuation_executor.shutdown(wait=False, cancel_futures=False)
        engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings, app.state.engine, app.state.session_factory = settings, engine, factory
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    @app.middleware("http")
    async def authentication(request, call_next):
        path = request.url.path
        if path in {"/health", "/login", "/favicon.ico"} or path.startswith("/static/"):
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

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(BASE_DIR / "static" / "img" / "ham-mark.png", media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, next: str = "/assets", db: Session = Depends(get_db)):
        initialized = db.scalar(select(LocalUser.id).limit(1)) is not None
        return templates.TemplateResponse(request, "login.html", {"csrf_token": ensure_csrf(request), "next_path": safe_next(next), "initialized": initialized})

    @app.post("/login", response_class=HTMLResponse)
    def login(request: Request, username: str = Form(max_length=100), password: str = Form(max_length=1000), csrf_token: str = Form(default=""), next_path: str = Form(default="/assets"), db: Session = Depends(get_db)):
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
        destination = safe_next(next_path)
        return RedirectResponse("/assets" if destination == "/" else destination, status_code=303)

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

    @app.get("/account", response_class=HTMLResponse)
    def account_page(request: Request, db: Session = Depends(get_db)):
        user = db.get(LocalUser, request.session.get("uid"))
        if not user: return RedirectResponse("/login", status_code=303)
        return templates.TemplateResponse(request, "account.html", {"user": user, "csrf_token": ensure_csrf(request), "saved": request.query_params.get("saved")})

    def ai_settings_page(request, error=None, status_code=200):
        return templates.TemplateResponse(request, "ai_settings.html", {
            **ai_keys.public_state(), "csrf_token": ensure_csrf(request),
            "error": error, "saved": request.query_params.get("saved"),
        }, status_code=status_code, headers={"Cache-Control": "no-store"})

    @app.get("/settings/ai", response_class=HTMLResponse)
    def ai_settings_get(request: Request):
        return ai_settings_page(request)

    @app.post("/settings/ai", response_class=HTMLResponse)
    async def ai_settings_update(request: Request):
        form = await request.form()
        if not valid_csrf(request, form.get("csrf_token", "")):
            return HTMLResponse("Neveljavna zahteva.", status_code=403)
        action = form.get("action")
        try:
            if action == "remove":
                ai_keys.save("")
            elif action in {"save", "check"}:
                key = (form.get("api_key") or "").strip() if action == "save" else ai_keys.key()
                if not valid_key_format(key):
                    return ai_settings_page(request, "Vnesite veljaven API ključ (najmanj 8 znakov, brez presledkov).", 422)
                previous = ai_keys.key()
                validity, checked_at = await check_key(key)
                # A pending check must never restore a concurrently removed/replaced key.
                if ai_keys.key() != previous:
                    return ai_settings_page(request, "Ključ je bil med preverjanjem spremenjen. Poskusite znova.", 409)
                ai_keys.save(key, validity, checked_at)
            else:
                return ai_settings_page(request, "Neveljavna zahteva.", 400)
        except (OSError, subprocess.SubprocessError):
            return ai_settings_page(request, "Ključa ni bilo mogoče varno shraniti. Preverite dovoljenja podatkovne mape.", 503)
        return RedirectResponse("/settings/ai?saved=1", status_code=303)

    @app.post("/account/profile", response_class=HTMLResponse)
    async def update_account_profile(request: Request, db: Session = Depends(get_db)):
        form = await request.form(); user = db.get(LocalUser, request.session.get("uid"))
        if not user: return RedirectResponse("/login", status_code=303)
        if not valid_csrf(request, form.get("csrf_token", "")): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        username, current_password = (form.get("username") or "").strip(), form.get("current_password") or ""
        error = None
        if not 3 <= len(username) <= 100: error = "Uporabniško ime mora imeti od 3 do 100 znakov."
        elif not verify_password(user.password_hash, current_password): error = "Trenutno geslo ni pravilno."
        elif db.scalar(select(LocalUser.id).where(LocalUser.username == username, LocalUser.id != user.id)): error = "To uporabniško ime je že uporabljeno."
        if error:
            return templates.TemplateResponse(request, "account.html", {"user": user, "error_profile": error, "csrf_token": ensure_csrf(request)}, status_code=422)
        user.username = username; db.commit(); logger.info("security_event=account_profile_updated")
        return RedirectResponse("/account?saved=profile", status_code=303)

    @app.post("/account/password", response_class=HTMLResponse)
    async def update_account_password(request: Request, db: Session = Depends(get_db)):
        form = await request.form(); user = db.get(LocalUser, request.session.get("uid"))
        if not user: return RedirectResponse("/login", status_code=303)
        if not valid_csrf(request, form.get("csrf_token", "")): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        current_password, new_password, confirmation = form.get("current_password") or "", form.get("new_password") or "", form.get("password_confirmation") or ""
        error = None
        if not verify_password(user.password_hash, current_password): error = "Trenutno geslo ni pravilno."
        elif len(new_password) < MIN_PASSWORD_LENGTH: error = f"Novo geslo mora imeti najmanj {MIN_PASSWORD_LENGTH} znakov."
        elif new_password != confirmation: error = "Novi gesli se ne ujemata."
        elif verify_password(user.password_hash, new_password): error = "Novo geslo mora biti drugačno od trenutnega."
        if error:
            return templates.TemplateResponse(request, "account.html", {"user": user, "error_password": error, "csrf_token": ensure_csrf(request)}, status_code=422)
        now, sid = utcnow(), new_session_id()
        user.password_hash, user.session_id_hash = hash_password(new_password), hash_session_id(sid)
        user.failed_login_count, user.locked_until = 0, None
        db.commit()
        request.session.clear(); request.session.update({"uid": user.id, "sid": sid, "csrf": new_csrf_token(), "last_seen": now.timestamp()})
        logger.info("security_event=account_password_changed")
        return RedirectResponse("/account?saved=password", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    def home():
        return RedirectResponse("/assets", status_code=303)

    @app.get("/assets/new", response_class=HTMLResponse)
    def index(request: Request, db: Session = Depends(get_db)):
        return templates.TemplateResponse(request, "index.html", {"csrf_token": ensure_csrf(request), **form_context(db)})

    @app.get("/assets/scan", response_class=HTMLResponse)
    def scan_asset(request: Request, db: Session = Depends(get_db)):
        created = db.get(Asset, int(request.query_params["created"])) if request.query_params.get("created", "").isdigit() else None
        return templates.TemplateResponse(request, "asset_scan.html", {"csrf_token": ensure_csrf(request), "ai_enabled": bool(ai_keys.key()), "created": created, **form_context(db)})

    @app.post("/assets/scan/analyze", response_class=HTMLResponse)
    async def analyze_asset_photos(request: Request, db: Session = Depends(get_db)):
        form = await request.form()
        if not valid_csrf(request, form.get("csrf_token", "")): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        uploads = [form.get(k) for k in ("asset_photo", "serial_photo", "label_photo")]
        images, attachments = [], []
        try:
            for upload in uploads:
                if upload is None or not getattr(upload, "filename", ""): continue
                attachment = await store_upload(upload, "photo", settings)
                content = (settings.data_dir / "attachments" / attachment.stored_name).read_bytes()
                images.append((content, attachment.mime_type)); attachments.append(attachment)
            if not images: raise ValueError("Posnemite ali izberite vsaj eno fotografijo.")
            data = await vision.analyze(images)
            for attachment in attachments: db.add(attachment)
            db.commit()
            return templates.TemplateResponse(request, "asset_scan_review.html", {"data": data, "attachments": attachments, "csrf_token": ensure_csrf(request), **form_context(db)})
        except (ValueError, RuntimeError, httpx.HTTPError, json.JSONDecodeError) as exc:
            root = (settings.data_dir / "attachments").resolve()
            for attachment in attachments:
                path = (root / attachment.stored_name).resolve()
                if root in path.parents: path.unlink(missing_ok=True)
            # HTMX privzeto ne zamenja cilja pri 4xx, zato pričakovano napako
            # vrnemo kot viden delni HTML. Obrazec in seja ostaneta nedotaknjena.
            return HTMLResponse(f'<div class="error scan-error" role="alert">{escape(str(exc))}</div>')

    @app.get("/assets", response_class=HTMLResponse)
    def asset_register(request: Request, db: Session = Depends(get_db)):
        p = request.query_params; query = select(Asset).options(selectinload(Asset.attachments))
        term = p.get("q", "").strip()
        if term:
            like = f"%{term}%"; query = query.where(or_(*[getattr(Asset, f).ilike(like) for f in ("name", "inventory_number", "manufacturer", "model", "serial_number", "category", "seller", "location")]))
        for param, field in (("name","name"),("serial","serial_number")):
            if p.get(param): query = query.where(getattr(Asset, field).ilike(f"%{p[param].strip()}%"))
        for param, field in (("category","category"),("manufacturer","manufacturer"),("location","location"),("status","status")):
            if p.get(param): query = query.where(getattr(Asset, field) == p[param])
        try:
            if p.get("purchase_from"): query = query.where(Asset.purchase_date >= optional_date(p["purchase_from"]))
            if p.get("purchase_to"): query = query.where(Asset.purchase_date <= optional_date(p["purchase_to"]))
            if p.get("price_min"): query = query.where(Asset.purchase_price >= optional_decimal(p["price_min"]))
            if p.get("price_max"): query = query.where(Asset.purchase_price <= optional_decimal(p["price_max"]))
        except (ValueError, InvalidOperation): pass
        archive = p.get("archive", "active")
        if archive == "archived": query = query.where(Asset.archived_at.is_not(None))
        elif archive != "all": query = query.where(Asset.archived_at.is_(None))
        structure = p.get("structure", "top")
        if structure == "components": query = query.where(Asset.parent_id.is_not(None))
        elif structure == "groups": query = query.where(Asset.is_group.is_(True))
        elif structure != "all": query = query.where(Asset.parent_id.is_(None))
        invoice = p.get("invoice", "")
        if invoice == "yes": query = query.where(Asset.attachments.any(Attachment.document_type == "invoice"))
        elif invoice == "no": query = query.where(~Asset.attachments.any(Attachment.document_type == "invoice"))
        coverage = p.get("warranty", ""); today = date.today()
        has_end = or_(Asset.conformity_end.is_not(None), Asset.warranty_end.is_not(None))
        valid_end = or_(Asset.conformity_end >= today, Asset.warranty_end >= today)
        if coverage == "active": query = query.where(valid_end)
        elif coverage == "expired": query = query.where(has_end, ~valid_end)
        elif coverage == "none": query = query.where(~has_end)
        sort_map = {"created_at": Asset.created_at, "name": Asset.name, "manufacturer": Asset.manufacturer, "purchase_date": Asset.purchase_date, "age": func.coalesce(Asset.received_date, Asset.purchase_date), "price": Asset.purchase_price, "location": Asset.location, "status": Asset.status}
        requested_sort = p.get("sort")
        sort = requested_sort if requested_sort in sort_map else "created_at"
        direction = p.get("direction", "asc" if requested_sort else "desc")
        direction = direction if direction in {"asc", "desc"} else ("asc" if requested_sort else "desc")
        ordering = desc if direction == "desc" else asc
        query = query.order_by(ordering(sort_map[sort]), ordering(Asset.id))
        per_page = int(p.get("per_page", "15")) if p.get("per_page", "15") in {"15","25","50"} else 15
        value_view = query.order_by(None).subquery()
        total, total_purchase_value, estimated_value_count = db.execute(select(
            func.count(),
            func.coalesce(func.sum(func.coalesce(value_view.c.purchase_price, value_view.c.estimated_purchase_price)), 0),
            func.coalesce(func.sum(cast(and_(value_view.c.purchase_price.is_(None), value_view.c.estimated_purchase_price.is_not(None)), Integer)), 0),
        ).select_from(value_view)).one()
        pages = max(1, (total + per_page - 1) // per_page); page = min(max(1, int(p.get("page", "1")) if p.get("page", "1").isdigit() else 1), pages)
        assets = db.scalars(query.offset((page-1)*per_page).limit(per_page)).unique().all()
        facets = form_context(db)
        filter_keys = ("name","category","manufacturer","serial","location","purchase_from","purchase_to","price_min","price_max","status","warranty","invoice","archive","structure")
        filter_value_labels = {
            "status": STATUS_LABELS,
            "warranty": {"active": "Veljavna garancija", "expired": "Potekla garancija", "none": "Brez evidentirane garancije"},
            "invoice": {"yes": "Z računom", "no": "Brez računa"},
            "archive": {"archived": "Samo arhivirana", "all": "Aktivna in arhivirana"},
            "structure": {"all": "Vsi zapisi", "components": "Samo komponente", "groups": "Samo sestavljena sredstva"},
        }
        active_filters = [
            (key, p.get(key), filter_value_labels.get(key, {}).get(p.get(key), p.get(key)))
            for key in filter_keys
            if p.get(key) and not (key == "archive" and p.get(key) == "active") and not (key == "structure" and p.get(key) == "top")
        ]
        start_item = (page-1)*per_page+1 if total else 0; end_item = min(page*per_page, total)
        return templates.TemplateResponse(request, "assets.html", {"assets": assets, "csrf_token": ensure_csrf(request), "params": p, "page": page, "pages": pages, "total": total, "total_purchase_value": total_purchase_value, "estimated_value_count": estimated_value_count, "valuation_batch": p.get("valuation_batch", ""), "per_page": per_page, "sort": sort, "direction": direction, "active_filters": active_filters, "start_item": start_item, "end_item": end_item, **facets})

    @app.post("/assets/valuations")
    async def enqueue_asset_valuations(request: Request, db: Session = Depends(get_db)):
        from uuid import uuid4
        form = await request.form()
        if not valid_csrf(request, form.get("csrf_token", "")): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        ids = selected_asset_ids(form.getlist("asset_id"))
        assets = db.scalars(select(Asset).where(Asset.id.in_(ids), Asset.archived_at.is_(None), Asset.is_group.is_(False))).all() if ids else []
        if not assets: return RedirectResponse("/assets?selection_error=valuation", status_code=303)
        batch_id = str(uuid4())
        db.add_all([AssetValuationJob(batch_id=batch_id, asset_id=asset.id) for asset in assets]); db.commit()
        valuation_executor.submit(process_valuation_batch, factory, valuator, batch_id)
        return RedirectResponse(f"/assets?valuation_batch={batch_id}", status_code=303)

    @app.get("/valuations/{batch_id}/status", response_class=HTMLResponse)
    def valuation_batch_status(batch_id: str, request: Request, db: Session = Depends(get_db)):
        jobs = db.scalars(select(AssetValuationJob).where(AssetValuationJob.batch_id == batch_id)).all()
        if not jobs: return HTMLResponse("Opravilo cenitve ne obstaja.", status_code=404)
        counts = {state: sum(job.status == state for job in jobs) for state in ("queued", "running", "completed", "failed")}
        pending = counts["queued"] + counts["running"]
        return templates.TemplateResponse(request, "valuation_status.html", {"batch_id": batch_id, "total_jobs": len(jobs), "counts": counts, "pending": pending})

    @app.post("/assets", response_class=HTMLResponse)
    async def add_asset(request: Request, db: Session = Depends(get_db)):
        form = await request.form(); csrf_token, name = form.get("csrf_token", ""), (form.get("name") or "").strip()
        if not valid_csrf(request, csrf_token):
            return HTMLResponse("Neveljavna zahteva.", status_code=403)
        if not name: return templates.TemplateResponse(request, "asset_form.html", {"error": "Naziv je obvezen.", "csrf_token": ensure_csrf(request), **form_context(db)}, status_code=422)
        try:
            asset = Asset(name=name); populate_asset(asset, form)
        except (ValueError, InvalidOperation):
            return templates.TemplateResponse(request, "asset_form.html", {"error": "Datum, trajanje ali cena niso v veljavnem formatu.", "csrf_token": ensure_csrf(request), **form_context(db)}, status_code=422)
        cleanup_staged(db, settings)
        attachment_ids = [int(v) for v in form.getlist("attachment_id") if str(v).isdigit()]
        if attachment_ids:
            attachments = db.scalars(select(Attachment).where(Attachment.id.in_(attachment_ids))).all()
            for attachment in attachments: attachment.confirmed = True
            asset.attachments.extend(attachments)
        new_attachments = []
        try:
            for field, kind in (("invoice_file","invoice"),("warranty_file","warranty"),("photo_file","photo"),("manual_file","manual"),("other_file","other")):
                upload = form.get(field)
                if upload is not None and hasattr(upload, "read") and getattr(upload, "filename", ""):
                    new_attachments.append(await store_upload(upload, kind, settings, confirmed=True))
        except ValueError as exc:
            root = (settings.data_dir / "attachments").resolve()
            for staged in new_attachments:
                path = (root / staged.stored_name).resolve()
                if root in path.parents: path.unlink(missing_ok=True)
            return templates.TemplateResponse(request, "asset_form.html", {"error": str(exc), "csrf_token": ensure_csrf(request), **form_context(db)}, status_code=422)
        asset.attachments.extend(new_attachments)
        db.add(asset)
        assign_inventory_number(db, asset)
        db.commit()
        db.refresh(asset)
        if request.headers.get("HX-Request") == "true": return templates.TemplateResponse(request, "asset_row.html", {"asset": asset})
        if form.get("scan_flow") == "1": return RedirectResponse(f"/assets/scan?created={asset.id}", status_code=303)
        return RedirectResponse(f"/assets/{asset.id}", status_code=303)

    @app.post("/receipts/preview", response_class=HTMLResponse)
    async def receipt_preview(request: Request, receipt: UploadFile = File(...), csrf_token: str = Form(default=""), db: Session = Depends(get_db)):
        if not valid_csrf(request, csrf_token): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        cleanup_staged(db, settings)
        try: attachment = await store_upload(receipt, "invoice", settings)
        except ValueError as exc: return HTMLResponse(str(exc), status_code=415)
        db.add(attachment); db.commit(); db.refresh(attachment)
        content = (settings.data_dir / "attachments" / attachment.stored_name).read_bytes(); data = extractor.extract(content, attachment.mime_type)
        return templates.TemplateResponse(request, "receipt_preview.html", {"data": data, "attachment": attachment, "csrf_token": ensure_csrf(request)})

    @app.post("/assets/from-receipt")
    async def assets_from_receipt(request: Request, db: Session = Depends(get_db)):
        form = await request.form()
        if not valid_csrf(request, form.get("csrf_token", "")): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        attachment = db.get(Attachment, int(form.get("attachment_id", 0)))
        if not attachment or attachment.confirmed: return HTMLResponse("Predogled računa ne obstaja.", status_code=404)
        names, prices = form.getlist("item_name"), form.getlist("item_price")
        selected = {int(x) for x in form.getlist("selected_item") if str(x).isdigit()}
        if not selected: return HTMLResponse("Izberite najmanj eno postavko.", status_code=422)
        created = []
        try:
            for i in sorted(selected):
                if i >= len(names) or not names[i].strip(): continue
                asset = Asset(name=names[i].strip()[:200], seller=(form.get("seller") or "").strip() or None, purchase_date=optional_date(form.get("purchase_date")), invoice_number=(form.get("invoice_number") or "").strip() or None, order_number=(form.get("order_number") or "").strip() or None, purchase_price=optional_decimal(prices[i] if i < len(prices) else ""), currency="EUR", warranty_months=int(form["warranty_months"]) if form.get("warranty_months") else None, purchase_condition="new", seller_type="business", status="in_use")
                if asset.purchase_date:
                    asset.conformity_months, asset.conformity_source, asset.conformity_start = 24, "default", asset.purchase_date
                    asset.conformity_end = add_months(asset.purchase_date, 24)
                    if asset.warranty_months: asset.warranty_start, asset.warranty_end = asset.purchase_date, add_months(asset.purchase_date, asset.warranty_months)
                asset.attachments.append(attachment); db.add(asset); assign_inventory_number(db, asset); created.append(asset)
        except (ValueError, InvalidOperation): return HTMLResponse("Preverite datum, ceno in trajanje.", status_code=422)
        if not created: return HTMLResponse("Izbrane postavke nimajo naziva.", status_code=422)
        attachment.confirmed = True; db.commit()
        return RedirectResponse(f"/assets/{created[0].id}", status_code=303)

    @app.post("/attachments/{attachment_id}/discard")
    def discard_staged(attachment_id: int, request: Request, csrf_token: str = Form(""), db: Session = Depends(get_db)):
        if not valid_csrf(request, csrf_token): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        attachment = db.get(Attachment, attachment_id)
        if not attachment or attachment.confirmed: return HTMLResponse("Začasna priloga ne obstaja.", status_code=404)
        path = (settings.data_dir / "attachments" / attachment.stored_name).resolve(); root = (settings.data_dir / "attachments").resolve()
        db.delete(attachment); db.commit()
        if root in path.parents: path.unlink(missing_ok=True)
        return HTMLResponse("")

    @app.get("/assets/merge", response_class=HTMLResponse)
    def merge_assets_review(request: Request, db: Session = Depends(get_db)):
        ids = selected_asset_ids(request.query_params.getlist("asset_id"))
        assets = db.scalars(select(Asset).where(Asset.id.in_(ids), Asset.archived_at.is_(None)).order_by(Asset.id)).all() if ids else []
        if len(assets) < 2 or any(asset.is_group for asset in assets):
            return RedirectResponse("/assets?selection_error=merge", status_code=303)
        return templates.TemplateResponse(request, "asset_merge.html", {"assets": assets, "csrf_token": ensure_csrf(request)})

    @app.post("/assets/merge")
    async def merge_assets(request: Request, db: Session = Depends(get_db)):
        form = await request.form()
        if not valid_csrf(request, form.get("csrf_token", "")): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        ids = selected_asset_ids(form.getlist("asset_id"))
        target_id = int(form.get("target_id")) if str(form.get("target_id", "")).isdigit() else 0
        assets = db.scalars(select(Asset).options(selectinload(Asset.attachments), selectinload(Asset.components)).where(Asset.id.in_(ids), Asset.archived_at.is_(None))).unique().all() if ids else []
        if len(assets) < 2 or target_id not in ids or any(asset.is_group for asset in assets):
            return HTMLResponse("Izberite najmanj dve navadni sredstvi in glavni zapis.", status_code=422)
        target = next(asset for asset in assets if asset.id == target_id)
        sources = [asset for asset in assets if asset.id != target_id]
        attachment_ids = {attachment.id for attachment in target.attachments}
        provenance = []
        for source in sources:
            for field in MERGEABLE_FIELDS:
                if getattr(target, field) in (None, "") and getattr(source, field) not in (None, ""):
                    setattr(target, field, getattr(source, field))
            for attachment in list(source.attachments):
                if attachment.id not in attachment_ids:
                    target.attachments.append(attachment); attachment_ids.add(attachment.id)
                source.attachments.remove(attachment)
            for component in list(source.components): component.parent = target
            if source.notes and source.notes.strip() and source.notes.strip() != (target.notes or "").strip():
                provenance.append(f"Opombe iz zapisa {source.name}: {source.notes.strip()}")
            provenance.append(f"Združen zapis #{source.id}: {source.name}")
            source.parent = None; source.merged_into = target; source.archived_at = datetime.now()
        if provenance:
            target.notes = "\n\n".join(part for part in [target.notes, *provenance] if part)
        db.commit()
        return RedirectResponse(f"/assets/{target.id}?merged={len(sources)}", status_code=303)

    @app.get("/assets/group", response_class=HTMLResponse)
    def group_assets_review(request: Request, db: Session = Depends(get_db)):
        ids = selected_asset_ids(request.query_params.getlist("asset_id"))
        assets = db.scalars(select(Asset).where(Asset.id.in_(ids), Asset.archived_at.is_(None), Asset.is_group.is_(False)).order_by(Asset.name)).all() if ids else []
        if len(assets) < 2: return RedirectResponse("/assets?selection_error=group", status_code=303)
        return templates.TemplateResponse(request, "asset_group.html", {"assets": assets, "csrf_token": ensure_csrf(request), **form_context(db)})

    @app.post("/assets/group")
    async def group_assets(request: Request, db: Session = Depends(get_db)):
        form = await request.form()
        if not valid_csrf(request, form.get("csrf_token", "")): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        ids = selected_asset_ids(form.getlist("asset_id")); name = (form.get("name") or "").strip()
        assets = db.scalars(select(Asset).where(Asset.id.in_(ids), Asset.archived_at.is_(None), Asset.is_group.is_(False))).all() if ids else []
        if len(assets) < 2 or not name: return HTMLResponse("Vnesite naziv in izberite najmanj dve komponenti.", status_code=422)
        group = Asset(name=name[:200], category=(form.get("category") or "Sestavljeno sredstvo").strip()[:100], location=(form.get("location") or "").strip() or None, status="in_use", is_group=True, notes=(form.get("notes") or "").strip() or None)
        db.add(group); assign_inventory_number(db, group)
        for asset in assets: asset.parent = group
        db.commit()
        return RedirectResponse(f"/assets/{group.id}?grouped={len(assets)}", status_code=303)

    @app.post("/assets/{asset_id}/archive")
    def archive_asset(asset_id: int, request: Request, csrf_token: str = Form(""), db: Session = Depends(get_db)):
        if not valid_csrf(request, csrf_token): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        asset = db.get(Asset, asset_id)
        if not asset: return HTMLResponse("Sredstvo ne obstaja.", status_code=404)
        asset.archived_at = datetime.now(); db.commit(); return RedirectResponse("/assets", status_code=303)

    @app.post("/assets/{asset_id}/restore")
    def restore_asset(asset_id: int, request: Request, csrf_token: str = Form(""), db: Session = Depends(get_db)):
        if not valid_csrf(request, csrf_token): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        asset = db.get(Asset, asset_id)
        if not asset: return HTMLResponse("Sredstvo ne obstaja.", status_code=404)
        asset.archived_at = None
        if asset.status == "stored": asset.status = "in_use"
        db.commit(); return RedirectResponse("/assets?archive=archived", status_code=303)

    @app.get("/assets/{asset_id}", response_class=HTMLResponse)
    def asset_detail(asset_id: int, request: Request, db: Session = Depends(get_db)):
        asset = db.scalar(select(Asset).options(selectinload(Asset.attachments), selectinload(Asset.components), selectinload(Asset.parent), selectinload(Asset.merged_into)).where(Asset.id == asset_id))
        if not asset: return HTMLResponse("Sredstvo ne obstaja.", status_code=404)
        available_components = db.scalars(select(Asset).where(Asset.archived_at.is_(None), Asset.is_group.is_(False), Asset.parent_id.is_(None), Asset.id != asset.id).order_by(Asset.name)).all() if asset.is_group else []
        try: estimate_sources = json.loads(asset.estimate_sources_json or "[]")
        except json.JSONDecodeError: estimate_sources = []
        return templates.TemplateResponse(request, "asset_detail.html", {"asset": asset, "available_components": available_components, "csrf_token": ensure_csrf(request), "estimate_sources": estimate_sources, "valuation_disclaimer": VALUATION_DISCLAIMER})

    @app.get("/assets/{asset_id}/edit", response_class=HTMLResponse)
    def asset_edit(asset_id: int, request: Request, db: Session = Depends(get_db)):
        asset = db.get(Asset, asset_id)
        if not asset: return HTMLResponse("Sredstvo ne obstaja.", status_code=404)
        return templates.TemplateResponse(request, "asset_edit.html", {"asset": asset, "csrf_token": ensure_csrf(request), **form_context(db)})

    @app.post("/assets/{asset_id}/edit")
    async def update_asset(asset_id: int, request: Request, db: Session = Depends(get_db)):
        form = await request.form()
        if not valid_csrf(request, form.get("csrf_token", "")): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        asset = db.get(Asset, asset_id)
        if not asset: return HTMLResponse("Sredstvo ne obstaja.", status_code=404)
        try: populate_asset(asset, form)
        except (ValueError, InvalidOperation): return HTMLResponse("Neveljavni podatki.", status_code=422)
        db.commit(); return RedirectResponse(f"/assets/{asset.id}", status_code=303)

    @app.post("/assets/{group_id}/components")
    async def add_group_components(group_id: int, request: Request, db: Session = Depends(get_db)):
        form = await request.form()
        if not valid_csrf(request, form.get("csrf_token", "")): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        group = db.get(Asset, group_id); ids = selected_asset_ids(form.getlist("component_id"))
        if not group or not group.is_group: return HTMLResponse("Sestavljeno sredstvo ne obstaja.", status_code=404)
        components = db.scalars(select(Asset).where(Asset.id.in_(ids), Asset.archived_at.is_(None), Asset.is_group.is_(False), Asset.id != group.id)).all() if ids else []
        if not components: return HTMLResponse("Izberite najmanj eno komponento.", status_code=422)
        for component in components: component.parent = group
        db.commit(); return RedirectResponse(f"/assets/{group.id}", status_code=303)

    @app.post("/assets/{group_id}/components/{component_id}/remove")
    def remove_group_component(group_id: int, component_id: int, request: Request, csrf_token: str = Form(""), db: Session = Depends(get_db)):
        if not valid_csrf(request, csrf_token): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        component = db.get(Asset, component_id)
        if not component or component.parent_id != group_id: return HTMLResponse("Komponenta ne obstaja v tem sestavljenem sredstvu.", status_code=404)
        component.parent = None; db.commit(); return RedirectResponse(f"/assets/{group_id}", status_code=303)

    @app.post("/assets/{asset_id}/attachments")
    async def add_attachment(asset_id: int, request: Request, document: UploadFile = File(...), document_type: str = Form("other"), csrf_token: str = Form(""), db: Session = Depends(get_db)):
        if not valid_csrf(request, csrf_token): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        asset = db.get(Asset, asset_id)
        if not asset: return HTMLResponse("Sredstvo ne obstaja.", status_code=404)
        content = await document.read(settings.max_attachment_bytes + 1); mime, extension = file_kind(content)
        if len(content) > settings.max_attachment_bytes: return HTMLResponse("Datoteka je prevelika.", status_code=413)
        if not mime: return HTMLResponse("Neveljavna vrsta datoteke.", status_code=415)
        import uuid
        stored_name = f"{uuid.uuid4().hex}{extension}"; (settings.data_dir / "attachments" / stored_name).write_bytes(content)
        attachment = Attachment(original_name=Path(document.filename or "document").name[:255], stored_name=stored_name, document_type=document_type if document_type in DOCUMENT_TYPES else "other", mime_type=mime, size=len(content), confirmed=True)
        asset.attachments.append(attachment); db.commit()
        return RedirectResponse(f"/assets/{asset_id}", status_code=303)

    @app.post("/assets/{asset_id}/photos")
    async def add_or_replace_asset_photo(asset_id: int, request: Request, photo: UploadFile | None = File(None), camera_photo: UploadFile | None = File(None), gallery_photo: UploadFile | None = File(None), replace_attachment_id: str = Form(""), csrf_token: str = Form(""), db: Session = Depends(get_db)):
        if not valid_csrf(request, csrf_token): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        asset = db.scalar(select(Asset).options(selectinload(Asset.attachments)).where(Asset.id == asset_id))
        if not asset: return HTMLResponse("Sredstvo ne obstaja.", status_code=404)
        selected_photo = next((upload for upload in (camera_photo, gallery_photo, photo) if upload and upload.filename), None)
        if not selected_photo: return HTMLResponse("Najprej fotografirajte sredstvo ali izberite sliko iz galerije.", status_code=422)
        try: new_photo = await store_upload(selected_photo, "photo", settings, confirmed=True)
        except ValueError as exc: return HTMLResponse(str(exc), status_code=415)
        old_photo = None; remove_old_file = False
        if replace_attachment_id.isdigit():
            candidate = db.get(Attachment, int(replace_attachment_id))
            if candidate and candidate.document_type == "photo" and candidate in asset.attachments:
                old_photo = candidate; remove_old_file = len(candidate.assets) <= 1
                asset.attachments.remove(candidate)
        asset.attachments.append(new_photo)
        if old_photo and remove_old_file: db.delete(old_photo)
        db.commit()
        if old_photo and remove_old_file:
            path = (settings.data_dir / "attachments" / old_photo.stored_name).resolve(); root = (settings.data_dir / "attachments").resolve()
            if root in path.parents: path.unlink(missing_ok=True)
        return RedirectResponse(f"/assets/{asset_id}?photo={'replaced' if old_photo else 'added'}", status_code=303)

    @app.get("/assets/{asset_id}/qr.png")
    def asset_qr(asset_id: int, db: Session = Depends(get_db)):
        asset = db.get(Asset, asset_id)
        if not asset: return HTMLResponse("Sredstvo ne obstaja.", status_code=404)
        if not asset.inventory_number: assign_inventory_number(db, asset); db.commit()
        return Response(qr_png(asset.name, asset.inventory_number), media_type="image/png", headers={"Content-Disposition": f'inline; filename="{asset.inventory_number}-qr.png"'})

    @app.get("/assets/{asset_id}/label.png")
    def asset_label(asset_id: int, printer: str = "b21pro", size: str = "50x30", db: Session = Depends(get_db)):
        asset = db.get(Asset, asset_id)
        if not asset: return HTMLResponse("Sredstvo ne obstaja.", status_code=404)
        if printer not in PRINTERS or size not in LABEL_SIZES: return HTMLResponse("Neveljavna predloga nalepke.", status_code=422)
        if not asset.inventory_number: assign_inventory_number(db, asset); db.commit()
        content = label_png(asset.name, asset.inventory_number, printer, size)
        filename = f"{asset.inventory_number}-{printer}-{size}.png"
        return Response(content, media_type="image/png", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/attachments/{attachment_id}")
    def preview_attachment(attachment_id: int, db: Session = Depends(get_db)):
        attachment = db.get(Attachment, attachment_id)
        if not attachment or not attachment.confirmed: return HTMLResponse("Priloga ne obstaja.", status_code=404)
        path = (settings.data_dir / "attachments" / attachment.stored_name).resolve(); root = (settings.data_dir / "attachments").resolve()
        if root not in path.parents or not path.is_file(): return HTMLResponse("Priloga ne obstaja.", status_code=404)
        return FileResponse(path, media_type=attachment.mime_type, filename=attachment.original_name, content_disposition_type="inline")

    @app.get("/attachments/{attachment_id}/download")
    def download_attachment(attachment_id: int, db: Session = Depends(get_db)):
        attachment = db.get(Attachment, attachment_id)
        if not attachment or not attachment.confirmed: return HTMLResponse("Priloga ne obstaja.", status_code=404)
        path = (settings.data_dir / "attachments" / attachment.stored_name).resolve(); root = (settings.data_dir / "attachments").resolve()
        if root not in path.parents or not path.is_file(): return HTMLResponse("Priloga ne obstaja.", status_code=404)
        return FileResponse(path, media_type=attachment.mime_type, filename=attachment.original_name, content_disposition_type="attachment")

    @app.post("/attachments/{attachment_id}/delete")
    def delete_attachment(attachment_id: int, request: Request, csrf_token: str = Form(""), db: Session = Depends(get_db)):
        if not valid_csrf(request, csrf_token): return HTMLResponse("Neveljavna zahteva.", status_code=403)
        attachment = db.get(Attachment, attachment_id)
        if not attachment: return HTMLResponse("Priloga ne obstaja.", status_code=404)
        asset_ids = [a.id for a in attachment.assets]
        path = (settings.data_dir / "attachments" / attachment.stored_name).resolve(); root = (settings.data_dir / "attachments").resolve()
        db.delete(attachment); db.commit()
        if root in path.parents: path.unlink(missing_ok=True)
        return RedirectResponse(f"/assets/{asset_ids[0]}" if asset_ids else "/", status_code=303)

    return app


app = create_app()
