# Výbušná koťátka – Popis jednotlivých karet

Tento dokument rozšiřuje základní pravidla hry **Výbušná koťátka** o **detailní popis jednotlivých karet**, jejich efektů a chování.  
Slouží jako **referenční přehled** pro hráče i jako **podklad pro implementaci herní logiky** v online verzi.

Zdroj: oficiální pravidla (CZ) + rozšíření, viz přiložený PDF soubor. fileciteturn3file0

---

## 🧨 Výbušné a speciální koťátka

### Výbušné koťátko (Exploding Kitten) ×4
- Pokud si tuto kartu lízneš a **nemáš kartu Zneškodni**, okamžitě **vypadáváš ze hry**.
- Pokud nemáš Zneškodni:
  - hráč končí
  - karta se **do balíčku nevrací**
- Pokud máš Zneškodni:
  - postup viz karta Zneškodni

---

### Implodující koťátko (Imploding Kitten) ×1
- Při **prvním líznutí**:
  - karta se **vrátí náhodně zpět do balíčku**
  - je otočená **obrázkem nahoru**
  - **nevyžaduje Zneškodni**
- Při **druhém líznutí (aktivované)**:
  - hráč **okamžitě prohrává**
  - **nelze použít Zneškodni**
- Pokud je aktivované implodující koťátko nahoře a dojde k míchání:
  - míchání musí proběhnout **skrytě**

---

## 🛡️ Obranné karty

### Zneškodni (Defuse) ×6
- Jediná karta, která tě zachrání před výbuchem.
- Používá se automaticky při líznutí Výbušného koťátka.
- Efekt:
  - karta Zneškodni se odhodí
  - Výbušné koťátko vložíš **kamkoliv do balíčku**
  - umístění můžeš provést **skrytě**

---

## ⚔️ Útočné karty

### Útok (Attack) ×4
- Tvůj tah **okamžitě končí** bez líznutí karty.
- Další hráč v pořadí musí odehrát **2 tahy**.

---

### Cílený útok (Targeted Attack) ×3
- Tvůj tah **okamžitě končí** bez líznutí karty.
- **Vybraný hráč** musí odehrát **2 tahy**.

---

## ⏭️ Tahové a poziční karty

### Přeskočení (Skip) ×4
- Okamžitě ukončí tvůj tah.
- Nemusíš líznout kartu.

---

### Tažení ze spodu (Draw from the Bottom) ×4
- Tvůj tah končí tažením karty **ze spodní části balíčku** místo vrchní.

---

### Otáčka (Reverse) ×4
- Tvůj tah končí bez líznutí karty.
- Směr hry se **otočí**.

---

## 🔄 Manipulace s balíčkem

### Zamíchání (Shuffle) ×4
- Okamžitě zamíchá lízací balíček.
- Používá se preventivně proti výbuchu.

---

### Pohled do budoucnosti (See the Future) ×5
- Prohlédneš si **horní 3 karty** z balíčku.
- Karty musíš vrátit **ve stejném pořadí**.
- Ostatní hráči karty nevidí.

---

### Změna budoucnosti (Alter the Future) ×4
- Prohlédneš si **horní 3 karty** z balíčku.
- Vrátíš je **v libovolném pořadí**.

---

## 🤝 Interakční karty

### Službička (Favor) ×4
- Vybereš jiného hráče.
- Ten ti dá **jednu kartu z ruky dle svého výběru**.

---

### Nené (Nope) ×5
- Zruší efekt **jakékoliv právě zahrané karty**.
- Lze zahrát **kdykoliv**, i mimo vlastní tah.
- **Nelze zrušit**:
  - Výbušné koťátko
  - Zneškodni
- Lze zahrát **Nope na Nope**:
  - druhá karta se bere jako „Yup / Alejo“

---

## 🐱 Kočičí karty (kombinace)

### Kočky (Combo Cats) – 5 druhů ×4
- Samy o sobě **nemají efekt**.
- Slouží ke hraní komb:

#### 2 stejné karty
- Vybereš hráče.
- Vezmeš si od něj **náhodnou kartu**.

#### 3 stejné karty
- Vybereš hráče.
- Řekneš název karty.
- Pokud ji má, **musí ti ji dát**.

#### 5 různých karet
- Odhodíš 5 karet s různými ikonami.
- Vezmeš si **libovolnou kartu z odhazovacího balíčku**.

---

### Divoká kočka (Feral Cat) ×4
- Funguje jako **žolík**.
- Může nahradit **jakoukoli kočičí kartu** v kombu.

---

## 📌 Poznámky pro online implementaci
- Výbušná koťátka **nesmí být nikdy v ruce** hráče (kromě okamžiku líznutí).
- Implodující koťátko vyžaduje **stavovou logiku** (neaktivní → aktivní).
- NOPE vyžaduje **frontu / prioritu akcí**.
- Komba jsou vhodná pro **v2+ rozšíření**.

---

*Dokument je určen jako referenční popis karet pro hráče i vývojáře.*
