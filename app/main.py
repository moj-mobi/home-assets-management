from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import partial
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import build_engine, build_session_factory, session_dependency
from app.models import Asset

BASE_DIR = Path(__file__).resolve().parent


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_directories()
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    get_db = partial(session_dependency, session_factory)
    templates = Jinja2Templates(directory=BASE_DIR / "templates")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.ensure_directories()
        yield
        engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, db: Session = Depends(get_db)):
        assets = db.scalars(select(Asset).order_by(Asset.created_at.desc())).all()
        return templates.TemplateResponse(request, "index.html", {"assets": assets})

    @app.post("/assets", response_class=HTMLResponse)
    def add_asset(
        request: Request,
        name: str = Form(min_length=1, max_length=200),
        category: str = Form(default="", max_length=100),
        purchase_date: str = Form(default=""),
        purchase_price: str = Form(default=""),
        notes: str = Form(default="", max_length=5000),
        db: Session = Depends(get_db),
    ):
        try:
            parsed_date = date.fromisoformat(purchase_date) if purchase_date else None
            parsed_price = Decimal(purchase_price) if purchase_price else None
        except (ValueError, InvalidOperation):
            return templates.TemplateResponse(
                request,
                "asset_form.html",
                {"error": "Datum ali cena nista v veljavnem formatu."},
                status_code=422,
            )
        asset = Asset(
            name=name.strip(),
            category=category.strip() or None,
            purchase_date=parsed_date,
            purchase_price=parsed_price,
            notes=notes.strip() or None,
        )
        db.add(asset)
        db.commit()
        return templates.TemplateResponse(request, "asset_row.html", {"asset": asset})

    return app


app = create_app()

