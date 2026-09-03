# Arhitekturne odločitve

## ADR-001: Lokalna enouporabniška avtentikacija

Uporabljen je Argon2id prek `argon2-cffi`. Registracija, vloge, OAuth in zunanji ponudniki niso del MVP.

## ADR-002: Podpisana in strežniško preverljiva seja

Starlette podpisuje `HttpOnly`, `SameSite=Lax` piškotek. Naključni session ID se zgoščeno preverja v uporabniškem zapisu, kar omogoča takojšnjo razveljavitev brez dodatnega servisa. Produkcijski HTTPS mora vključiti `HAM_SECURE_COOKIES=true`.

## ADR-003: CSRF in omejevanje prijav

CSRF token je naključen in vezan na podpisano sejo. SQLite uporabniški zapis hrani števec neuspehov ter čas blokade; meja je 5 poskusov in 15 minut. Redis ni potreben za eno instanco.
## ADR-004: HTTP samo v zaupanja vrednem domačem omrežju

HAM je objavljen na konkretnem LAN naslovu `10.200.100.11:8010`, ne na wildcard naslovu. Za zdaj se zavestno uporablja HTTP in `HAM_SECURE_COOKIES=false`; javna domena, internetni dostop, TLS in Nginx Proxy Manager niso vključeni. Uporabniško geslo mora biti unikatno. Pred kakršnimkoli dostopom iz nezaupanja vrednega omrežja sta obvezna HTTPS in nastavitev `HAM_SECURE_COOKIES=true`.

## ADR-005: Izbirna Gemini analiza fotografij

Mobilni čarovnik uporablja Google Gemini Interactions API z modelom `gemini-3.7-flash` in strukturirano izhodno shemo. Vse izbrane fotografije se analizirajo v eni zahtevi, vendar AI nikoli ne zapisuje neposredno v bazo: uporabnik mora podatke pregledati in potrditi. API ključ se upravlja prek Nastavitve / AI in hrani v zasebni datoteki `data/private/gemini.json`; `.env` je združljivostna možnost, dokler zasebna nastavitev ne obstaja. Osnovna evidenca ostane uporabna brez ključa.

## ADR-006: Datoteke lokalno, predogled privzeto

Izvirne priloge ostanejo na lokalnem podatkovnem nosilcu, v SQLite pa so metapodatki in povezave. Privzeti klik uporabi avtenticiran vgrajeni predogled z dispozicijo `inline`; prenos je ločena uporabniška odločitev. S tem ogled ne povzroči neželenega prenosa, izvirnik pa ostane dosegljiv.

## ADR-007: Revizijska združitev in virtualna sestavljena sredstva

Podvojeni zapisi se ne izbrišejo: izbrani glavni zapis se dopolni, izvori pa se mehko arhivirajo in povežejo z `merged_into_id`. Sestavljeno sredstvo je označeno z `is_group`, komponente pa imajo `parent_id`. Tako ostanejo njihove serijske številke, priloge in življenjski cikel neodvisni, uporabnik pa jih lahko upravlja kot celoto.

## ADR-008: Drseča 60-minutna seja

Veljavnost seje se ob aktivnosti podaljšuje in privzeto poteče po 3600 sekundah neaktivnosti. Nastavitev `HAM_SESSION_MAX_AGE_SECONDS` omogoča prilagoditev brez spremembe kode; odjava in sprememba gesla še vedno takoj razveljavita sejo.

## ADR-009: Stabilna inventarna številka in prenosljiva NIIMBOT predloga

Inventarna številka uporablja stabilno obliko `HAM-NNNNNN`, vezano na notranji ID, in se po združevanju ali preimenovanju ne spremeni. QR nosi samo naziv in inventarno številko. Zaradi lastniškega Bluetooth postopka tiskalnikov HAM ne poskuša neposredno upravljati naprave iz brskalnika, temveč izdela PNG pravilne fizične velikosti in DPI za uvoz v uradno NIIMBOT aplikacijo.
