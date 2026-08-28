# Faza 0.1 – pregled ciljnega Linux Docker strežnika

Datum pregleda: 24. avgust 2026  
Strežnik: `10.200.100.11`  
Uporabnik: `ella`

## Status

- SSH dostop z namensko identiteto prek Windows OpenSSH Agenta: **uspešen**.
- Docker okolje: **primerno ob izvedbi spodaj navedenih predpogojev**.
- Pregled je bil izključno read-only. Na strežniku ni bila izvedena nobena sprememba.

## Sistem in viri

| Lastnost | Ugotovitev |
|---|---|
| Operacijski sistem | Ubuntu 26.04 LTS (`resolute`) |
| Arhitektura | `x86_64` / `amd64` |
| Jedro | `7.0.0-28-generic` |
| Docker Engine | klient in strežnik `29.4.1` |
| Docker Compose | `v5.1.3` |
| Docker storage driver | `overlay2` |
| Cgroup driver | `systemd` |
| Procesorji | 12 |
| Pomnilnik | 60 GiB skupaj, približno 54 GiB razpoložljivo ob pregledu |
| Swap | 8 GiB, ob pregledu neuporabljen |
| Korenski disk | 455 GiB, približno 373 GiB prosto |
| `/opt` | ločen ext4 disk 916 GiB, približno 835 GiB prosto |
| Docker podatki | `/var/lib/docker` na korenskem datotečnem sistemu |

## Uporabnik in dovoljenja

Uporabnik `ella` je član skupin `ella`, `adm`, `cdrom`, `sudo`, `dip`, `plugdev`, `lxd`, `docker` in `ollama`. Docker ukazi delujejo brez `sudo`.

Mapa `/opt` ima lastnika `root:root` in dovoljenja `0755`; uporabnik `ella` vanjo ne more pisati. Pred namestitvijo mora skrbnik enkrat ustvariti `/opt/home-assets-management` in jo dodeliti uporabniku oziroma skupini, dogovorjeni za upravljanje HAM. Med pregledom mapa ni obstajala in ni bil zaznan drug projekt z nasprotujočim imenom.

Neposredne projektne mape v `/opt` ob pregledu: `firecrawl`, `gstack`, `hermes_out`, `markitdown`, `mikrodash`, `n8n`, `npm`, `ollama`, `open-webui`, `pihole`, `scrapegraph-api`, `signal-cli` in `wiki`. Sistemski mapi `docker` in `containerd` sta prav tako pod `/opt`.

## Docker okolje in omrežje

Ob pregledu je delovalo 15 vsebnikov; ustavljenih vsebnikov ni bilo. Med pomembnejšimi storitvami so Nginx Proxy Manager, Portainer, Pi-hole, n8n, PostgreSQL, Qdrant, Open WebUI, Firecrawl, Mikrodash in ScrapeGraph API.

Docker omrežja: standardna `bridge`, `host` in `none` ter projektna omrežja `firecrawl_backend`, `mikrodash_default`, `n8n_default`, `npm_default`, `open-webui_default`, `pihole_default` in `scrapegraph-api_default`.

Na vseh vmesnikih so med drugim objavljena TCP vrata `80`, `81`, `443`, `3000`, `3002`, `3081`, `5432`, `5678`, `6333`, `8000`, `8005`, `8080` in `9000`. Prisotna so tudi druga poslušajoča vrata gostitelja. Ta pregled ni spreminjal požarnega zidu ali omrežij.

### Port za HAM

Vrata gostitelja `8000` so zasedena s Portainerjem (`0.0.0.0:8000` in `[::]:8000`). Trenutni `compose.yaml` HAM zato na tem strežniku brez prilagoditve ne more biti zagnan.

Predlagana lokalna vrata za prvo strežniško preverjanje so `8010`; ob pregledu niso bila v uporabi. Dokler HAM nima zahtevanega varnostnega sklopa, morajo biti vezana izključno kot `127.0.0.1:8010:8000` in ne smejo biti objavljena v LAN ali internet. Nginx Proxy Manager naj se v tej fazi še ne poveže s HAM.

## Reverse proxy

Kot Docker vsebnik deluje **Nginx Proxy Manager** in uporablja vrata `80`, `81` ter `443`. Gostiteljske storitve Nginx, Apache, Traefik, Caddy in HAProxy niso bile zaznane kot aktivne. Za morebitno poznejšo HTTPS objavo je smiselno uporabiti obstoječi Nginx Proxy Manager, vendar šele po uvedbi prijave, sej, CSRF zaščite in omejitve gostiteljev.

## Varnostne kopije

