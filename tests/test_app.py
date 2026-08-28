import logging
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from conftest import TEST_PASSWORD, csrf_from, login


def test_home_login_and_brand_target_register(app_client):
    _, client = app_client
    assert client.get("/", follow_redirects=False).headers["location"].startswith("/login")
    response = login(client, follow=False)
    assert response.headers["location"] == "/assets"
    page = client.get("/assets")
    assert 'class="brand" href="/assets"' in page.text and 'Domov / Evidenca' in page.text


def test_accessible_hamburger_drawer_and_logout(app_client):
    _, client = app_client; login(client); page = client.get("/assets")
    assert 'id="menu-toggle"' in page.text and 'aria-expanded="false"' in page.text and 'aria-controls="nav-drawer"' in page.text
    assert 'id="drawer-overlay"' in page.text and "e.key==='Escape'" in page.text
    assert 'action="/logout"' in page.text and 'name="csrf_token"' in page.text and 'aria-current="page"' in page.text
    assert 'href="/assets/scan"' in page.text and "Skeniraj sredstvo" in page.text
    scan = client.get("/assets/scan")
    assert 'href="/assets/scan" class="nav-item active"' in scan.text and 'aria-current="page"' in scan.text


def test_design_system_controls_and_localized_table(app_client):
    app, client = app_client; login(client)
    from app.models import Asset
    from datetime import date
    with app.state.session_factory() as db:
        db.add(Asset(name="Lokalizirano", status="in_use", purchase_date=date(2026, 8, 1), purchase_price=29.99)); db.commit()
    page = client.get("/assets")
    assert "V uporabi" in page.text and "in_use</" not in page.text and "01. 08. 2026" in page.text and "29,99 €" in page.text
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")
    assert "--control-height:2.875rem" in css and "select,textarea" in css and "width:100%" in css
    assert "@media(min-width:1920px)" in css and "@media(min-width:2560px)" in css
    assert "@media(max-width:" not in css


def test_existing_database_migrates_without_losing_asset(tmp_path, monkeypatch):
    db_path = tmp_path / "existing.db"
    monkeypatch.setenv("HAM_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("HAM_DATA_DIR", str(tmp_path))
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "20260824_01")
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO assets (id,name) VALUES (1,'existing asset')")
        db.commit()
    command.upgrade(cfg, "head")
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT name FROM assets WHERE id=1").fetchone() == ("existing asset",)
        assert db.execute("SELECT inventory_number FROM assets WHERE id=1").fetchone() == ("HAM-000001",)
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("20260828_06",)


def test_manual_asset_and_separate_warranties(app_client):
    app, client = app_client; login(client); page = client.get("/")
    response = client.post("/assets", data={"csrf_token": csrf_from(page), "name": "Prenosnik", "purchase_condition": "new", "seller_type": "business", "purchase_date": "2026-01-15", "warranty_months": "12"})
    assert response.status_code == 200
    with app.state.session_factory() as db:
        from app.models import Asset
        asset = db.query(Asset).filter_by(name="Prenosnik").one()
        assert (asset.conformity_months, str(asset.conformity_end), asset.warranty_months, str(asset.warranty_end)) == (24, "2028-01-15", 12, "2027-01-15")


def test_receipt_preview_requires_confirmation_and_rejects_fake_file(app_client):
    app, client = app_client; login(client); page = client.get("/"); token = csrf_from(page)
    fake = client.post("/receipts/preview", data={"csrf_token": token}, files={"receipt": ("x.pdf", b"not a pdf", "application/pdf")})
    assert fake.status_code == 415
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 20
    preview = client.post("/receipts/preview", data={"csrf_token": token}, files={"receipt": ("receipt.png", png, "image/png")})
    assert preview.status_code == 200 and "Izbrani račun" in preview.text and "receipt.png" in preview.text
    with app.state.session_factory() as db:
        from app.models import Asset, Attachment
        assert db.query(Asset).count() == 0 and db.query(Attachment).one().confirmed is False


def test_multiple_assets_share_confirmed_receipt(app_client):
    app, client = app_client; login(client); token = csrf_from(client.get("/"))
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 20
    client.post("/receipts/preview", data={"csrf_token": token}, files={"receipt": ("receipt.png", png, "image/png")})
    with app.state.session_factory() as db:
        from app.models import Attachment
        attachment_id = db.query(Attachment.id).scalar()
    response = client.post("/assets/from-receipt", data={"csrf_token": token, "attachment_id": str(attachment_id), "selected_item": ["0", "1"], "item_name": ["Monitor", "Tipkovnica"], "item_price": ["200", "50"], "currency": "EUR"}, follow_redirects=False)
    assert response.status_code == 303
    with app.state.session_factory() as db:
        from app.models import Asset
        assets = db.query(Asset).all()
        assert len(assets) == 2 and assets[0].attachments[0].id == assets[1].attachments[0].id


