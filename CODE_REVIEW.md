# Code Review – Výbušná koťátka

**Datum:** 2026-07-11
**Rozsah:** celý repozitář na commitu `e39e56b` (main.py, app/, static/, Docker/CI)
**Kontext:** Veřejně nasazovaná real-time multiplayer hra (FastAPI + WebSocket, stav v RAM, Docker image na GHCR). Bezpečnostní sekce je proto hodnocena v plném rozsahu.

---

## 1. Shrnutí

Projekt je na poměry "vibecoding" MVP v překvapivě dobré kondici: veškerá herní logika běží server-side, frontend je stateless, vstupy z WebSocketu se validují (typ, délka, JSON), všechna dynamická data v UI procházejí `escapeHtml()` (XSS jsem nenašla) a existuje rate limiting, heartbeat i reconnect. Hlavní rizika jsou dvě: **(a)** dva "zapomenuté" WS handlery (`end_turn`, `restart_game`) bez validace, přes které jde regulérně podvádět nebo rozbít cizí hru, a **(b)** zastaralé závislosti se známými CVE + slabá ochrana admin hesla. Třetí slabina je funkční: per-IP limity nepočítají s reverse proxy, což v produkci buď limity zcela vyřadí, nebo naopak zablokuje legitimní hráče.

---

## 2. Kritické nálezy

### K1. WS zpráva `end_turn` umožňuje ukončit tah bez líznutí karty (cheat)

- **Kde:** `main.py:1000–1011`
- **Co je špatně:** Handler `end_turn` ověří jen to, že jde o aktuálního hráče, a rovnou zavolá `end_turn(session)`. Frontend (`static/app.js`) tuto zprávu nikdy neposílá – je to mrtvý serverový endpoint. Pravidla (i `_docs/Vybusna_kotatka_pravidla.md`, sekce Průběh tahu) říkají, že tah **vždy končí líznutím karty**.
- **Proč to vadí:** Kdokoli s upraveným klientem (stačí `ws.send('{"type":"end_turn"}')` z konzole prohlížeče) může donekonečna předávat tah bez rizika líznutí Výbušného koťátka. Tím je rozbitá základní herní mechanika – nesmrtelnost.
- **Návrh opravy:** Handler úplně odstranit (nikdo ho nepoužívá). Pokud má zůstat pro budoucí použití, musí být povolen jen ve stavech, kdy pravidla dovolují ukončit tah bez lízání (dnes žádný takový není).

### K2. `restart_game` může poslat kdokoli a kdykoli – reset běžící hry

- **Kde:** `main.py:1016–1042`
- **Co je špatně:** Handler nekontroluje `session.status` ani oprávnění. Jediná podmínka je "jsi v místnosti". Frontend tlačítko zobrazuje až po `game_end`, ale server to nevynucuje.
- **Proč to vadí:** Prohrávající hráč může uprostřed hry poslat `restart_game` a celou hru vynulovat (balíček, ruce, tahy). Griefing dostupný na jeden řádek v konzoli.
- **Návrh opravy:** Povolit restart jen když `session.status == GameStatus.FINISHED` (případně navíc jen zakladateli místnosti nebo adminovi). Zvážit i minimální počet hráčů.

### K3. Slabé výchozí admin heslo + neomezený brute-force

- **Kde:** `main.py:33` (`ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "TajneHeslo")`), `main.py:528–533` (porovnání), `docker-compose.yml:11` (default `TvojeSilneHeslo123`)
- **Co je špatně:**
  1. Výchozí hesla jsou natvrdo v repu (a `"TajneHeslo"` je i v git historii od commitu `0c0fb0b`). Kdo nenastaví env proměnnou, běží s veřejně známým heslem.
  2. Pokusy o heslo nejsou nijak penalizovány – limituje je jen obecný rate limit 10 zpráv/s na IP, tj. ~36 000 pokusů za hodinu z jedné IP.
  3. Porovnání přes `!=` místo `secrets.compare_digest` (timing side-channel; u tohoto typu aplikace okrajové, ale oprava je zadarmo).