Zaznano je rootovo cron opravilo `/etc/cron.d/mi5srv-backup` z dovoljenji `0644`. Njegova vsebina zaradi omejitev pregleda ni bila prebrana, zato iz samega imena ni mogoče potrditi obsega, cilja, retencije ali uspešnosti centralne strategije varnostnih kopij. Namenska orodja Restic, Borg/Borgmatic, Duplicity, Rclone in Rsnapshot niso bila najdena v uporabnikovi poti. Pred deploymentom mora skrbnik potrditi, ali obstoječe opravilo lahko varno vključuje HAM `data/backups/` in `data/attachments/`.

## Tveganja in predpogoji

1. Vrata `8000` so v konfliktu s Portainerjem; uporabiti je treba strežniško prilagoditev na `127.0.0.1:8010:8000`.
2. Uporabnik `ella` ne more ustvariti ciljne mape neposredno pod `/opt`; potreben je enkraten skrbniški poseg.
3. Centralna backup strategija ni potrjena, zaznano je le poimenovano cron opravilo.
4. Docker integracijsko preverjanje Faze 0.2 je uspešno; odprta ostajata varnostni sklop in odločitev o poznejši vključitvi v reverse proxy.
5. Več obstoječih storitev je objavljenih na vseh omrežnih vmesnikih. HAM mora ostati vezan na loopback, dokler ni dodan zahtevani varnostni sklop.

## Predlagani naslednji deployment korak

Prvi deployment je izveden. Naslednji korak naj bo opredelitev funkcionalne Faze 1 oziroma varnostnega sklopa pred kakršnokoli omrežno objavo. Do takrat naj HAM ostane na `127.0.0.1:8010` in nepovezan z Nginx Proxy Managerjem.

## Faza 0.2 – prvi testni Docker deployment

Deployment je bil izveden 24. avgusta 2026 v `/opt/home-assets-management` iz aplikacijskega commita `809e5e834eb68debbbea12b047baad9f494d69dc`. Naknadno je bil prenesen še popravek line-ending pravil iz commita `a29ed23c74bd0a3b8d4072c3597f2587d07037f5`.

### Rezultati

| Preverjanje | Rezultat |
|---|---|
| Compose konfiguracija | uspešna |
| Vezava | `127.0.0.1:8010:8000` |
| Docker build | uspešen, slika `home-assets-management-ham` |
| Zagon vsebnika | uspešen, stanje `healthy` |
| Alembic | `20260824_01 (head)` |
| Health endpoint | HTTP 200, `{"status":"ok"}` |
| Začetna stran | HTTP 200 |
| Testni asset | ID `1`, `HAM INTEGRATION TEST 2026-08-24` |
| Ponovno ustvarjanje | `docker compose up -d --force-recreate` uspešen |
| Trajnost | testni asset ID `1` je ostal prisoten |
| Backup | uspešen, 20.480 bajtov |
| SQLite integrity check | `ok` |
| Backup shema | tabeli `alembic_version` in `assets` |
| Ločena začasna obnova | uspešna; obnovljen isti testni zapis |

Backup je shranjen v `data/backups/ham-20260823-225816.db`. Čas v imenu je čas strežnika (UTC). Začasna obnovitvena baza je bila po uspešnem preverjanju odstranjena; aktivna baza ni bila prepisana.

### Opažena in odpravljena težava

Prvi prenos prek PowerShell cevovoda `git archive | ssh` je na oddaljeni strani pretvoril LF v CRLF, zato Ubuntu ni mogel izvesti `backup-ham.sh`. Projekt je bil ponovno prenesen z binarno varnim TAR/SCP postopkom, dodan pa je bil `.gitattributes` z `eol=lf` za Linux skripte. Po popravku je bilo v `backup-ham.sh` potrjenih nič CR bajtov in backup je uspel.

### Odprte točke

- HAM še nima varnostnega sklopa za dostop iz LAN ali interneta.
- Nginx Proxy Manager ni povezan s HAM.
- Vključitev HAM backupov v obstoječo centralno backup strategijo še ni potrjena.
- Testni asset ID `1` ostaja v bazi kot jasno označen integracijski zapis, ker aplikacija še nima varnega endpointa za brisanje.

## Faza 1.1 – varnostni deployment

Pred buildom mora strežniški `.env` vsebovati naključno `HAM_SESSION_SECRET`; vrednost se ne izpisuje v `docker compose config` ali loge. Po migraciji `20260824_02` se uporabnik inicializira izključno z interaktivnim `docker compose exec ham python -m app.cli set-password`. HAM ostane na `127.0.0.1:8010`; Nginx Proxy Manager še ni vključen. Pred migracijo se preverijo backup, trenutna revizija in asset ID `1`.
## Izolirani LAN dostop

