# Arhitekturne odločitve

## ADR-001: Lokalna enouporabniška avtentikacija

Uporabljen je Argon2id prek `argon2-cffi`. Registracija, vloge, OAuth in zunanji ponudniki niso del MVP.

## ADR-002: Podpisana in strežniško preverljiva seja

Starlette podpisuje `HttpOnly`, `SameSite=Lax` piškotek. Naključni session ID se zgoščeno preverja v uporabniškem zapisu, kar omogoča takojšnjo razveljavitev brez dodatnega servisa. Produkcijski HTTPS mora vključiti `HAM_SECURE_COOKIES=true`.

## ADR-003: CSRF in omejevanje prijav

CSRF token je naključen in vezan na podpisano sejo. SQLite uporabniški zapis hrani števec neuspehov ter čas blokade; meja je 5 poskusov in 15 minut. Redis ni potreben za eno instanco.
## ADR-004: HTTP samo v zaupanja vrednem domačem omrežju

HAM je objavljen na konkretnem LAN naslovu `10.200.100.11:8010`, ne na wildcard naslovu. Za zdaj se zavestno uporablja HTTP in `HAM_SECURE_COOKIES=false`; javna domena, internetni dostop, TLS in Nginx Proxy Manager niso vključeni. Uporabniško geslo mora biti unikatno. Pred kakršnimkoli dostopom iz nezaupanja vrednega omrežja sta obvezna HTTPS in nastavitev `HAM_SECURE_COOKIES=true`.