- **Proč to vadí:** Admin (`is_super_power`) vidí celý balíček (`view_deck`), maže místnosti a vyhazuje hráče. Získání admina = plná kontrola nad hrou.
- **Návrh opravy:** Odstranit default – pokud `ADMIN_PASSWORD` není nastaveno, admin login zakázat (`is_super_power` nikdy nepřidělit). Přidat exponenciální backoff / lockout per IP na neúspěšné pokusy. Použít `secrets.compare_digest`. Do README doplnit, že heslo jde jen přes env.

### K4. Zastaralé závislosti se známými CVE

- **Kde:** `requirements.txt:1–4`
- **Co je špatně:** `fastapi==0.104.1` (tahá Starlette ~0.27), `python-multipart==0.0.6`, `uvicorn==0.24.0` – vše z konce roku 2023. Známé zranitelnosti:
  - `python-multipart` 0.0.6: **CVE-2024-24762** (ReDoS přes Content-Type) a **CVE-2024-53981** (DoS při parsování multipart) – opraveno v 0.0.7 resp. 0.0.18,
  - Starlette < 0.38.6: **CVE-2024-47874** (DoS přes multipart upload bez limitu velikosti).
- **Proč to vadí:** Veřejně dostupná aplikace s HTTP endpointy je snadný cíl DoS. Přitom `python-multipart` tu reálně nejspíš není vůbec potřeba (žádné form uploady).
- **Návrh opravy:** Upgrade `fastapi`/`uvicorn` na aktuální verze, `python-multipart` úplně odstranit z requirements (ověřit, že nic nespadne). Přidat občasnou kontrolu `pip audit`.

### K5. Per-IP limity nefungují za reverse proxy (a naopak škrtí uživatele za NATem)

- **Kde:** `main.py:106–107` (`_client_ip` čte jen `ws.client.host`), `main.py:469` (limit 10 spojení/IP), `main.py:489` (rate limit per IP); `Dockerfile:14` (uvicorn bez `--proxy-headers`)
- **Co je špatně:** Produkční nasazení podle README běží za reverse proxy v docker síti `core`. Bez `--proxy-headers` + `--forwarded-allow-ips` uvidí server u všech klientů IP proxy. Důsledky:
  1. Všichni hráči sdílejí jeden bucket → 11. připojený hráč (nebo 11. zpráva/s celého serveru) je odmítnut = samo-DoS.
  2. Útočník naopak není reálně limitován per-IP, protože limit dopadá na všechny stejně.
  3. I bez proxy: 5 hráčů na jedné školní/firemní síti (NAT) sdílí limit 10 spojení.
- **Proč to vadí:** V produkci je to buď funkční havárie, nebo díra v ochraně – podle topologie.
- **Návrh opravy:** Spouštět uvicorn s `--proxy-headers --forwarded-allow-ips=<IP proxy>` (konfigurovatelně přes env) a v `_client_ip` tomu věřit jen za proxy. Zvážit rate limit per `player_id` (po přihlášení) místo čistě per IP.

---

## 3. Střední priorita

### S1. Chybný error-path ve `play_card`: karta se "spálí" i při chybě

- **Kde:** `app/game_logic.py:291–292` (pop z ruky + discard), poté error returny na `349–356` (FAVOR bez/špatný cíl) a `380–383` (NOPE bez akce)
- **Co je špatně:** Karta se odebere z ruky a přidá do odhazovacího balíčku **před** validací specifickou pro typ karty. Když pak FAVOR/NOPE vrátí `{"error": ...}`, klient dostane chybovou hlášku, ale karta je nenávratně pryč.
- **Návrh opravy:** Provádět validace (cíl FAVOR, existence akce pro NOPE) před `player.hand.pop(...)`, nebo při error returnu kartu vrátit do ruky a odebrat z discard pile.

### S2. NOPE okno nikdy neexpiruje + SHUFFLE nelze vrátit

