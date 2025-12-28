# Výbušná koťátka - Online hra MVP

Online webová hra inspirovaná hrou "Výbušná koťátka" (Exploding Kittens) - single-lobby MVP verze.

## Popis

Jednoduchá online hra pro 2-5 hráčů, kde se všichni hráči připojují do jednoho společného lobby. Hra běží v reálném čase pomocí WebSocket komunikace.

## Technický stack

- **Backend**: FastAPI (Python 3.11)
- **Realtime komunikace**: WebSocket (`/ws`)
- **Frontend**: HTML + CSS + vanilla JavaScript
- **Deployment**: Docker + Docker Compose

## Funkce

- ✅ Přihlášení hráčů do lobby (max 5 hráčů)
- ✅ Ready mechanika - hra začne automaticky, když jsou všichni připraveni
- ✅ Realtime herní komunikace přes WebSocket
- ✅ Všechny základní karty (Zneškodni, Přeskoč, Zaútoč, Zamíchej, Pohledni do budoucnosti, Tohle si vezmu, Nené)
- ✅ Automatické spuštění hry při připravenosti všech hráčů
- ✅ Auto-reset lobby po 60 sekundách, pokud je prázdná
- ✅ Reconnect funkcionalita pomocí tokenu
- ✅ **Blokování nových hráčů během probíhající hry** (reconnect stále funguje)
- ✅ **Responzivní design pro mobilní zařízení (iPhone, Android)**
- ✅ Touch-friendly ovládání
- ✅ Optimalizace pro malé obrazovky
- ✅ **Chat s časem hraní** - každá zpráva má časové razítko na jednom řádku s textem (úspora místa)
- ✅ **Chat seřazený nejnovějšími zprávami nahoru**
- ✅ **Barevné zprávy v chatu**:
  - Modrá barva: když někdo přežije Výbušné koťátko pomocí Zneškodni
  - Hnědá barva: když někdo zemře
- ✅ **Karty zobrazují pouze název** - popis se zobrazí při najetí myši (desktop) nebo dlouhém tapu (mobil)
- ✅ **Tlačítko "Začít novou hru"** po dokončení hry
- ✅ **Možnost odejít z lobby** - po opuštění lobby se může hráč znovu přihlásit bez obnovení stránky
- ✅ **Zvukové efekty** - zvuk pro výbušné koťátko (když hráč umře) a konec hry
- ✅ **Karty seřazené podle typu** v ruce hráče
- ✅ **Zobrazení počtu tahů** u jména hráče v závorce (např. "Hráč (2)")

## Herní pravidla

### Karty
- **Výbušné koťátko**: Pokud si ho lízneš a nemáš Zneškodni, okamžitě končíš (vypadáváš ze hry). Výbušné koťátko se do balíčku už nevrací.
- **Zneškodni**: Zabrání výbuchu Výbušného koťátka. Zneškodni se odebere z ruky a Výbušné koťátko se vloží zpět do balíčku **na náhodnou pozici**
- **Přeskoč**: Okamžitě ukončíš svůj tah bez lízání
- **Zaútoč**: Tvůj tah končí a další hráč má **+1 tah navíc** (tj. bude hrát 2 tahy celkem, pokud měl standardně 1)
- **Zamíchej**: Zamíchá dobírací balíček (globálně)
- **Pohlédni do budoucnosti**: Podívej se na několik vrchních karet balíčku (výbušná koťátka se zobrazí jako "Výbušné koťátko"; při líznutí se zpracují normálně)
- **Tohle si vezmu**: Vezmeš si náhodnou kartu od jiného hráče (**nikdy ne Výbušné koťátko**)
- **Nené**: Zruší akci jiné karty (first click wins)

### Setup
- Každý hráč začíná s **7 kartami z balíčku + 1× Zneškodni**
- Exploding Kittens: počet hráčů − 1
- Balíček je zamíchán
- Server určí prvního hráče

### Cíl hry
Vyhrává poslední živý hráč.

## Detailní herní logika

### Inicializace hry

