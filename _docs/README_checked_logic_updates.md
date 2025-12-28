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
- ✅ Všechny základní karty (Zneškodni, Přeskoč, Zaútoč, Zamíchej, Pohlédni do budoucnosti, Tohle si vezmu, Nené)
- ✅ Automatické spuštění hry při připravenosti všech hráčů
- ✅ Auto-reset lobby po 60 sekundách, pokud je prázdná
- ✅ Reconnect funkcionalita pomocí tokenu
- ✅ Blokování nových hráčů během probíhající hry (reconnect stále funguje)
- ✅ **Responzivní design pro mobilní zařízení (iPhone, Android)**
- ✅ Touch-friendly ovládání
- ✅ Optimalizace pro malé obrazovky
- ✅ **Chat s časem hraní** - každá zpráva má časové razítko
- ✅ **Chat seřazený nejnovějšími zprávami nahoru**
- ✅ **Karty zobrazují pouze název** - popis se zobrazí při najetí myši (desktop) nebo dlouhém tapu (mobil)
- ✅ **Tlačítko "Začít novou hru"** po dokončení hry
- ✅ **Možnost odejít z lobby**
- ✅ **Zvukové efekty** - zvuk pro výbušné koťátko (když hráč vypadne) a konec hry

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
   - Pokud hráč použil "Pohlédni do budoucnosti", lízne se první karta z jeho `peeked_cards[player_id]`
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
- Použije se automaticky, když hráč lízne výbušné koťátko
- Po použití se odebere z ruky hráče

#### Přeskoč (SKIP)
- Okamžitě ukončí tah hráče
- Hráč nemusí líznout kartu
- Tah se přepne na dalšího hráče

#### Zaútoč (ATTACK)
- Okamžitě ukončí tah hráče
- Další hráč v pořadí dostane **+1 tah navíc**:
  - implementačně: `pending_turns[next_player] += 1`
- Pokud další hráč nemá `pending_turns` nastavené, nastaví se standardně na 1 a pak se přičte +1 → výsledně 2

#### Zamíchej (SHUFFLE)
- Zamíchá `draw_pile` náhodně (globálně)
- Vymaže `peeked_cards` **všem hráčům**
- Neukončuje tah

#### Pohlédni do budoucnosti (SEE_FUTURE)
- Zobrazí top 3 karty z `draw_pile`
- Uloží se do `peeked_cards[player_id]` pro respektování pořadí
- Výbušná koťátka se zobrazí jako "Výbušné koťátko"
- Při líznutí se bere první karta z `peeked_cards[player_id]` (v původním pořadí)
- Pokud je v balíčku méně než 3 karty, zobrazí se všechny dostupné

#### Tohle si vezmu (FAVOR)
- Vyžaduje cílového hráče
- Cílový hráč odevzdá náhodnou kartu
- **NIKDY to nemůže být výbušné koťátko** (filtr pouze z běžných karet)
- Pokud cílový hráč nemá žádnou běžnou kartu, akce selže (server vrátí chybu)

#### Nené (NOPE)
- Zruší poslední akci (first click wins)
- Uloží se do `last_action_for_nope` pro zrušení efektu
- MVP implementace: jednoduché označení zrušení akce (bez Nope-na-Nope)

### Mechanika pending_turns

- Každý hráč má `pending_turns` (počet zbývajících tahů)
- Při inicializaci: první hráč má `pending_turns = 1`
- Při ukončení tahu:
  - `pending_turns` aktuálního hráče se sníží o 1
  - Pokud `pending_turns > 0`, hráč zůstane na tahu
  - Pokud `pending_turns = 0`, přepne se na dalšího živého hráče
- Nový hráč dostane `pending_turns = 1` (pokud ještě nemá)
- ATTACK karta přidá `pending_turns += 1` dalšímu hráči (tj. standardně z 1 na 2)

### Konec hry

- Pokud hráč vypadne, pokračují jen ostatní
- Hra končí, když zbývá pouze **1 živý hráč** → ten vyhrává
- Po konci hry:
  - Status se nastaví na `FINISHED`
  - Všichni hráči mají `ready = False`
  - Zobrazí se tlačítko "Začít novou hru"
  - Přehrává se zvuk konce hry

### Peeked cards (Pohlédni do budoucnosti)

- `peeked_cards` je **per-player** (`peeked_cards[player_id]`)
- Při líznutí se bere první karta z `peeked_cards[player_id]`
- Karta se odstraní z `draw_pile` podle ID
- Pokud se balíček zamíchá (SHUFFLE), `peeked_cards` se vymažou **všem hráčům**
- Pokud se balíček vyčerpá a zamíchá discard pile, `peeked_cards` se vymažou **všem hráčům**

## Instalace a spuštění

### Předpoklady
- Docker a Docker Compose

### Spuštění

```bash
docker compose up -d --build
```

Aplikace bude dostupná na: `http://localhost:8000`

### Zastavení

```bash
docker compose down
```

## Poznámky

- Všechny data jsou uložena pouze v RAM (žádná persistence)
- Hra je plně responzivní a optimalizována pro desktop i mobilní zařízení
- Karty používají placeholder obrázky (snadná výměna později)
- Auto-reset lobby po 60 sekundách, pokud je prázdná
- Noví hráči se nemohou připojit během probíhající hry - pouze reconnect pro existující hráče
- "Pohlédni do budoucnosti" je per-player; Zamíchej resetuje peek všem

