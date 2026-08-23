# Arhitektura

HAM je monolitna FastAPI aplikacija s strežniško izrisanim Jinja2/HTMX vmesnikom in SQLite bazo prek SQLAlchemy 2 ter Alembic migracij.

## Varnostna plast

En aktivni `LocalUser` hrani samo Argon2id hash in stanje blokade. Podpisani sejski piškotek vsebuje naključni identifikator, uporabniški ID, CSRF token in čas zadnje aktivnosti; SHA-256 identifikatorja se preverja proti bazi. S tem odjava ali sprememba gesla strežniško razveljavi sejo. Piškotek je `HttpOnly`, `SameSite=Lax`, ima 30-minutno neaktivnost in podpira `Secure` prek nastavitve.

Javne poti so samo `/login`, `/health` in `/static`. HTML zahteve se preusmerijo na prijavo, `/api/*` brez seje vrne 401. Vsi trenutni spreminjajoči obrazci preverjajo sejno vezan CSRF token. Varnostni logger beleži samo vrste dogodkov, nikoli poverilnic ali tokenov.