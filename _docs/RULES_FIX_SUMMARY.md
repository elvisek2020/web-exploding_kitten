# Oprava herní logiky podle pravidel

**Datum:** 2024-12-27  
**Backup:** `_backup/` (app/, static/)

## Přehled změn

Tento dokument popisuje opravy herní logiky, které byly provedeny podle oficiálních pravidel hry "Výbušná koťátka".

---

## 1. ATTACK (Zaútoč)

### Problém
Původní implementace přidávala dalšímu hráči `current_player_turns + 1` tahů, což neodpovídalo pravidlům.

### Oprava
Podle pravidel: "Další hráč musí odehrát **2 tahy**" - další hráč nyní dostane přesně **2 tahy**, bez ohledu na to, kolik tahů měl aktuální hráč.

**Soubor:** `app/game_logic.py` (řádky ~290-320)

---

## 2. SEE FUTURE (Pohlédni do budoucnosti)

### Problém
Původní implementace používala globální `peeked_cards` list, což znamenalo, že pouze jeden hráč mohl mít aktivní peek najednou.

### Oprava
- `peeked_cards` je nyní per-player dictionary: `peeked_cards[player_id] = [Card, ...]`
- Více hráčů může mít současně aktivní peek
- Každý hráč lízne karty ze svého vlastního peeku

**Soubory:**
- `app/models.py` - změna typu `peeked_cards` z `List[Card]` na `Dict[str, List[Card]]`
- `app/game_logic.py` - úprava logiky v `draw_card()` a `play_card()` pro SEE_FUTURE

---

## 3. SHUFFLE (Zamíchej)

### Problém
Původní implementace vymazávala globální `peeked_cards` list, ale nyní je to per-player dictionary.

### Oprava
Po zamíchání balíčku se vymažou **všechny peeky všech hráčů**: `session.peeked_cards = {}`

**Soubor:** `app/game_logic.py` (řádek ~328)

---

## 4. EXPLODING KITTEN (Výbušné koťátko)

### Problém
Výbušné koťátko by se teoreticky mohlo zobrazit v ruce (i když se tam nikdy nedostane díky logice).

### Oprava
- **Backend:** V `Player.to_dict()` se filtrují EK karty z ruky před odesláním na frontend
- **Frontend:** V `updateMyHand()` se filtrují EK karty před zobrazením
- **FAVOR:** EK karty se nemohou vzít přes FAVOR (už bylo implementováno)
- **Draw:** EK se nikdy nedostane do ruky - buď se použije DEFUSE a vloží zpět do balíčku, nebo hráč umře a EK se neukládá nikam

**Soubory:**
- `app/models.py` - filtrování EK v `to_dict()`
- `static/app.js` - filtrování EK v `updateMyHand()`

---

## 5. Player Death & Win Condition

### Kontrola
Win condition je správně implementována:
- `check_game_end()` kontroluje, zda zůstal pouze 1 živý hráč
- Kontrola se provádí po každé smrti hráče (v `main.py` po `player_died` eventu)
- Hra končí, když `len(alive_players) == 1`

**Soubory:**
- `app/game_logic.py` - funkce `check_game_end()`
- `main.py` - volání `check_game_end()` po smrti hráče

---

## 6. NOPE logika pro SEE_FUTURE

### Oprava
Při zrušení SEE_FUTURE přes NOPE se nyní vymažou peeked_cards pouze pro konkrétního hráče (ne všechny).

**Soubor:** `app/game_logic.py` (řádky ~509-519)

---

## Změněné soubory

1. **app/models.py**
   - Změna typu `peeked_cards` z `List[Card]` na `Dict[str, List[Card]]`
   - Filtrování EK v `Player.to_dict()`

2. **app/game_logic.py**
   - Oprava ATTACK logiky (2 tahy místo current + 1)
   - Přechod na per-player peeked_cards
   - Oprava SHUFFLE (vymazání všech peeků)
   - Oprava NOPE logiky pro SEE_FUTURE

3. **static/app.js**
   - Filtrování EK v `updateMyHand()`

---

## Poznámky

- Všechny změny jsou zpětně kompatibilní s existující logikou
- Backup je uložen v `_backup/` adresáři
- Win condition funguje správně a kontroluje se po každé smrti hráče
- EK se nikdy nezobrazí v ruce (ani v UI, ani v backendu)

---

## Testování

Doporučené testovací scénáře:
1. **ATTACK:** Hráč zahraje ATTACK → další hráč má přesně 2 tahy
2. **SEE FUTURE:** Více hráčů zahraje SEE FUTURE → každý má svůj vlastní peek
3. **SHUFFLE:** Po zamíchání se zruší všechny peeky
4. **EK:** EK se nikdy nezobrazí v ruce
5. **Win condition:** Hra končí, když zůstane 1 živý hráč