1. **Vytvoření balíčku**:
   - Vytvoří se balíček podle konfigurace (`base.json`)
   - Přidají se výbušná koťátka (počet hráčů - 1)
   - Balíček se zamíchá

2. **Rozdávání karet**:
   - Každý hráč dostane 7 náhodných karet z balíčku
   - **DŮLEŽITÉ**: Výbušná koťátka se při rozdávání přeskočí a vrátí do balíčku
   - Každý hráč dostane navíc 1× Zneškodni
   - Po rozdání se balíček znovu zamíchá
   - **Bezpečnostní kontrola**: Pokud by se výbušné koťátko dostalo do ruky, automaticky se odstraní a vrátí do balíčku

3. **Určení prvního hráče**:
   - První hráč v seznamu začíná
   - Nastaví se `pending_turns = 1` pro prvního hráče

### Průběh tahu

1. **Hráč může hrát akční karty**:
   - Může hrát libovolné karty z ruky
   - Některé karty ukončí tah automaticky (Přeskoč, Zaútoč)
   - Jiné karty umožňují pokračovat v tahu

2. **Ukončení tahu**:
   - Tah se ukončí automaticky při:
     - Líznutí karty
     - Zahraní karty Přeskoč
     - Zahraní karty Zaútoč
   - Pokud hráč má `pending_turns > 1`, zůstane na tahu
   - Jinak se přepne na dalšího živého hráče

3. **Líznutí karty**:
   - Pokud existují globální `peeked_cards`, lízne se první karta z nich (respektuje se pořadí pro všechny)
   - Jinak se lízne první karta z `draw_pile`
   - Pokud je balíček prázdný, zamíchá se `discard_pile` a použije se jako nový `draw_pile`

### Detailní logika karet

#### Výbušné koťátko (EXPLODING_KITTEN)
- **Může být pouze v balíčku** (nikdy v ruce, nikdy přes FAVOR)
- **Když hráč lízne výbušné koťátko**:
  - Pokud má Zneškodni: Zneškodni se odebere z ruky a výbušné koťátko se vloží náhodně zpět do balíčku
  - Pokud nemá Zneškodni: hráč vypadává (`alive = False`) a výbušné koťátko se **do balíčku už nevrací** (odstraní se ze hry / graveyard)
- Zvuk exploze se přehrává všem hráčům, když někdo vypadne

#### Zneškodni (DEFUSE)
- Každý hráč začíná s 1× Zneškodni
- **Nelze normálně zahrat** - používá se pouze automaticky, když hráč lízne výbušné koťátko
- Zabraňuje smrti hráče
- V dobíracím balíčku je stejný počet Zneškodni karet jako Exploding Kittens

#### Přeskoč (SKIP)
- Okamžitě ukončí tah hráče
- Hráč nemusí líznout kartu
- Tah se přepne na dalšího hráče

#### Zaútoč (ATTACK)
- Okamžitě ukončí tah hráče
- Další hráč v pořadí dostane **+1 tah navíc**:
  - implementačně: `pending_turns[next_player] += 1`
- Pokud další hráč nemá `pending_turns` nastavené, nastaví se standardně na 1 a pak se přičte +1 → výsledně 2
- **Kumulativní efekt**: Pokud další hráč také zahraje ATTACK, další hráč v pořadí dostane znovu +1 tah navíc (tahy se sčítají)
- **Příklad**: Hráč A zahraje ATTACK → Hráč B má 2 tahy. Hráč B zahraje ATTACK → Hráč C má 3 tahy. Hráč C zahraje ATTACK → Hráč D má 4 tahy.

#### Zamíchej (SHUFFLE)
- Zamíchá `draw_pile` náhodně (globálně)
- Vymaže `peeked_cards` **všem hráčům**
- Neukončuje tah

#### Pohlédni do budoucnosti (SEE_FUTURE)
- Zobrazí top 3 karty z `draw_pile`
- Uloží se do globálního `peeked_cards` pro respektování pořadí (pro všechny hráče)
- Výbušná koťátka se zobrazí jako "Výbušné koťátko"
- Při líznutí se bere první karta z globálního `peeked_cards` (v původním pořadí)
- Pokud je v balíčku méně než 3 karty, zobrazí se všechny dostupné