Dne 24. avgusta 2026 je bila po izrecni skrbniški odobritvi strežniška vezava spremenjena na `10.200.100.11:8010`, ker je strežnik izoliran za lokalnimi požarnimi zidovi. Aplikacija prek `HAM_ALLOWED_HOSTS` dovoljuje samo `10.200.100.11`, `127.0.0.1` in `localhost`; zahteva z neznanim `Host` je bila zavrnjena s HTTP 400. Dostop `http://10.200.100.11:8010/login` in health sta bila preverjena z drugega računalnika v omrežju. Nginx Proxy Manager in požarni zid nista bila spremenjena. Ker povezava uporablja HTTP, promet ni šifriran; za širšo ali manj zaupanja vredno uporabo je naslednji korak HTTPS in `HAM_SECURE_COOKIES=true`.
## Zaključek Faze 1.1

Faza 1.1 je bila 24. avgusta 2026 uspešno nameščena in integracijsko preverjena. Aktivna Alembic revizija je `20260824_02`; asset ID `1` je ostal ohranjen. Lokalni uporabnik je inicializiran z interaktivnim CLI, v bazi je samo Argon2id hash. Preverjeni so prijava, odjava, strežniška razveljavitev seje, CSRF, javni health, 30-minutna neaktivnost ter blokada po petih neuspehih.

Pri prvem brskalniškem testu je samodejna zahteva `/favicon.ico` razveljavila anonimno prijavno sejo in povzročila CSRF zavrnitev. Pot je zdaj javna in vrača 204; regresijski test pokriva zaporedje login–favicon–POST. Varnostni dogodki so usmerjeni v Uvicornove Docker loge. V dejanskem preizkusu sta bila zabeležena `logout` in `login_success`, brez gesel, hashov, sejnih skrivnosti, CSRF tokenov ali piškotkov.

Vsebnik je `healthy`, health vrača `{"status":"ok"}`, vezava pa je `10.200.100.11:8010` z omejitvijo dovoljenih gostiteljev. Odprta ostajata HTTPS in nastavitev `HAM_SECURE_COOKIES=true`, preden bi okolje prenehalo biti zaupanja vreden izoliran LAN.
## Faza 1.2 – omejena LAN vezava

Dne 24. avgusta 2026 je bila gostiteljska Docker vezava omejena z `0.0.0.0:8010` na konkretni naslov `10.200.100.11:8010`. Strežniški `.env`, ki ni v Git, vsebuje `HAM_BIND_ADDRESS=10.200.100.11`, `HAM_HOST_PORT=8010` in `HAM_SECURE_COOKIES=false`. `ss` je potrdil poslušanje samo na `10.200.100.11:8010`; wildcard vezava ni prisotna. Health je uspel lokalno na strežniku in z Windows računalnika, prijavna stran je vrnila HTTP 200, vsebnik pa je ostal `healthy`. UFW je aktiven in ni bil spremenjen, saj je bil LAN dostop že dovoljen. Dostop iz interneta ni dovoljen.

## Posodobitev 28. avgusta 2026

Na testni strežnik so bili objavljeni razširjena evidenca in obrazec sredstva, hitri filtri in sortiranje, odzivne mobilne kartice, mobilni fotografski čarovnik, Gemini Interactions API, trajna hramba fotografij ter vgrajeni predogled slik in PDF. Privzeti pogled evidence je `created_at DESC`.

Strežniški `.env` dodatno vsebuje `GEMINI_API_KEY`, `HAM_GEMINI_MODEL=gemini-3.7-flash` in po potrebi `HAM_MAX_ATTACHMENT_BYTES`. Dejanske vrednosti skrivnosti se ne zapisujejo v dokumentacijo ali Git. Pred vsako objavo je bila izdelana SQLite varnostna kopija v `data/backups/`; po zadnji objavi je bil vsebnik `healthy`. Lokalni regresijski sklop je zaključil z 24 uspešnimi testi.

## Dopolnitev 28. avgusta 2026 — upravljanje inventarja

Različica dodaja 60-minutno drsečo sejo, mobilno dodajanje oziroma zamenjavo fotografije obstoječega sredstva, varno združevanje podvojenih evidenčnih zapisov ter virtualna sestavljena sredstva s komponentami. Migracija `20260828_05` doda `is_group`, `parent_id` in `merged_into_id`. Strežniška nastavitev je `HAM_SESSION_MAX_AGE_SECONDS=3600`.

Pred objavo je treba izdelati kopijo aktivne SQLite baze, nato zgraditi vsebnik, preveriti Alembic `20260828_05`, health endpoint, ohranitev obstoječih sredstev ter vrednost sejne nastavitve brez izpisa drugih skrivnosti. Lokalni regresijski sklop vsebuje 28 testov; mobilni pogled je preverjen pri 430 × 932 px brez vodoravnega preliva.
