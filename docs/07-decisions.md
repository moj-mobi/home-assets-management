# Arhitekturne odločitve

## ADR-001: Lokalna enouporabniška avtentikacija

Uporabljen je Argon2id prek `argon2-cffi`. Registracija, vloge, OAuth in zunanji ponudniki niso del MVP.

## ADR-002: Podpisana in strežniško preverljiva seja

Starlette podpisuje `HttpOnly`, `SameSite=Lax` piškotek. Naključni session ID se zgoščeno preverja v uporabniškem zapisu, kar omogoča takojšnjo razveljavitev brez dodatnega servisa. Produkcijski HTTPS mora vključiti `HAM_SECURE_COOKIES=true`.

## ADR-003: CSRF in omejevanje prijav

CSRF token je naključen in vezan na podpisano sejo. SQLite uporabniški zapis hrani števec neuspehov ter čas blokade; meja je 5 poskusov in 15 minut. Redis ni potreben za eno instanco.