#### Tohle si vezmu (FAVOR)
- Vyžaduje cílového hráče
- Cílový hráč odevzdá náhodnou kartu
- **NIKDY to nemůže být výbušné koťátko** (filtr pouze z běžných karet)
- Pokud cílový hráč nemá žádnou běžnou kartu, akce selže (server vrátí chybu)
- **Cílový hráč je informován**, jakou kartu si od něj vzali

#### Nené (NOPE)
- Zruší poslední akci (first click wins)
- **Může zrušit jakoukoliv kartu, kromě Zneškodni**
- **Může zrušit jinou NOPE kartu** - pokud někdo zahraje NOPE, další hráč může zrušit tuto NOPE kartu
- Uloží se do `last_action_for_nope` pro další NOPE karty
- MVP implementace: jednoduché označení zrušení akce

### Mechanika pending_turns

- Každý hráč má `pending_turns` (počet zbývajících tahů)
- Při inicializaci: první hráč má `pending_turns = 1`
- Při ukončení tahu:
  - `pending_turns` aktuálního hráče se sníží o 1
  - Pokud `pending_turns > 0`, hráč zůstane na tahu
  - Pokud `pending_turns = 0`, přepne se na dalšího hráče
- Nový hráč dostane `pending_turns = 1` (pokud ještě nemá)
- ATTACK karta přidá `pending_turns += 1` dalšímu hráči (tj. standardně z 1 na 2)
- **Kumulativní ATTACK**: Pokud několik hráčů za sebou zahraje ATTACK, každý další hráč dostane +1 tah navíc (tahy se sčítají)
- **Příklad**: Hráč A zahraje ATTACK → Hráč B má 2 tahy. Hráč B zahraje ATTACK → Hráč C má 3 tahy. Hráč C zahraje ATTACK → Hráč D má 4 tahy.

### Konec hry

- Pokud hráč vypadne, pokračují jen ostatní
- Hra končí, když zbývá pouze **1 živý hráč** → ten vyhrává
- Po konci hry:
  - Status se nastaví na `FINISHED`
  - Všichni hráči mají `ready = False`
  - Zobrazí se tlačítko "Začít novou hru"
  - Přehrává se zvuk konce hry

### Bezpečnostní kontroly

1. **Výbušné koťátko v ruce**:
   - Při inicializaci: výbušná koťátka se přeskočí při rozdávání
   - Bezpečnostní kontrola po inicializaci: odstraní všechny výbušná koťátka z rukou
   - Při FAVOR: filtruje se pouze z běžných karet
   - Při líznutí: výbušné koťátko se zpracuje speciálně, nikdy se nepřidá do ruky

2. **Mrtví hráči a pending_turns**:
   - Pokud hráč zemře (lízne výbušné koťátko bez Zneškodni), jeho `pending_turns` se automaticky vymažou
   - Mrtví hráči nemohou mít aktivní tahy - pokud má mrtvý hráč `pending_turns`, tah se okamžitě přepne na dalšího živého hráče

3. **Validace tahů**:
   - Hráč může hrát pouze na svůj tah
   - Hráč musí být živý (`alive = True`)
   - Karta musí být v ruce hráče
   - FAVOR vyžaduje cílového hráče
   - DEFUSE nelze normálně zahrat (pouze automaticky při líznutí výbušného koťátka)

4. **Synchronizace stavu**:
   - Každý hráč vidí pouze své karty
   - Ostatní hráči vidí pouze počet karet
   - Server validuje všechny akce

### Peeked cards (Pohlédni do budoucnosti)

- `peeked_cards` je **globální** (`List[Card]`) - respektuje se pořadí pro všechny hráče
- Když někdo použije "Pohlédni do budoucnosti", uloží se top 3 karty do globálního `peeked_cards`
- Při líznutí se bere první karta z globálního `peeked_cards` (pokud existuje)
- Karta se odstraní z `draw_pile` podle ID
- Pokud se balíček zamíchá (SHUFFLE), `peeked_cards` se vymažou
- Pokud se balíček vyčerpá a zamíchá discard pile, `peeked_cards` se vymažou

