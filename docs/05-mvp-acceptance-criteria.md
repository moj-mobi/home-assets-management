# Sprejemni kriteriji MVP

## Faza 1.1

- Migracija `20260824_02` ohrani obstoječe assete.
- Neprijavljen uporabnik ne more videti ali spreminjati HAM podatkov.
- Pravilne poverilnice ustvarijo novo veljavno sejo; napačne vrnejo splošno napako.
- Peta zaporedna napaka sproži 15-minutno blokado, uspeh pa števec ponastavi.
- Odjava strežniško razveljavi sejo.
- Manjkajoč ali napačen CSRF token zavrne spremembo.
- Veljavna HTMX zahteva deluje.
- Gesla, hashi, sejne skrivnosti, tokeni in piškotki niso v logih.
- Strežniški zagon brez dovolj dolge `HAM_SESSION_SECRET` varno odpove.