def test_attachment_download_and_delete(app_client):
    app, client = app_client; login(client); token = csrf_from(client.get("/"))
    client.post("/assets", data={"csrf_token": token, "name": "Fotoaparat"})
    with app.state.session_factory() as db:
        from app.models import Asset
        asset_id = db.query(Asset.id).scalar()
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 20
    client.post(f"/assets/{asset_id}/attachments", data={"csrf_token": token, "document_type": "invoice"}, files={"document": ("../receipt.png", png, "image/png")})
    with app.state.session_factory() as db:
        from app.models import Attachment
        attachment = db.query(Attachment).one(); attachment_id, stored = attachment.id, attachment.stored_name
        assert attachment.original_name == "receipt.png"
    preview = client.get(f"/attachments/{attachment_id}")
    assert preview.content == png and preview.headers["content-disposition"].startswith("inline")
    download = client.get(f"/attachments/{attachment_id}/download")
    assert download.content == png and download.headers["content-disposition"].startswith("attachment")
    detail = client.get(f"/assets/{asset_id}")
    assert "data-attachment-preview" in detail.text and f'/attachments/{attachment_id}/download' in detail.text
    assert 'id="attachment-viewer"' in detail.text and "dialog.showModal()" in detail.text
    assert client.post(f"/attachments/{attachment_id}/delete", data={"csrf_token": token}, follow_redirects=False).status_code == 303
    assert not (app.state.settings.data_dir / "attachments" / stored).exists()


def test_mobile_inventory_photo_can_be_added_and_replaced(app_client):
    app, client = app_client; login(client); token = csrf_from(client.get("/"))
    client.post("/assets", data={"csrf_token": token, "name": "Sredstvo za inventuro"})
    with app.state.session_factory() as db:
        from app.models import Asset
        asset_id = db.query(Asset.id).filter_by(name="Sredstvo za inventuro").scalar()
    detail = client.get(f"/assets/{asset_id}")
    assert 'name="camera_photo"' in detail.text and 'capture="environment"' in detail.text
    assert 'name="gallery_photo"' in detail.text and "Fotografiraj zdaj" in detail.text and "Dodaj ali zamenjaj sliko" in detail.text
    first = b"\x89PNG\r\n\x1a\n" + b"first-photo"
    response = client.post(f"/assets/{asset_id}/photos", data={"csrf_token": token}, files={"camera_photo": ("first.png", first, "image/png")}, follow_redirects=False)
    assert response.status_code == 303 and "photo=added" in response.headers["location"]
    with app.state.session_factory() as db:
        from app.models import Asset
        asset = db.get(Asset, asset_id); old = asset.attachments[0]; old_id, old_path = old.id, app.state.settings.data_dir / "attachments" / old.stored_name
    second = b"\x89PNG\r\n\x1a\n" + b"replacement-photo"
    response = client.post(f"/assets/{asset_id}/photos", data={"csrf_token": token, "replace_attachment_id": str(old_id)}, files={"gallery_photo": ("new.png", second, "image/png")}, follow_redirects=False)
    assert response.status_code == 303 and "photo=replaced" in response.headers["location"]
    with app.state.session_factory() as db:
        from app.models import Asset
        asset = db.get(Asset, asset_id)
        assert len(asset.attachments) == 1 and asset.attachments[0].original_name == "new.png"
    assert not old_path.exists()


def test_inventory_number_qr_and_niimbot_label(app_client):
    from io import BytesIO
    from PIL import Image
    app, client = app_client; login(client); token = csrf_from(client.get("/"))
    client.post("/assets", data={"csrf_token": token, "name": "Asus Creator"})
    with app.state.session_factory() as db:
        from app.models import Asset
        asset = db.query(Asset).filter_by(name="Asus Creator").one()
        asset_id, inventory_number = asset.id, asset.inventory_number
    assert inventory_number == f"HAM-{asset_id:06d}"
    detail = client.get(f"/assets/{asset_id}")
    assert inventory_number in detail.text and "NIIMBOT B21" in detail.text and "NIIMBOT M2" in detail.text
    qr = client.get(f"/assets/{asset_id}/qr.png")
    assert qr.status_code == 200 and qr.headers["content-type"] == "image/png" and qr.content.startswith(b"\x89PNG")
    label = client.get(f"/assets/{asset_id}/label.png?printer=b21pro&size=50x30")
    assert label.status_code == 200 and label.headers["content-disposition"].startswith("attachment")
    with Image.open(BytesIO(label.content)) as image:
        assert image.size == (591, 354)