- **Kde:** `app/game_logic.py:432–441` (uložení `last_action_for_nope`), `184–232` (`_cancel_action_effects` – chybí větev pro SHUFFLE), `main.py:899–906` (vrácení tahu)
- **Co je špatně:** `last_action_for_nope` se přepíše až další zahranou kartou – líznutí ani konec tahu ho nečistí. Hráč tak může "nopnout" akci o několik tahů později: (a) tah se vrátí hráči, který už dávno dohrál (`return_turn_to` + `current_player_id`), (b) u SHUFFLE se nezruší vůbec nic (balíček nejde od-zamíchat), ale tah se přesto vrátí. Výsledek je nekonzistentní stav tahů.
- **Návrh opravy:** Čistit `last_action_for_nope` při `draw_card` a `end_turn` (fyzická hra: nope okno je "než se stane další věc"). U SHUFFLE buď nope zakázat po provedení, nebo alespoň nevracet tah.

### S3. Hráč s prázdnou rukou je vyřazen z game_state (možný softlock)

- **Kde:** `main.py:238–239` a `257–259` (skip hráčů s `len(hand) == 0 and alive`)
- **Co je špatně:** Podmínka vypadá jako pozůstatek single-lobby verze (diváci připojení během hry). Dnes ale připojení do běžící hry server blokuje, takže jediný, koho podmínka trefí, je legitimní hráč, který zahrál/ztratil poslední kartu. Ten přestane dostávat `game_state`, zmizí ostatním ze seznamu a jeho UI zamrzne – přitom podle pravidel (`_docs`: "Pokud nemáš žádné karty, normálně pokračuješ ve hře") má hrát dál.
- **Návrh opravy:** Obě podmínky odstranit; rozhodovat čistě podle `player.alive`.

### S4. Zneškodněné koťátko rozbije konzistenci `peeked_cards`

- **Kde:** `app/game_logic.py:146–151` (draw preferuje `peeked_cards`), `167` (defuse vloží EK na náhodnou pozici, peeked se neaktualizuje)
- **Co je špatně:** Po defusu může být EK vloženo na vršek balíčku, ale pokud mezitím existuje neprázdný `peeked_cards` (globální!), další `draw_card` líže podle zastaralého peeku, ne podle skutečného vršku. "Budoucnost" pak lže a pozice EK se fakticky posouvá.
- **Návrh opravy:** Po defuse-reinsertu vyčistit `session.peeked_cards` (stejně jako to dělá SHUFFLE), nebo peek přestat používat jako zdroj pravdy pro lízání a lízat vždy z `draw_pile[0]`.

### S5. Krátký výpadek spojení = trvalý kick z běžící hry

- **Kde:** `main.py:321–379` (`_force_disconnect_player` hráče **odstraní z lobby**), `382–399` (heartbeat 45 s)
- **Co je špatně:** Heartbeat timeout i obyčejné zavření socketu (finally-blok WS endpointu volá tutéž funkci) vede k okamžitému `alive=False` + odstranění z `session.players`. Postihuje to tedy i **obyčejný refresh stránky (F5)** během hry. Reconnect token sice přežije, ale hráč se vrátí jen do browseru místností – do rozehrané hry se už nedostane (join do PLAYING lobby je blokován). README přitom slibuje "Reconnect funkcionalita". Mobilní hráč, kterému na 50 s zhasne displej, je mrtvý.
- **Návrh opravy:** Oddělit "odpojen" od "odstraněn": při heartbeat timeoutu hráče jen označit jako odpojeného (a případně přeskakovat jeho tahy), z lobby ho mazat až po delší lhůtě (např. 2–5 min). Reconnect pak hráče vrátí do hry.

### S6. Prázdný balíček se hlásí jako "přežil díky Zneškodni"

