# Arhitektura

HAM je monolitna FastAPI aplikacija s strežniško izrisanim Jinja2/HTMX vmesnikom in SQLite bazo prek SQLAlchemy 2 ter Alembic migracij.

## Evidenca in datoteke

Model `Asset` hrani opisne, nakupne, jamstvene in arhivske podatke. Samoreferenčni `parent_id` poveže komponente z virtualnim sestavljenim sredstvom, `merged_into_id` pa ohrani sled združitve podvojenega zapisa. `Attachment` hrani metapodatke, dejanska vsebina pa je pod naključnim internim imenom v `data/attachments/`. Povezovalna tabela omogoča, da je ena potrjena priloga povezana z enim ali več sredstvi. Začasne, nepotrjene priloge se po 24 urah počistijo.

Pot `/attachments/{id}` je namenjena avtenticiranemu vgrajenemu predogledu in vrne `Content-Disposition: inline`; `/attachments/{id}/download` je izrecna možnost prenosa. Brisanje ostaja CSRF-zaščiteno.

## Zajem in prepoznava

Ročni vnos, lokalna OCR-predizpolnitev računa in mobilni fotografski čarovnik se zaključijo v istem validiranem zapisu sredstva. Čarovnik združi največ tri slike v eno zahtevo Gemini Interactions API, zahteva strukturiran JSON in uporabniku vedno pokaže popravljiv pregled pred potrditvijo. API ključ je samo v okolju procesa; fotografije se trajno povežejo šele ob potrditvi sredstva.

## Upravljanje inventarja

Združitev podvojenih zapisov dopolni samo prazna polja izbranega glavnega zapisa, nanj prenese priloge in morebitne komponente ter izvorne zapise mehko arhivira z revizijsko povezavo. Sestavljeno sredstvo je virtualni nadrejeni zapis; komponente ostanejo polnopravna sredstva in jih je mogoče brez brisanja odpeti ali ponovno povezati. Fotografija obstoječega sredstva se doda kot priloga ali zamenja izbrano staro fotografijo.

## Varnostna plast

En aktivni `LocalUser` hrani samo Argon2id hash in stanje blokade. Podpisani sejski piškotek vsebuje naključni identifikator, uporabniški ID, CSRF token in čas zadnje aktivnosti; SHA-256 identifikatorja se preverja proti bazi. S tem odjava ali sprememba gesla strežniško razveljavi sejo. Piškotek je `HttpOnly`, `SameSite=Lax`, ima privzeto 60-minutno neaktivnost in podpira `Secure` prek nastavitve.

Javne poti so samo `/login`, `/health` in `/static`. HTML zahteve se preusmerijo na prijavo, `/api/*` brez seje vrne 401. Vsi trenutni spreminjajoči obrazci preverjajo sejno vezan CSRF token. Varnostni logger beleži samo vrste dogodkov, nikoli poverilnic ali tokenov.
