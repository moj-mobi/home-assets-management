# HAM — Home Assets Management

HAM je lokalno gostovana spletna aplikacija za evidenco domačega premoženja. MVP uporablja Python 3.13, FastAPI, SQLAlchemy 2, Alembic, SQLite, Jinja2 in HTMX. Uporabniški vmesnik je strežniško izrisan in ne potrebuje Node.js ali zunanjih oblačnih storitev.

## Hiter zagon z Dockerjem

Potrebujete Docker z dodatkom Docker Compose.

```sh
docker compose up -d --build
```

Aplikacija je nato na <http://127.0.0.1:8000>. Stanje preverite z `docker compose ps` ali na <http://127.0.0.1:8000/health>.

Ustavitev:

```sh
docker compose down
```

`compose down` ne izbriše podatkov, ker so v gostiteljski mapi `data/`, ne v vsebniku. Ne uporabljajte `docker compose down -v` za odstranjevanje podatkovnih nosilcev v prihodnjih konfiguracijah.

Na Windows lahko uporabite `start-ham.bat` in `stop-ham.bat`, na Linuxu pa `./start-ham.sh` ter `./stop-ham.sh`. Po kloniranju na Linuxu po potrebi nastavite izvedljivost: `chmod +x *.sh`.

Compose na Linuxu privzeto zažene proces z UID/GID `1000:1000`, da so datoteke v vezani mapi `data/` v lasti običajnega uporabnika. Če ima uporabnik strežnika drugačna identifikatorja, kopirajte `.env.example` v `.env` ter vrednosti `HAM_UID` in `HAM_GID` uskladite z izpisoma `id -u` in `id -g`.

## Trajni podatki

```text
data/
├── database/     # aktivna SQLite baza ham.db
├── attachments/  # priponke in dokumenti
├── backups/      # varnostne kopije
└── imports/      # datoteke za uvoz
```

Celotna mapa se v vsebnik priklopi kot `/app/data`. Vsebina je izključena iz Gita; različica hrani samo datoteke `.gitkeep`. Aktivna SQLite baza mora ostati na lokalnem disku gostitelja. Ne postavljajte je na SMB, NFS ali NAS. Na omrežno lokacijo kopirajte samo zaključene varnostne kopije.

## Varnostna kopija in obnova

Na Linuxu med delovanjem aplikacije izvedite:

```sh
./backup-ham.sh
```

Skripta uporabi SQLite Online Backup API in ustvari časovno označeno konsistentno kopijo v `data/backups/`. Poleg baze ločeno kopirajte tudi `data/attachments/`. Kopije redno prenesite na drugo napravo in preizkusite obnovo.

Obnova: ustavite HAM, obstoječo `data/database/ham.db` najprej varno preimenujte, izbrano kopijo skopirajte na njeno mesto kot `ham.db`, nato aplikacijo zaženite. Pred obnovo shranite še trenutno stanje.

## Posodobitev

1. Izdelajte varnostno kopijo.
2. Pridobite novo različico kode.
3. Zaženite `docker compose up -d --build`.
4. Preverite `docker compose ps` in `/health`.

Vsebnik pred zagonom sam izvede `alembic upgrade head`. Podatkovna mapa pri ponovni izdelavi slike ali ponovnem ustvarjanju vsebnika ostane nedotaknjena.

## Neposredni razvojni zagon

Uporabite Python 3.13:

```sh
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"   # Windows
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn app.main:app --reload
```

Na Linuxu sta ustrezni poti `.venv/bin/...`. Teste zaženete z `pytest`.

## Dostop in varnostne meje MVP

Compose vrata namenoma objavi le na `127.0.0.1`, zato aplikacija privzeto ni dostopna iz domačega omrežja ali interneta. Trenutni MVP še nima prijave in ga ne smete objaviti na `0.0.0.0`, v LAN ali internet.

Pred dostopom iz drugih naprav je treba kot enoten varnostni sklop dodati: enouporabniško prijavo z varno zgoščenim geslom, skrivnosti iz `.env`, varne sejne piškotke, CSRF zaščito vseh obrazcev, omejitev dovoljenih gostiteljev in dokumentiran postopek ponastavitve gesla. Gesel, licenčnih ključev ali plačilnih podatkov se ne shranjuje v navadnem besedilu.

Internetna objava ni del MVP. Za poznejši HTTPS je predviden reverse proxy (na primer Nginx) na istem Linux strežniku; dodan naj bo šele skupaj s preverjeno avtentikacijo, HTTPS certifikati in ustreznimi omrežnimi pravili.

## Arhitektura

SQLAlchemy model in seja sta ločena od poti FastAPI. Povezava je nastavljiva z `HAM_DATABASE_URL`, vendar MVP podpira in preizkuša samo SQLite. Morebitni prehod na PostgreSQL bo izveden z migracijami, brez sočasnega vzdrževanja dveh baz.

Statični datoteki za slog in HTMX sta vključeni lokalno, zato običajna uporaba ne potrebuje internetne povezave.
