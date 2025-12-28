# 📦 ZADÁNÍ PRO CURSOR  
## Online hra „Výbušná koťátka“ – single-lobby MVP

---

## 1. Cíl aplikace
Vytvořit jednoduchou online webovou hru inspirovanou **Výbušná koťátka**:

- **2–5 hráčů**
- jeden společný server, **bez místností**
- všichni se přihlásí na `/`, zadají jméno
- všichni kliknou **Start (Ready)** → hra začne automaticky
- **žádná persistence**, vše jen v RAM
- **desktop UI**, responzivita až později
- snadná výměna karet (placeholder → reálné obrázky)

---

## 2. Technický stack
- Backend: **FastAPI (Python)**
- Realtime komunikace: **WebSocket (`/ws`)**
- Frontend: **HTML + CSS + vanilla JS**
- Assets:
  - `/static/cards/placeholder/`
  - později `/static/cards/real/<deck_id>/`
- Konfigurace balíčku: **JSON (`/app/data/decks/`)**

---

## 3. Routing
- `GET /` – lobby + herní UI
- `WS /ws` – veškerá herní komunikace

---

## 4. Lobby & přihlášení

### Přihlášení hráče
1. Otevře `/`
2. Zadá jméno
3. Klikne **Přihlásit**
4. Server přidá hráče do lobby (pokud `players < 5`)

### WebSocket zprávy
**Client → Server**
```json
{ "type": "join", "name": "Elvisek" }
```

**Server → Client**
```json
{ "type": "join_ok", "player_id": "uuid", "token": "uuid" }
```

**Broadcast**
```json
{
  "type": "lobby_state",
  "status": "waiting",
  "players": [
    { "player_id":"...", "name":"Elvisek", "ready": false }
  ],
  "can_start": false
}
```

### Identita hráče
- `player_id` + `token` generuje server
- klient ukládá `token` do `sessionStorage`
- reconnect:
```json
{ "type": "reconnect", "token": "..." }
```

---

## 5. Start hry – READY mechanika
- Tlačítko **Start** = toggle `ready`
- hra se spustí automaticky, když:
  - **2–5 hráčů**
  - **všichni mají `ready == true`**

```json
{ "type": "set_ready", "ready": true }
```

---

## 6. Auto-reset lobby
- Pokud:
  - `status == waiting`
  - `players == 0`
  - uplyne **60 s**
- server resetne lobby

---

## 7. Herní pravidla (MVP)

### Karty
- EXPLODING_KITTEN
- DEFUSE
- SKIP
- ATTACK
- SHUFFLE
- SEE_FUTURE
- FAVOR
- NOPE

### Setup
- každý hráč: **1× DEFUSE**
- Exploding Kittens: **počet hráčů − 1**
- balíček zamíchat
- server určí prvního hráče

### Tah
1. hráč může hrát akční karty
2. pokud tah neukončí → **líže kartu**
3. Exploding Kitten:
   - má DEFUSE → EK se vloží **random**
   - nemá DEFUSE → hráč umírá
4. vyhrává poslední živý hráč

---

## 8. Speciální mechaniky

### ATTACK
- ukončí tah
- zvýší `pending_turns` dalšího hráče

### NOPE (MVP)
- **first click wins**
- bez timeru
- žádné Nope-na-Nope

### FAVOR
- cíl odevzdá **náhodnou kartu**

### SEE FUTURE
- server pošle **top 3 karty** jen hráči

---

## 9. Datový model (RAM)

### GameSession
```python
status
players
draw_pile
discard_pile
current_player_id
pending_turns
last_action_for_nope
```

### Player
```python
player_id
name
token
hand
alive
ready
```

### Card
```python
id
type
title
description
asset_path
```

---

## 10. Bezpečnost
- klient neposílá stav karet
- server validuje všechny akce

---

## 11. Deck systém
```json
{
  "id": "base",
  "name": "Base MVP",
  "assets_root": "/static/cards/placeholder",
  "cards": [
    { "type": "DEFUSE", "count": 6 },
    { "type": "SKIP", "count": 4 }
  ]
}
```

---

## 12. Konec hry
- lobby zůstává
- hráči zůstávají přihlášeni
- `ready = false`
- nová hra opět přes READY

---

## 13. Není v MVP
- databáze
- mobilní UI
- komba koček
- animace
