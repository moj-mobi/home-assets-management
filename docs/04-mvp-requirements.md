# Zahteve MVP

## Faza 1.1

- Natanko en lokalni aktivni uporabnik brez registracije ali vlog.
- Geslo je shranjeno samo kot Argon2id hash in nastavljeno interaktivno.
- Brez inicializiranega uporabnika podatki niso dostopni.
- Sejna skrivnost je obvezna v strežniškem načinu in ni v Git.
- Neaktivna seja poteče po 30 minutah; odjava in sprememba gesla jo razveljavita.
- Po 5 zaporednih neuspehih je račun blokiran 15 minut.
- Vsi spreminjajoči obrazci, vključno s HTMX in odjavo, zahtevajo CSRF token.
- `/health` ostane javen in vrača samo `{"status":"ok"}`.