def test_duplicate_merge_preserves_data_attachments_and_audit_link(app_client):
    app, client = app_client; login(client); token = csrf_from(client.get("/"))
    from app.models import Asset, Attachment
    with app.state.session_factory() as db:
        target = Asset(name="Glavni računalnik", manufacturer="Acme", status="in_use")
        source = Asset(name="Podvojeni računalnik", model="X1", serial_number="SN-42", status="in_use")
        source.attachments.append(Attachment(original_name="slika.png", stored_name="merge-photo.png", document_type="photo", mime_type="image/png", size=8, confirmed=True))
        db.add_all([target, source]); db.commit(); target_id, source_id = target.id, source.id
        (app.state.settings.data_dir / "attachments" / "merge-photo.png").write_bytes(b"png-data")
    review = client.get(f"/assets/merge?asset_id={target_id}&asset_id={source_id}")
    assert review.status_code == 200 and "Združi podvojene vnose" in review.text
    response = client.post("/assets/merge", data={"csrf_token": token, "asset_id": [str(target_id), str(source_id)], "target_id": str(target_id)}, follow_redirects=False)
    assert response.status_code == 303 and f"/assets/{target_id}" in response.headers["location"]
    with app.state.session_factory() as db:
        target, source = db.get(Asset, target_id), db.get(Asset, source_id)
        assert (target.model, target.serial_number, len(target.attachments)) == ("X1", "SN-42", 1)
        assert source.archived_at is not None and source.merged_into_id == target_id and not source.attachments


def test_composite_asset_groups_and_releases_components(app_client):
    app, client = app_client; login(client); token = csrf_from(client.get("/"))
    from app.models import Asset
    with app.state.session_factory() as db:
        disk, board = Asset(name="Disk", status="in_use"), Asset(name="Matična plošča", status="in_use")
        db.add_all([disk, board]); db.commit(); disk_id, board_id = disk.id, board.id
    review = client.get(f"/assets/group?asset_id={disk_id}&asset_id={board_id}")
    assert review.status_code == 200 and "Ustvari sestavljeno sredstvo" in review.text
    response = client.post("/assets/group", data={"csrf_token": token, "asset_id": [str(disk_id), str(board_id)], "name": "Delovni računalnik", "location": "Pisarna"}, follow_redirects=False)
    assert response.status_code == 303
    with app.state.session_factory() as db:
        group = db.query(Asset).filter_by(name="Delovni računalnik").one(); group_id = group.id
        assert group.is_group and {component.id for component in group.components} == {disk_id, board_id}
    register = client.get("/assets")
    assert "Delovni računalnik" in register.text and ">Disk<" not in register.text
    detail = client.get(f"/assets/{group_id}")
    assert "Komponente" in detail.text and "Matična plošča" in detail.text
    assert client.post(f"/assets/{group_id}/components/{disk_id}/remove", data={"csrf_token": token}, follow_redirects=False).status_code == 303
    with app.state.session_factory() as db: assert db.get(Asset, disk_id).parent_id is None


def test_session_default_is_one_hour(app_client):
    app, _ = app_client
    assert app.state.settings.session_max_age_seconds == 3600


def test_account_management_changes_username_and_password_without_plaintext_storage(app_client):
    app, client = app_client; login(client, follow=True)
    account = client.get("/account")
    assert account.status_code == 200 and "Uporabniški račun" in account.text and "Zamenjava gesla" in account.text
    token = csrf_from(account)
    wrong = client.post("/account/profile", data={"csrf_token": token, "username": "updated-user", "current_password": "wrong-password"})
    assert wrong.status_code == 422 and "Trenutno geslo ni pravilno" in wrong.text
    changed_name = client.post("/account/profile", data={"csrf_token": token, "username": "updated-user", "current_password": TEST_PASSWORD}, follow_redirects=False)
    assert changed_name.status_code == 303
    token = csrf_from(client.get("/account")); new_password = "A different secure password 2026!"
    changed_password = client.post("/account/password", data={"csrf_token": token, "current_password": TEST_PASSWORD, "new_password": new_password, "password_confirmation": new_password}, follow_redirects=False)
    assert changed_password.status_code == 303 and changed_password.headers["location"] == "/account?saved=password"
    with app.state.session_factory() as db:
        from app.models import LocalUser
        user = db.query(LocalUser).one()
        assert user.username == "updated-user" and user.password_hash not in {TEST_PASSWORD, new_password}
        assert user.password_hash.startswith("$argon2id$") and user.session_id_hash
    assert client.get("/account").status_code == 200
    token = csrf_from(client.get("/account")); client.post("/logout", data={"csrf_token": token})
    old_login = client.post("/login", data={"username": "updated-user", "password": TEST_PASSWORD, "csrf_token": csrf_from(client.get("/login")), "next_path": "/assets"})
    assert old_login.status_code == 401
    assert client.post("/login", data={"username": "updated-user", "password": new_password, "csrf_token": csrf_from(client.get("/login")), "next_path": "/assets"}, follow_redirects=False).status_code == 303


