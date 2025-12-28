# 🃏 Reálné karty – Výbušná koťátka (CZ)

Tento dokument obsahuje seznam **reálných herních karet** pro budoucí rozšíření hry.
Slouží jako podklad pro:
- tvorbu `deck.json`
- assety (obrázky karet)
- implementaci herní logiky (v2+)

---

## 🔥 Výbušné karty
- **Výbušné koťátko**  
  Pokud si ho lízneš a nemáš Zneškodni, okamžitě prohráváš.

- **Štěkající koťátko**  
  Speciální typ koťátka – chová se podobně jako Výbušné, ale s rozšířenými pravidly (v2).

---

## 🛡️ Obranné a reakční karty
- **Zneškodni**  
  Zabrání výbuchu Výbušného koťátka. Koťátko se vrací zpět do balíčku.

- **Nené**  
  Zruší akci jiné karty.

---

## 🔮 Manipulace s budoucností
- **Sdílej budoucnost**  
  Podívej se na vrchní karty balíčku spolu s jiným hráčem.

- **Pohledni do budoucnosti**  
  Podívej se na několik vrchních karet balíčku.

- **Změň budoucnost**  
  Přerovnej nebo změň pořadí nadcházejících karet.

---

## ⚔️ Útočné karty
- **Osobní útok**  
  Cílený útok na konkrétního hráče.

- **Zaútoč**  
  Přesune tahy na dalšího hráče.

- **Cílený útok**  
  Vybereš konkrétního hráče, který musí odehrát více tahů.

---

## 🔄 Ovlivnění balíčku
- **Změň směr**  
  Změní směr hry.

- **Zamíchej**  
  Zamíchá dobírací balíček.

- **Lízni si zespodu**  
  Místo vršku balíčku lízneš spodní kartu.

---

## 🃏 Karty krádeže a interakce
- **Tohle si vezmu**  
  Vezmeš si náhodnou kartu od jiného hráče.

- **Označ**  
  Označí kartu nebo hráče (rozšířená logika).

---

## ⏭️ Tahové karty
- **Přeskoč**  
  Okamžitě ukončíš svůj tah bez lízání.

- **Super skok**  
  Silnější verze Přeskoč (např. vícenásobný efekt).

---

## 🐱 Kočičí karty (kombinace)
- **Takočka**
- **Duha zvracečička**
- **Vousatá kočka**
- **Zdivočelá kočka**
- **Nekromour**

> Kočičí karty slouží primárně ke kombům (páry, trojice apod.).  
> Logika není součástí MVP, ale počítá se s ní v rozšířeních.

---

## 📌 Poznámky
- Názvy jsou **v češtině**, doporučeno mapovat na interní `card_type` (EN, UPPER_SNAKE_CASE).
- Každá karta bude mít:
  - název
  - popis
  - typ (attack / defense / future / combo / special)
  - asset (PNG / SVG)

---

*Dokument slouží jako zdroj pro další iterace projektu (v2+).*  