- **Kde:** `main.py:985–995` vs. `app/game_logic.py:152–161`
- **Co je špatně:** `draw_card` vrací `None` ve dvou nesouvisejících případech: (a) EK bylo zneškodněno, (b) není co líznout (draw i discard prázdné). `main.py` oba případy interpretuje jako defuse a broadcastne `exploding_kitten_defused`. Případ (b) je dnes prakticky nedosažitelný (EK v balíčku zůstávají), ale konflace je časovaná bomba pro budoucí úpravy balíčku.
- **Návrh opravy:** Vracet rozlišený výsledek (např. dict/enum `{"drawn": card}` / `{"defused": True}` / `{"empty": True}`) místo přetíženého `None`.

### S7. Opakovaný `join` na jednom spojení vytváří osiřelé identity + jména blokovaná hodinu

- **Kde:** `main.py:517–560` (join nekontroluje, že `player_id` už existuje), `301–318` (cleanup až po expiraci tokenu), `535–538` (kontrola jmen proti celému registry)
- **Co je špatně:** (1) Přihlášený klient může poslat další `join` a vyrobit novou identitu – stará zůstane v `player_registry`/`token_map` až hodinu. (2) Jméno hráče, který zavřel prohlížeč (sessionStorage nepřežije zavření tabu), je blokované až do expirace tokenu. (3) Útočník může přes opakované joiny plnit registry (~36k záznamů/h z jedné IP) – pomalý memory DoS.
- **Návrh opravy:** Odmítnout `join`, pokud už `player_id` na spojení existuje. Uvolňovat registry záznamy dřív, pokud hráč není v lobby a nemá spojení (např. po 5 min). Zvážit strop celkového počtu záznamů v registry.

### S8. CORS: wildcard origin + `allow_credentials=True`

- **Kde:** `main.py:34` (default `ALLOWED_ORIGINS="*"`), `423–429`
- **Co je špatně:** Kombinace `allow_origins=["*"]` s `allow_credentials=True` vede u Starlette k zrcadlení libovolného originu s povolenými credentials. Aplikace dnes cookies nepoužívá, takže reálný dopad je malý, ale konfigurace je nebezpečný vzor. Stejný default `*` vypíná i origin-check WebSocketu (`_is_origin_allowed`), takže se na cizí web dá napsat stránka, která se připojí k serveru jménem návštěvníka.
- **Návrh opravy:** `allow_credentials=False` (nic je nepotřebuje) a v produkci vždy nastavit konkrétní `ALLOWED_ORIGINS`; do README přidat důrazné doporučení.

### S9. Sémantika řetězeného ATTACK neodpovídá pravidlům ani README

- **Kde:** `app/game_logic.py:306–322` (`new_turns = cur_turns + 1`)
- **Co je špatně:** README říká "+1 tah navíc (2 tahy celkem)". Implementace ale kumuluje: A zaútočí → B má 2 tahy; B zaútočí → C má 3 tahy; atd. Oficiální pravidla original edice: napadený hráč, který zahraje Attack, předá **2 tahy** (nekumuluje se do 3+). Něčemu z toho se implementace musí přizpůsobit.
- **Návrh opravy:** Rozhodnout zamýšlené chování, srovnat kód + README + `_docs`. Nejjednodušší varianta věrná pravidlům: pokud `cur_turns > 1`, předat `cur_turns` (přenos), jinak 2.

### S10. Dokumentační nesoulady

- **Kde:** `README.md:81, 99–100` (port 80) vs. `docker-compose.yml:9` (`8080:8000`); README sekce Struktura projektu nezmiňuje `super_power.html`, `version.json`, multi-lobby; README nezmiňuje env proměnné `ADMIN_PASSWORD`, `ALLOWED_ORIGINS`, `MAX_LOBBIES` atd.
- **Proč to vadí:** Návod na deployment nesedí s realitou; admin rozhraní a jeho konfigurace nejsou zdokumentované vůbec.
- **Návrh opravy:** Sjednotit porty, doplnit tabulku env proměnných a aktuální strukturu.

---

## 4. Nice-to-have