def test_entry_and_register_are_separate(app_client):
    _, client = app_client; login(client)
    entry = client.get("/assets/new"); register = client.get("/assets")
    assert "Priloži račun in predizpolni" in entry.text and "Dodaj sredstvo" in entry.text
    assert "Filter in razvrščanje" not in entry.text and "Filter in razvrščanje" in register.text


def test_column_filters_and_mobile_scan_wizard(app_client):
    _, client = app_client; login(client)
    register = client.get("/assets?purchase_from=2026-01-01&sort=purchase_date&direction=desc")
    assert register.status_code == 200 and "Datum nakupa" in register.text
    assert 'name="purchase_from"' in register.text and "Filter in razvrščanje: Datum nakupa" in register.text
    scan = client.get("/assets/scan")
    assert scan.status_code == 200 and 'capture="environment"' in scan.text
    assert "Sredstvo" in scan.text and "Serijska številka" in scan.text and "Nalepka" in scan.text
    assert 'class="mobile-scan-callout"' in register.text and 'href="/assets/scan">Odpri čarovnika' in register.text
    assert 'class="mobile-asset-list"' in register.text and "/static/css/mobile.css" in register.text
    mobile_css = Path("app/static/css/mobile.css").read_text(encoding="utf-8")
    assert ".table-surface{display:none}" in mobile_css and "env(safe-area-inset-bottom)" in mobile_css


def test_scan_shows_previews_combines_three_photos_and_surfaces_ai_error(app_client):
    _, client = app_client; login(client)
    scan = client.get("/assets/scan")
    assert "Prepoznaj vse tri fotografije" in scan.text and scan.text.count("data-preview-input") >= 3
    assert 'aria-live="polite"' in scan.text and "htmx:beforeRequest" in scan.text
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 20
    response = client.post("/assets/scan/analyze", data={"csrf_token": csrf_from(scan)}, files=[
        ("asset_photo", ("asset.png", png, "image/png")),
        ("serial_photo", ("serial.png", png, "image/png")),
        ("label_photo", ("label.png", png, "image/png")),
    ])
    assert response.status_code == 200 and 'role="alert"' in response.text
    assert "GEMINI_API_KEY" in response.text


def test_register_search_filters_sort_pagination_and_sizes(app_client):
    app, client = app_client; login(client)
    from app.models import Asset
    with app.state.session_factory() as db:
        for i in range(31): db.add(Asset(name=f"Naprava {i:02}", manufacturer="Acme" if i % 2 else "Beta", category="Elektronika", location="Studio", status="in_use", purchase_price=i))
        db.commit()
    page = client.get("/assets?q=naprava&category=Elektronika&location=Studio&sort=price&direction=desc&per_page=15&page=2")
    assert page.status_code == 200 and "2 / 3" in page.text and "31 sredstev" in page.text
    assert "per_page=15" in page.text and "q=naprava" in page.text
    assert "31 sredstev" in client.get("/assets?per_page=25").text and "1 / 2" in client.get("/assets?per_page=25").text
    assert "1 / 1" in client.get("/assets?per_page=50").text


def test_register_defaults_to_latest_created_asset_and_scan_confirmation_links_to_it(app_client):
    app, client = app_client; login(client)
    from app.models import Asset
    with app.state.session_factory() as db:
        db.add(Asset(name="Zgodnejše sredstvo", status="in_use")); db.commit()
        db.add(Asset(name="Najnovejše sredstvo", status="in_use")); db.commit()

    page = client.get("/assets")
    assert page.text.index("Najnovejše sredstvo") < page.text.index("Zgodnejše sredstvo")

    with app.state.session_factory() as db:
        newest = db.scalar(select(Asset).where(Asset.name == "Najnovejše sredstvo"))
    confirmation = client.get(f"/assets/scan?created={newest.id}")
    assert f'href="/assets/{newest.id}"' in confirmation.text
    assert "Odpri shranjeno sredstvo" in confirmation.text