### Restart hry

- Restart je možný pouze po skončení hry (`status = FINISHED`)
- Resetuje se:
  - Status na `WAITING`
  - Všichni hráči: `ready = False`, `alive = True`
  - Volá se `initialize_game()` pro novou hru
- Hráči zůstávají v lobby

## Instalace a spuštění

### Předpoklady
- Docker a Docker Compose

### Spuštění (lokální vývoj)

```bash
docker compose up -d --build
```

Aplikace bude dostupná na: `http://localhost:8000`

### Zastavení

```bash
docker compose down
```

## Deployment (Synology)

Aplikace je dostupná jako public Docker image z GitHub Container Registry (GHCR).

### Stáhnutí image

Image je automaticky dostupná na: `ghcr.io/elvisek2020/web-exploding_kitten:latest`

V Synology Container Manager:
1. Otevřete **Container Manager**
2. Přejděte na **Registry**
3. Vyhledejte `ghcr.io/elvisek2020/web-exploding_kitten`
4. Stáhněte image (nebo použijte docker-compose.yml níže)

### Spuštění pomocí docker-compose.yml

Vytvořte soubor `docker-compose.yml` s následujícím obsahem:

```yaml
services:
  vybusna-kotatka:
    image: ghcr.io/elvisek2020/web-exploding_kitten:latest
    container_name: vybusna-kotatka
    ports:
      - "80:8000"
    restart: unless-stopped
```

V Synology Container Manager:
1. Otevřete **Container Manager**
2. Přejděte na **Project**
3. Vytvořte nový projekt a naimportujte `docker-compose.yml`
4. Spusťte projekt

Aplikace bude dostupná na: `http://<synology-ip>:80`

### Aktualizace image

Pro aktualizaci na nejnovější verzi:

```bash
docker compose pull
docker compose up -d
```

Nebo v Synology Container Manager:
1. Otevřete projekt
2. Klikněte na **Action** → **Update**
3. Container Manager automaticky stáhne nejnovější image a restartuje kontejner

### Poznámky

- Image je **public** - není potřeba autentizace pro stažení
- Aplikace běží na portu **80** (mapuje se z kontejneru port 8000)
- Image podporuje architektury: `linux/amd64` a `linux/arm64`
- Image je automaticky buildována při push do `main` branch
- Každý build má tag `latest` a `sha-<commit-hash>`

## Struktura projektu