1. **Testy neexistují.** Prioritní scénáře k pokrytí (unit testy `app/game_logic.py` jsou levné, nemají I/O):
   - `draw_card`: EK + defuse (reinsert), EK bez defuse (smrt), lízání podle peeked_cards,
   - NOPE řetězy: nope → double-nope → triple-nope pro ATTACK/SKIP/FAVOR (vrácení karty),
   - `end_turn` + `pending_turns`: attack chain, skip pod attackem, smrt současného hráče,
   - `initialize_game`: počty karet, žádné EK v ruce, EK = hráči − 1,
   - integrace WS (httpx/starlette TestClient): join → create_lobby → ready → hra; odmítnutí cizího tahu, odmítnutí `end_turn`/`restart_game` po opravě K1/K2.
2. **`main.py` je 1200řádkový monolit** – `websocket_endpoint` má ~760 řádků. Rozdělit na dispatch tabulku `{msg_type: handler}` v samostatném modulu; zlepší čitelnost i testovatelnost.
3. **Dockerfile:** kontejner běží jako root – přidat `USER` s neprivilegovaným uživatelem; přidat `HEALTHCHECK` (endpoint `/health` už existuje); rozšířit `.dockerignore` o `_docs/`, `images/`, `generate_sounds.py`, `terminals` artefakty.
4. **Mrtvý kód:** `GameSession.last_reset_time` (`app/models.py:80`) se nikde nepoužívá; nedosažitelná větev `join_lobby` → `send_game_state` (`main.py:717–718`, join do PLAYING je blokován výš); `X-XSS-Protection` hlavička (`main.py:86`) je v moderních prohlížečích deprecated (neškodí, ale nic nedělá).
5. **`showError` zapisuje jen do `#login-error`** (`static/app.js:306–313`) – chyby serveru během hry (např. "Není váš tah") uživatel nikdy neuvidí, protože element je na skrytém login screenu. Přidat toast/hlášku i do herní obrazovky.
6. **`super_power.html` monkey-patchuje globální funkce** (`window.updateLobby`, `window.handleMessage`) a páruje hráče podle zobrazeného jména (`textContent.trim()`), ne podle `player_id` – křehké, při přejmenování CSS tříd nebo shodě jmen se rozbije. Lepší je feature-flag přímo v `app.js` (`is_super_power` už klient zná).
7. **Kombinace karet** (2×/3× stejná, 5 různých) z `_docs/Vybusna_kotatka_pravidla.md` nejsou implementované a README je nezmiňuje ani jako omezení – doplnit do "známá omezení", ať se to nehledá v kódu.
8. **FAVOR bere náhodnou kartu**, oficiální pravidla říkají "cílový hráč dá kartu dle svého výběru". README to dokumentuje jako záměr – jen potvrdit, že jde o vědomé zjednodušení, a poznamenat v `_docs`.
9. **Tokeny přes `uuid.uuid4()`** – v CPythonu je pod tím `os.urandom`, takže entropie je OK; idiomatičtější je `secrets.token_urlsafe(32)`. Nízká priorita.
10. **`player_registry` jako volný dict** (`main.py:98–99`) – klíče `name`/`token`/`lobby_id` bez typové kontroly; dataclass by odchytila překlepy (zbytek kódu dataclassy používá, tady je výjimka).
11. **Kontrola velikosti zprávy až po přijetí** (`main.py:485`) – zprávu už server přečetl do paměti; skutečný strop drží default limit `websockets` (~1 MB). Nastavit `--ws-max-size` uvicornu na ~4 kB a interní check nechat jen jako druhou vrstvu.

---

## Jak postupovat

Doporučené pořadí oprav: **K1 + K2** (pár řádků, okamžitě zavřou cheaty) → **K4** (upgrade závislostí) → **K3** (admin heslo) → **K5** (proxy headers, nutné před produkčním nasazením za proxy) → S1–S6 (herní logika) → zbytek dle chuti.

Žádná změna z tohoto reportu zatím nebyla aplikována – čekám na výběr nálezů k opravě.