def test_archive_filter_and_restore(app_client):
    app, client = app_client; login(client); token = csrf_from(client.get("/"))
    client.post("/assets", data={"csrf_token": token, "name": "Arhivski test"})
    with app.state.session_factory() as db:
        from app.models import Asset
        asset_id = db.query(Asset.id).filter_by(name="Arhivski test").scalar()
    assert client.post(f"/assets/{asset_id}/archive", data={"csrf_token": token}, follow_redirects=False).status_code == 303
    assert "Arhivski test" not in client.get("/assets").text and "Arhivski test" in client.get("/assets?archive=archived").text
    client.post(f"/assets/{asset_id}/restore", data={"csrf_token": token})
    assert "Arhivski test" in client.get("/assets").text


def test_form_suggestions_eur_controls_and_manual_attachment(app_client):
    app, client = app_client; login(client); token = csrf_from(client.get("/"))
    client.post("/assets", data={"csrf_token": token, "name": "Obstoječa", "manufacturer": "Sony", "model": "Alpha"})
    form = client.get("/assets/new")
    assert 'datalist id="manufacturers"' in form.text and 'value="Sony"' in form.text and 'value="Alpha"' in form.text
    assert "Cena <span" in form.text and "Država nakupa" not in form.text and 'name="currency"' not in form.text and 'name="product_url"' in form.text
    assert "Privzeto pravilo" in form.text and "shranjeno</option>" not in form.text and "uničeno" in form.text
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 20
    response = client.post("/assets", data={"csrf_token": token, "name": "S prilogo"}, files={"invoice_file": ("racun.png", png, "image/png")}, follow_redirects=False)
    assert response.status_code == 303
    with app.state.session_factory() as db:
        from app.models import Asset
        asset = db.query(Asset).filter_by(name="S prilogo").one()
        assert asset.currency == "EUR" and asset.attachments[0].document_type == "invoice"


def test_health_is_public_and_data_page_is_protected(app_client):
    _, client = app_client
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"].startswith("/login")


def test_successful_and_failed_login_without_secret_logging(app_client, caplog):
    _, client = app_client
    with caplog.at_level(logging.INFO, logger="uvicorn.error.ham.security"):
        failed = login(client, "wrong-password")
        success = login(client)
    assert failed.status_code == 401
    assert success.status_code == 303
    assert client.get("/").status_code == 200
    logs = caplog.text
    assert TEST_PASSWORD not in logs and "wrong-password" not in logs
    assert "login_failed" in logs and "login_success" in logs


def test_logout_invalidates_session(app_client):
    _, client = app_client
    login(client)
    page = client.get("/")
    response = client.post("/logout", data={"csrf_token": csrf_from(page)}, follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 303


def test_account_locks_after_repeated_failures(app_client):
    _, client = app_client
    for _ in range(5):
        assert login(client, "wrong-password").status_code == 401
    assert login(client).status_code == 401


def test_mutation_requires_csrf_and_htmx_accepts_valid_token(app_client):
    _, client = app_client
    login(client)
    assert client.post("/assets", data={"name": "blocked"}).status_code == 403
    page = client.get("/")
    response = client.post("/assets", data={"name": "HTMX asset", "csrf_token": csrf_from(page)}, headers={"HX-Request": "true"})
    assert response.status_code == 200 and "HTMX asset" in response.text


def test_open_redirect_is_rejected(app_client):
    _, client = app_client
    page = client.get("/login?next=//evil.example")
    response = client.post("/login", data={"username": "local-test-user", "password": TEST_PASSWORD, "csrf_token": csrf_from(page), "next_path": "//evil.example"}, follow_redirects=False)
    assert response.headers["location"] == "/assets"

def test_untrusted_host_is_rejected(app_client):
    _, client = app_client
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 400
    assert client.get("/health", headers={"host": "127.0.0.1"}).status_code == 200

def test_favicon_does_not_invalidate_anonymous_login_csrf(app_client):
    _, client = app_client
    page = client.get("/login")
    token = csrf_from(page)
    assert client.get("/favicon.ico").status_code == 204
    response = client.post("/login", data={"username": "invalid-test-user", "password": "invalid-test-password", "csrf_token": token, "next_path": "/"})
    assert response.status_code == 401
    assert "Neveljavna zahteva" not in response.text
from app.asset_ai import GeminiVisionAnalyzer


def test_gemini_interactions_response_text():
    payload = {
        "status": "completed",
        "steps": [
            {"type": "thought"},
            {
                "type": "model_output",
                "content": [{"type": "text", "text": '{"name":"Prenosnik"}'}],
            },
        ],
    }

    assert GeminiVisionAnalyzer._response_text(payload) == '{"name":"Prenosnik"}'