```
Vybusna_kotatka_online/
├── app/
│   ├── __init__.py
│   ├── models.py          # Datové modely (GameSession, Player, Card)
│   ├── game_logic.py      # Herní logika
│   └── data/
│       └── decks/
│           └── base.json   # Konfigurace balíčku
├── static/
│   ├── index.html         # Hlavní HTML stránka
│   ├── style.css          # Styly
│   ├── app.js             # Frontend JavaScript
│   ├── cards/
│   │   └── placeholder/   # Placeholder pro obrázky karet
│   └── sounds/            # Zvukové soubory
│       ├── exploding_kitten.mp3  # Zvuk pro výbušné koťátko
│       └── game_end.mp3          # Zvuk pro konec hry
├── main.py                # FastAPI aplikace
├── requirements.txt       # Python závislosti
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## WebSocket API

### Client → Server

#### Přihlášení
```json
{ "type": "join", "name": "Jméno hráče" }
```

#### Reconnect
```json
{ "type": "reconnect", "token": "uuid" }
```

#### Ready
```json
{ "type": "set_ready", "ready": true }
```

#### Zahraní karty
```json
{ "type": "play_card", "card_id": "id", "target_player_id": "id" }
```

#### Líznutí karty
```json
{ "type": "draw_card" }
```

#### Restart hry
```json
{ "type": "restart_game" }
```

#### Odejít z lobby
```json
{ "type": "leave_lobby" }
```

#### Informace o odebrané kartě (FAVOR)
```json
{ "type": "favor_card_taken", "from_player_name": "...", "card_title": "..." }
```

### Server → Client

#### Lobby stav
```json
{
  "type": "lobby_state",
  "status": "waiting",
  "players": [
    { "player_id": "...", "name": "...", "ready": false }
  ],
  "can_start": false
}
```

#### Herní stav
```json
{
  "type": "game_state",
  "status": "playing",
  "current_player_id": "...",
  "pending_turns": { "...": 1 },
  "players": [...]
}
```

## Zvukové efekty

Hra obsahuje zvukové efekty pro zvýšení herního zážitku:

- **Výbušné koťátko**: Zvuk se přehrává všem hráčům, když někdo umře (lízne si výbušné koťátko bez Zneškodni)
- **Konec hry**: Fanfára se přehrává všem hráčům při ukončení hry

### Umístění zvukových souborů

Zvukové soubory jsou umístěny v `/static/sounds/`:
- `exploding_kitten.mp3` - zvuk exploze
- `game_end.mp3` - fanfára pro konec hry

### Nahrazení zvukových souborů

Aktuálně jsou použity placeholder zvukové soubory vygenerované pomocí `generate_sounds.py`. Pro produkci můžete:

1. Nahradit MP3 soubory vlastními zvuky (stejné názvy)
2. Nebo použít WAV formát (aplikace automaticky použije WAV, pokud MP3 není dostupný)

Zvukové soubory jsou automaticky načteny při prvním použití a cachovány pro rychlejší přehrávání.

## Poznámky

- Všechny data jsou uložena pouze v RAM (žádná persistence)
- Hra je plně responzivní a optimalizována pro desktop i mobilní zařízení
- Karty používají placeholder obrázky (snadná výměna později)
- Auto-reset lobby po 60 sekundách, pokud je prázdná
- Mobilní verze podporuje touch ovládání a je optimalizována pro iPhone a Android
- **Noví hráči se nemohou připojit během probíhající hry** - pouze reconnect pro existující hráče
- **Chat zobrazuje čas každé zprávy na jednom řádku s textem** (úspora místa) a je seřazený nejnovějšími zprávami nahoru
- **Barevné zprávy v chatu**:
  - Modrá barva: zprávy o přežití Výbušného koťátka pomocí Zneškodni
  - Hnědá barva: zprávy o smrti hráče
- **Karty zobrazují pouze název** - popis se zobrazí při najetí myši (desktop) nebo dlouhém tapu 500ms (mobil)
- **Tah se ukončuje automaticky** - líznutím karty nebo kartami Přeskoč/Zaútoč (tlačítko "Ukončit tah" není potřeba)
- **"Pohlédni do budoucnosti"** je globální - všichni hráči respektují viděné karty v pořadí
- **Karta "Zaútoč" má kumulativní efekt** - pokud několik hráčů za sebou zahraje ATTACK, každý další hráč dostane +1 tah navíc (tahy se sčítají)
- **Karta "Zneškodni" nelze normálně zahrat** - používá se pouze automaticky při líznutí výbušného koťátka
- **Karta "Tohle si vezmu" informuje cílového hráče**, jakou kartu si od něj vzali
- **Karta "Nené" může zrušit jinou NOPE kartu** - umožňuje řetězec zrušení akcí
- **Opuštění lobby a opětovné přihlášení** - po opuštění lobby se WebSocket správně zavře a token se smaže, takže hráč se může znovu přihlásit bez obnovení stránky
- **Karty v ruce jsou seřazené podle typu** - stejné typy karet jsou vedle sebe pro lepší přehlednost
- **Zobrazení počtu tahů** - u jména hráče v seznamu se zobrazuje počet zbývajících tahů v závorce (např. "Hráč (2)")

## Budoucí vylepšení (není v MVP)

- Databáze pro perzistenci
- Komba koček
- Animace
- Více místností/lobby
- Push notifikace pro mobilní zařízení

## Licence

Projekt vytvořen pro vzdělávací účely.

