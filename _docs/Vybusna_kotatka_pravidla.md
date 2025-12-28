# Výbušná koťátka – Pravidla hry (souhrn)

Tento dokument shrnuje kompletní pravidla karetní hry **Výbušná koťátka (Exploding Kittens – Original Edition)** a slouží jako podklad pro digitální implementaci.

Zdroj: oficiální pravidla hry (CZ překlad).

---

## Základní informace
- **Počet hráčů:** 2–5 (až 9 při kombinaci balíčků)
- **Cíl hry:** Přežít – vyhrává poslední nevybuchlý hráč
- **Typ hry:** Eliminace hráčů
- **Balíček:** 56 karet

---

## Princip hry
Hráči se střídají ve směru hodinových ručiček. Ve svém tahu mohou zahrát libovolný počet karet z ruky, poté **musí líznout jednu kartu**, čímž svůj tah zakončí.

Pokud si hráč lízne **Výbušné koťátko** a nemá kartu **Zneškodni**, okamžitě prohrává a je vyřazen ze hry.

---

## Příprava hry

1. Vyjměte z balíčku všechny karty **Výbušné koťátko** a **Zneškodni**.
2. Každému hráči rozdejte **4 karty**.
3. Každému hráči přidejte **1× Zneškodni** (každý má 5 karet).
4. Do balíčku vložte:
   - **o 1 Výbušné koťátko méně, než je hráčů**
   - zbylé karty **Zneškodni**
5. Balíček zamíchejte a položte doprostřed – vzniká **lízací balíček**.
6. Vyberte prvního hráče.

---

## Průběh tahu

Hráč může:
- zahrát **libovolný počet karet**
- zahrát **kombinace karet**
- nebo **nezahrát nic**

Tah **vždy končí líznutím jedné karty**, pokud není výslovně řečeno jinak (např. Skip, Attack).

---

## Karty a jejich účinky

### Výbušné koťátko
- Pokud si ho lízneš a **nemáš Zneškodni**, okamžitě vypadáváš ze hry.
- Pokud máš **Zneškodni**, výbuch se zruší.

### Zneškodni (Defuse)
- Jediná karta, která tě zachrání před výbuchem.
- Po použití ji odhodíš.
- Výbušné koťátko vložíš **kamkoliv zpět do balíčku** (bez míchání).

### Přeskoč (Skip)
- Okamžitě ukončí tvůj tah **bez líznutí karty**.

### Útok (Attack)
- Ukončí tvůj tah.
- Další hráč musí odehrát **2 tahy**.
- Pokud zahraje také Útok, efekt se přenáší dál.

### Zamíchej (Shuffle)
- Náhodně zamíchá lízací balíček.
- Užívá se, pokud tušíš blížící se výbuch.

### Pohlédni do budoucnosti (See the Future)
- Podíváš se na **3 horní karty balíčku**.
- Karty vrátíš ve stejném pořadí.
- Neukazuješ je ostatním hráčům.

### Tohle si vezmu (Favor)
- Vybereš jiného hráče.
- Ten ti musí dát **jednu kartu dle svého výběru**.

### Nené (Nope)
- Zruší účinek jakékoliv jiné karty (kromě Výbušného koťátka a Zneškodni).
- Můžeš ji zahrát **kdykoliv**, i mimo svůj tah.
- Lze hrát i **Nope na Nope**.

---

## Kombinace karet

### Dvě stejné karty
- Vybereš si hráče a vezmeš si od něj **náhodnou kartu**.

### Tři stejné karty
- Vybereš si hráče a **pojmenuješ konkrétní kartu**.
- Pokud ji má, musí ti ji dát.

### Pět různých karet
- Odhodíš 5 karet s různými ikonami.
- Vezmeš si **libovolnou kartu z odhazovacího balíčku**.

---

## Další pravidla
- Neexistuje limit karet v ruce.
- Pokud nemáš žádné karty, normálně pokračuješ ve hře.
- Balíček se během hry **nikdy nevyčerpá**.
- Hra končí, jakmile zůstane **1 hráč**.

---

*Dokument je určen jako přehled pravidel a technický podklad pro digitální implementaci hry.*
