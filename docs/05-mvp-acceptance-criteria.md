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

## Faza 1.2

- `/assets` brez parametrov vrne aktivna sredstva po `created_at DESC`.
- Filtri, izbrano sortiranje, smer in velikost strani se ohranijo v povezavah paginacije.
- Čarovnik lahko v eni analizi pošlje eno do tri veljavne JPG, PNG ali WebP slike.
- Po uspešni analizi uporabnik popravi podatke, potrdi zapis in dobi neposredno povezavo do ustvarjenega sredstva.
- Potrjene fotografije so povezane s sredstvom; neuspešna analiza ne ustvari sredstva.
- Gemini strukturirani odgovor se pravilno prebere iz trenutne ovojnice Interactions API.
- Predogled priloge vrne `inline`, ločena pot za prenos pa `attachment`.
- Dodajanje in zamenjava fotografije obstoječega sredstva delujeta prek mobilnega obrazca; zamenjana neuporabljena datoteka se odstrani.
- Združitev dopolni manjkajoče podatke glavnega sredstva, prenese priloge in arhivira izvor z `merged_into_id`.
- Sestavljeno sredstvo ohrani komponente kot ločene zapise in omogoča njihovo odpenjanje.
- Mobilni pogled pri širini 430 px nima vodoravnega preliva; izbira več sredstev in fotografiranje sta dosegljiva.
- Celoten avtomatski sklop vsebuje 28 uspešnih testov.
