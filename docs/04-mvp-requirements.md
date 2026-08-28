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

## Faza 1.2

- Evidenca ima datum nakupa, filtre in sortiranje po stolpcih ter privzeto pokaže najnovejše vnose.
- Mobilni pogled uporablja kartice in je uporaben na telefonu Google Pixel 9 XL brez vodoravnega drsenja.
- Mobilni čarovnik sprejme fotografije sredstva, serijske številke in nalepke ter jih analizira skupaj.
- Gemini prepoznani podatki so pred zapisom vedno prikazani v popravljivem obrazcu.
- Potrditev čarovnika atomarno zapiše sredstvo in poveže vse fotografije.
- Fotografije in PDF se primarno odprejo v vgrajenem predogledu; prenos je ločena možnost.
- Gemini integracija je izbirna in ne razkrije API ključa v HTML, dnevnikih ali Git repozitoriju.
