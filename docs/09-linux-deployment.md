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
4. Docker je nameščen in dostopen, vendar dejanski HAM build, migracija, health check in trajnost podatkov še niso bili integracijsko preverjeni.
5. Več obstoječih storitev je objavljenih na vseh omrežnih vmesnikih. HAM mora ostati vezan na loopback, dokler ni dodan zahtevani varnostni sklop.

## Predlagani naslednji deployment korak

Po izrecni odobritvi sprememb naj skrbnik najprej ustvari `/opt/home-assets-management` z lastnikom in skupino, primernima za uporabnika `ella`. Nato naj se projekt prenese v to mapo in doda strežniška Compose prilagoditev, ki objavi HAM samo kot `127.0.0.1:8010:8000`, pri čemer mora `data/` ostati lokalna vezana mapa na `/opt` disku. Šele nato naj se izvede prvi `docker compose up -d --build`, preveri Alembic migracija, `/health`, ustvarjanje testnega zapisa, ponovna izdelava vsebnika, ohranitev podatkov in SQLite backup/restore. Povezava z Nginx Proxy Managerjem ni del tega koraka.
