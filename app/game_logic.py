import random
import json
import os
from typing import List, Dict, Any, Optional
from .models import GameSession, Player, Card, CardType, GameStatus


CARD_DEFINITIONS = {
    CardType.EXPLODING_KITTEN: {
        "title": "Výbušné koťátko",
        "description": "Pokud si ho lízneš a nemáš Zneškodni, okamžitě prohráváš.",
        "asset_path": "/static/cards/placeholder/exploding_kitten.png"
    },
    CardType.DEFUSE: {
        "title": "Zneškodni",
        "description": "Zabrání výbuchu Výbušného koťátka. Koťátko se vrací zpět do balíčku.",
        "asset_path": "/static/cards/placeholder/defuse.png"
    },
    CardType.SKIP: {
        "title": "Přeskoč",
        "description": "Okamžitě ukončíš svůj tah bez lízání.",
        "asset_path": "/static/cards/placeholder/skip.png"
    },
    CardType.ATTACK: {
        "title": "Zaútoč",
        "description": "Přesune tahy na dalšího hráče. Musí hrát 2 tahy.",
        "asset_path": "/static/cards/placeholder/attack.png"
    },
    CardType.SHUFFLE: {
        "title": "Zamíchej",
        "description": "Zamíchá dobírací balíček.",
        "asset_path": "/static/cards/placeholder/shuffle.png"
    },
    CardType.SEE_FUTURE: {
        "title": "Pohledni do budoucnosti",
        "description": "Podívej se na několik vrchních karet balíčku.",
        "asset_path": "/static/cards/placeholder/see_future.png"
    },
    CardType.FAVOR: {
        "title": "Tohle si vezmu",
        "description": "Vezmeš si náhodnou kartu od jiného hráče.",
        "asset_path": "/static/cards/placeholder/favor.png"
    },
    CardType.NOPE: {
        "title": "Nené",
        "description": "Zruší akci jiné karty (first click wins).",
        "asset_path": "/static/cards/placeholder/nope.png"
    },
    CardType.REVERSE: {
        "title": "Změna směru",
        "description": "Změní směr tahu (dopředu ↔ dozadu).",
        "asset_path": "/static/cards/placeholder/reverse.png"
    }
}


def load_deck_config(deck_id: str = "base") -> Dict[str, Any]:
    """Načte konfiguraci balíčku z JSON souboru"""
    deck_path = os.path.join("app", "data", "decks", f"{deck_id}.json")
    if os.path.exists(deck_path):
        with open(deck_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    # Defaultní konfigurace pro MVP - DEFUSE se přidává dynamicky podle počtu hráčů
    return {
        "id": "base",
        "name": "Base MVP",
        "assets_root": "/static/cards/placeholder",
        "cards": [
            {"type": "SKIP", "count": 8},
            {"type": "ATTACK", "count": 8},
            {"type": "SHUFFLE", "count": 8},
            {"type": "SEE_FUTURE", "count": 8},
            {"type": "FAVOR", "count": 7},
            {"type": "NOPE", "count": 7},
            {"type": "REVERSE", "count": 6}
        ]
    }


def create_card(card_type: CardType, card_id: Optional[str] = None) -> Card:
    """Vytvoří kartu podle typu"""
    if card_id is None:
        card_id = str(random.randint(100000, 999999))
    
    def_data = CARD_DEFINITIONS[card_type]
    return Card(
        id=card_id,
        type=card_type,
        title=def_data["title"],
        description=def_data["description"],
        asset_path=def_data["asset_path"]
    )


def create_deck(deck_config: Dict[str, Any], num_players: int) -> List[Card]:
    """Vytvoří balíček karet podle konfigurace"""
    deck = []
    
    # Přidáme karty podle konfigurace (kromě DEFUSE, které přidáme dynamicky)
    print(f"DEBUG create_deck: Konfigurace obsahuje {len(deck_config['cards'])} typů karet")
    for card_spec in deck_config["cards"]:
        card_type = CardType(card_spec["type"])
        print(f"DEBUG create_deck: Zpracovávám kartu typu {card_type.value}, count={card_spec.get('count', 0)}")
        # Přeskočíme DEFUSE - ty přidáme dynamicky podle počtu hráčů
        if card_type == CardType.DEFUSE:
            print(f"DEBUG create_deck: Přeskakuji DEFUSE (přidá se dynamicky)")
            continue
        count = card_spec["count"]
        print(f"DEBUG create_deck: Přidávám {count} karet typu {card_type.value}")
        for _ in range(count):
            deck.append(create_card(card_type))
        print(f"DEBUG create_deck: Celkem karet typu {card_type.value} v balíčku: {sum(1 for c in deck if c.type == card_type)}")
    
    # Přidáme Exploding Kittens (počet hráčů - 1)
    for _ in range(num_players - 1):
        deck.append(create_card(CardType.EXPLODING_KITTEN))
    
    # Přidáme Zneškodni karty do balíčku (stejný počet jako Exploding Kittens)
    # Každý hráč už má 1 Zneškodni v ruce, takže do balíčku přidáme num_players - 1
    for _ in range(num_players - 1):
        deck.append(create_card(CardType.DEFUSE))
    
    # Zamícháme
    random.shuffle(deck)
    
    return deck


def initialize_game(session: GameSession) -> None:
    """Inicializuje novou hru"""
    num_players = len(session.players)
    if num_players < 2 or num_players > 5:
        return
    
    # Vytvoříme balíček
    deck_config = load_deck_config()
    session.draw_pile = create_deck(deck_config, num_players)
    session.discard_pile = []
    session.pending_turns = {}
    session.last_action_for_nope = None
    session.peeked_cards = []  # Reset peeked cards (globální)
    session.reverse_direction = False  # Reset směru tahu
    
    # Každý hráč dostane 7 karet z balíčku + 1 DEFUSE
    # DŮLEŽITÉ: Výbušná koťátka se NESMÍ dostat do ruky hráče!
    exploding_kittens_to_return = []
    
    for player in session.players:
        player.hand = []
        # Lízneme 7 karet (ale ne výbušná koťátka!)
        cards_drawn = 0
        while cards_drawn < 7 and session.draw_pile:
            card = session.draw_pile.pop(0)
            if card.type == CardType.EXPLODING_KITTEN:
                # Výbušné koťátko vrátíme do balíčku později
                exploding_kittens_to_return.append(card)
            else:
                player.hand.append(card)
                cards_drawn += 1
        
        # Přidáme 1 DEFUSE
        player.hand.append(create_card(CardType.DEFUSE))
        player.alive = True
        player.ready = False
    
    # Vrátíme výbušná koťátka zpět do balíčku
    session.draw_pile.extend(exploding_kittens_to_return)
    # Zamícháme znovu, aby byla výbušná koťátka náhodně rozmístěna
    random.shuffle(session.draw_pile)
    
    # BEZPEČNOSTNÍ KONTROLA: Zajistíme, že žádný hráč nemá výbušné koťátko v ruce
    for player in session.players:
        # Odstraníme všechny výbušná koťátka z ruky (pokud by se tam nějak dostala)
        exploding_kittens_in_hand = [c for c in player.hand if c.type == CardType.EXPLODING_KITTEN]
        for ek in exploding_kittens_in_hand:
            player.hand.remove(ek)
            session.draw_pile.append(ek)
        # Pokud jsme odstranili karty, zamícháme znovu
        if exploding_kittens_in_hand:
            random.shuffle(session.draw_pile)
    
    # Určíme prvního hráče
    session.current_player_id = session.players[0].player_id
    session.pending_turns[session.current_player_id] = 1
    session.status = GameStatus.PLAYING


def draw_card(session: GameSession, player: Player) -> Optional[Card]:
    """Hráč si lízne kartu z balíčku"""
    # Pokud máme peeked cards (z "Pohlédni do budoucnosti"), vezmeme první z nich
    # DŮLEŽITÉ: peeked_cards je globální - respektuje se pořadí pro všechny hráče
    if session.peeked_cards:
        card = session.peeked_cards.pop(0)
        # Odstraníme tuto kartu z draw_pile (měla by být na začátku, ale pro jistotu hledáme)
        found = False
        for i, c in enumerate(session.draw_pile):
            if c.id == card.id:
                session.draw_pile.pop(i)
                found = True
                break
        # Pokud karta nebyla nalezena v draw_pile, může to znamenat problém - ale pokračujeme
        if not found:
            # Karta už byla odebrána nebo není v balíčku - to by nemělo nastat, ale pro jistotu
            pass
    else:
        if not session.draw_pile:
            # Pokud je balíček prázdný, zamícháme discard pile
            if session.discard_pile:
                session.draw_pile = session.discard_pile.copy()
                session.discard_pile = []
                random.shuffle(session.draw_pile)
                # Vymažeme peeked_cards, protože se balíček změnil
                session.peeked_cards = []
            else:
                return None
        
        card = session.draw_pile.pop(0)
    
    # Pokud je to Exploding Kitten
    if card.type == CardType.EXPLODING_KITTEN:
        # Zkontrolujeme, jestli má DEFUSE
        defuse_idx = None
        for i, c in enumerate(player.hand):
            if c.type == CardType.DEFUSE:
                defuse_idx = i
                break
        
        if defuse_idx is not None:
            # Má DEFUSE - odstraníme ho a vložíme EK náhodně do balíčku
            player.hand.pop(defuse_idx)
            insert_pos = random.randint(0, len(session.draw_pile))
            session.draw_pile.insert(insert_pos, card)
            return None  # Hráč přežil
        else:
            # Nemá DEFUSE - umírá
            # Výbušné koťátko se odstraní ze hry (graveyard) - nevrátí se do balíčku
            player.alive = False
            # Vymažeme pending_turns mrtvého hráče
            if player.player_id in session.pending_turns:
                del session.pending_turns[player.player_id]
                print(f"DEBUG: Hráč {player.name} zemřel, vymazány pending_turns")
            # Karta se neukládá nikam, prostě zmizí ze hry
            return card
    
    # Normální karta - přidáme do ruky
    player.hand.append(card)
    return card


def play_card(session: GameSession, player: Player, card_id: str, target_player_id: Optional[str] = None) -> Dict[str, Any]:
    """Hráč zahraje kartu"""
    # Najdeme kartu v ruce
    card_idx = None
    for i, card in enumerate(player.hand):
        if card.id == card_id:
            card_idx = i
            break
    
    if card_idx is None:
        return {"error": "Karta není v ruce"}
    
    # Zkontrolujeme kartu před odebráním
    card = player.hand[card_idx]
    
    # DEFUSE nelze normálně zahrat - používá se pouze automaticky při líznutí výbušného koťátka
    if card.type == CardType.DEFUSE:
        return {"error": "Zneškodni nelze normálně zahrat. Používá se automaticky při líznutí výbušného koťátka."}
    
    # Debug: počet karet před odebráním
    cards_before = len(player.hand)
    card = player.hand.pop(card_idx)
    session.discard_pile.append(card)
    cards_after_remove = len(player.hand)
    print(f"DEBUG play_card: Hráč {player.name} měl {cards_before} karet, po odebrání {card.type.value} má {cards_after_remove} karet")
    
    result = {"success": True, "card_type": card.type.value}
    
    # Zpracujeme speciální efekty
    if card.type == CardType.SKIP:
        # Skip ukončí tah
        result["end_turn"] = True
        # Uložíme informace pro případné zrušení NOPE
        old_pending = session.pending_turns.get(player.player_id, 0)
        result["skip_effect"] = {
            "player_id": player.player_id,
            "old_pending": old_pending
        }
    
    elif card.type == CardType.ATTACK:
        # Attack OKAMŽITĚ ukončí tah hráče (bez ohledu na pending_turns) a zvýší pending_turns dalšího hráče
        # KLÍČOVÁ LOGIKA: Když hráč s X tahy zahraje ATTACK, další hráč dostane X + 1 tahů
        # Příklad: A má 1 tah, zahraje ATTACK → B má 1 + 1 = 2 tahy
        #          B má 2 tahy, zahraje ATTACK → C má 2 + 1 = 3 tahy
        #          C má 3 tahy, zahraje ATTACK → D má 3 + 1 = 4 tahy
        result["end_turn"] = True
        result["force_end_turn"] = True  # Označíme, že tah se musí ukončit bez ohledu na pending_turns
        
        # DŮLEŽITÉ: Před vynulováním si zapamatujeme, kolik tahů měl aktuální hráč
        # Tento počet + 1 dostane další hráč
        current_player_turns = session.pending_turns.get(player.player_id, 1)  # Defaultně 1, pokud není nastaven
        
        # OKAMŽITĚ ukončíme tah aktuálního hráče (nastavíme pending_turns na 0)
        old_pending_current = session.pending_turns.get(player.player_id, 0)
        session.pending_turns[player.player_id] = 0  # Vynulujeme tahy aktuálního hráče
        
        next_player = session.get_next_player(player.player_id)
        if next_player:
            # Uložíme původní hodnotu pending_turns pro případné zrušení NOPE
            old_pending_next = session.pending_turns.get(next_player.player_id, 0)
            
            # KLÍČOVÁ LOGIKA: Další hráč dostane "počet tahů, které měl aktuální hráč" + 1
            # Příklad: Aktuální hráč měl 2 tahy, zahrál ATTACK → další hráč dostane 2 + 1 = 3 tahy
            new_turns_for_next = current_player_turns + 1
            
            print(f"DEBUG ATTACK: Hráč {player.name} měl {current_player_turns} tahů, zahrál ATTACK")
            print(f"DEBUG ATTACK: Další hráč {next_player.name} dostane {new_turns_for_next} tahů ({current_player_turns} + 1)")
            
            # Nastavíme další hráči nový počet tahů
            session.pending_turns[next_player.player_id] = new_turns_for_next
            
            # Uložíme informace pro případné zrušení NOPE
            result["attack_effect"] = {
                "next_player_id": next_player.player_id,
                "old_pending": old_pending_next,
                "new_pending": new_turns_for_next,
                "old_pending_current": old_pending_current
            }
    
    elif card.type == CardType.SHUFFLE:
        # Zamíchá balíček - vymažeme peeked cards, protože se pořadí změnilo
        random.shuffle(session.draw_pile)
        session.peeked_cards = []  # Vymažeme globální peeked_cards
        result["message"] = "Balíček byl zamíchán"
    
    elif card.type == CardType.SEE_FUTURE:
        # Pošleme top 3 karty hráči a uložíme je pro respektování pořadí při líznutí
        # VÝBUŠNÁ KOŤÁTKA se zobrazují jako "Výbušné koťátko"
        # VŽDY bereme přesně 3 karty (nebo méně, pokud jich není dost v balíčku)
        num_cards_to_peek = min(3, len(session.draw_pile))
        top_cards = session.draw_pile[:num_cards_to_peek]
        
        print(f"DEBUG SEE_FUTURE: Balíček má {len(session.draw_pile)} karet, bereme {num_cards_to_peek} karet")
        print(f"DEBUG SEE_FUTURE: Top karty: {[c.title for c in top_cards]}")
        
        # Uložíme globální peeked_cards - respektuje se pořadí pro všechny hráče
        # Pokud už existují peeked_cards, nahradíme je novými (nový peek přepíše starý)
        session.peeked_cards = top_cards.copy()  # Uložíme kopii pro respektování pořadí
        
        # Pro zobrazení skryjeme výbušná koťátka (nahradíme placeholder)
        display_cards = []
        for i, c in enumerate(top_cards):
            print(f"DEBUG SEE_FUTURE: Zpracovávám kartu {i+1}/{len(top_cards)}: {c.title} (typ: {c.type.value})")
            if c.type == CardType.EXPLODING_KITTEN:
                # Vytvoříme placeholder kartu pro zobrazení - ukážeme že je to výbušné koťátko
                placeholder = Card(
                    id=f"hidden_{i}",
                    type=CardType.EXPLODING_KITTEN,  # Použijeme stejný typ
                    title="Výbušné koťátko",
                    description="Pokud si ho lízneš a nemáš Zneškodni, okamžitě prohráváš.",
                    asset_path="/static/cards/placeholder/exploding_kitten.png"
                )
                display_cards.append(placeholder.to_dict())
            else:
                display_cards.append(c.to_dict())
        
        print(f"DEBUG SEE_FUTURE: Vytvořeno {len(display_cards)} karet pro zobrazení: {[c.get('title', 'N/A') for c in display_cards]}")
        
        # DŮLEŽITÉ: Vždy pošleme všechny karty (3 nebo méně, pokud jich není dost)
        result["see_future_cards"] = display_cards
        print(f"DEBUG SEE_FUTURE: Posíláme {len(result['see_future_cards'])} karet na frontend")
        
        # Uložíme informace pro případné zrušení NOPE
        result["see_future_effect"] = {
            "peeked_count": len(top_cards)
        }
    
    elif card.type == CardType.FAVOR:
        # Cíl musí odevzdat náhodnou kartu (NEMŮŽE být výbušné koťátko)
        if target_player_id:
            target = session.get_player(target_player_id)
            if target and target.alive and len(target.hand) > 0:
                # Najdeme všechny karty, které NEJSOU výbušné koťátko
                available_cards = [c for c in target.hand if c.type != CardType.EXPLODING_KITTEN]
                
                if len(available_cards) == 0:
                    # Protihráč má pouze výbušná koťátka - nelze vzít kartu
                    return {"error": "Protihráč má pouze výbušná koťátka, nelze vzít kartu"}
                
                # Vybereme náhodnou kartu z dostupných (ne výbušné koťátko)
                random_card = random.choice(available_cards)
                cards_before_favor = len(player.hand)
                target.hand.remove(random_card)
                player.hand.append(random_card)
                cards_after_favor = len(player.hand)
                result["favor_card"] = random_card.to_dict()
                result["target_player_id"] = target_player_id
                # Uložíme informace pro případné zrušení NOPE
                result["favor_effect"] = {
                    "from_player_id": target_player_id,
                    "to_player_id": player.player_id,
                    "card_id": random_card.id,
                    "card_title": random_card.title
                }
                # Debug: zkontrolujeme, že karta je v ruce
                print(f"DEBUG FAVOR: Hráč {player.name} ({player.player_id}) měl {cards_before_favor} karet před přidáním, nyní má {cards_after_favor} karet v ruce")
                print(f"DEBUG FAVOR: Přidaná karta: {random_card.title} (ID: {random_card.id})")
                print(f"DEBUG FAVOR: Očekávaný počet: {cards_before_favor} + 1 = {cards_before_favor + 1}, skutečný: {cards_after_favor}")
                
                # Zkontrolujeme, jestli cílový hráč nemá žádné karty (kromě výbušných koťátek) - pokud ano, zemřel
                non_exploding_cards = [c for c in target.hand if c.type != CardType.EXPLODING_KITTEN]
                if len(non_exploding_cards) == 0:
                    # Hráč nemá žádné karty kromě výbušných koťátek - zemřel
                    target.alive = False
                    # Vymažeme pending_turns mrtvého hráče
                    if target.player_id in session.pending_turns:
                        del session.pending_turns[target.player_id]
                    print(f"DEBUG FAVOR: Hráč {target.name} ztratil poslední kartu (kromě výbušných koťátek), označen jako mrtvý")
            else:
                return {"error": "Neplatný cíl pro FAVOR"}
        else:
            return {"error": "FAVOR vyžaduje cílového hráče"}
    
    elif card.type == CardType.REVERSE:
        # Změní směr tahu a ukončí tah
        old_direction = session.reverse_direction
        session.reverse_direction = not session.reverse_direction
        result["end_turn"] = True  # REVERSE ukončí tah
        result["reverse_effect"] = {
            "new_direction": session.reverse_direction,
            "old_direction": old_direction
        }
        result["message"] = f"Směr tahu změněn na {'dozadu' if session.reverse_direction else 'dopředu'}"
        print(f"DEBUG REVERSE: Směr tahu změněn na {'dozadu' if session.reverse_direction else 'dopředu'}, ukončuji tah")
    
    elif card.type == CardType.NOPE:
        # NOPE zruší poslední akci (first click wins)
        # NELZE použít na Zneškodni (DEFUSE)
        if session.last_action_for_nope:
            last_action = session.last_action_for_nope
            cancelled_card_type = last_action.get("card_type")
            
            # Zkontrolujeme, že to není DEFUSE
            if cancelled_card_type == "DEFUSE":
                return {"error": "Nené nelze použít na kartu Zneškodni"}
            
            result["nope_action"] = last_action
            result["action_cancelled"] = True
            result["return_turn_to"] = last_action.get("player_id")  # Vrátíme tah na hráče, který kartu zahrál
            
            # Zrušíme efekt akce podle typu
            cancelled_effect = last_action.get("effect")
            
            if cancelled_card_type == "ATTACK" and cancelled_effect:
                # Vrátíme pending_turns dalšímu hráči na původní hodnotu
                next_player_id = cancelled_effect.get("next_player_id")
                old_pending = cancelled_effect.get("old_pending", 0)
                old_pending_current = cancelled_effect.get("old_pending_current", 0)
                
                if next_player_id:
                    next_player = session.get_player(next_player_id)
                    if next_player:
                        # Vrátíme pending_turns na původní hodnotu
                        if old_pending == 0:
                            # Pokud neměl pending_turns, odstraníme ho (nebo nastavíme na 1, pokud je to aktuální hráč)
                            if session.current_player_id == next_player_id:
                                session.pending_turns[next_player_id] = 1
                            else:
                                if next_player_id in session.pending_turns:
                                    del session.pending_turns[next_player_id]
                        else:
                            session.pending_turns[next_player_id] = old_pending
                        
                        # Vrátíme pending_turns aktuálnímu hráči (pokud byl ukončen ATTACK)
                        if old_pending_current > 0:
                            session.pending_turns[last_action["player_id"]] = old_pending_current
                        
                        print(f"DEBUG NOPE: Zrušil ATTACK efekt, hráč {next_player.name} má nyní {session.pending_turns.get(next_player_id, 0)} tahů")
            
            elif cancelled_card_type == "SKIP" and cancelled_effect:
                # Vrátíme pending_turns hráči (pokud byl ukončen SKIP)
                skip_player_id = cancelled_effect.get("player_id")
                old_pending = cancelled_effect.get("old_pending", 0)
                
                if skip_player_id:
                    if old_pending > 0:
                        session.pending_turns[skip_player_id] = old_pending
                    print(f"DEBUG NOPE: Zrušil SKIP efekt, hráč má nyní {session.pending_turns.get(skip_player_id, 0)} tahů")
            
            elif cancelled_card_type == "FAVOR" and cancelled_effect:
                # Vrátíme kartu zpět
                from_player_id = cancelled_effect.get("from_player_id")
                to_player_id = cancelled_effect.get("to_player_id")
                card_id = cancelled_effect.get("card_id")
                
                if from_player_id and to_player_id and card_id:
                    from_player = session.get_player(from_player_id)
                    to_player = session.get_player(to_player_id)
                    
                    if from_player and to_player:
                        # Najdeme kartu v ruce hráče, který ji dostal
                        card_to_return = None
                        for c in to_player.hand:
                            if c.id == card_id:
                                card_to_return = c
                                break
                        
                        if card_to_return:
                            to_player.hand.remove(card_to_return)
                            from_player.hand.append(card_to_return)
                            print(f"DEBUG NOPE: Zrušil FAVOR efekt, karta {card_to_return.title} vrácena hráči {from_player.name}")
            
            elif cancelled_card_type == "SEE_FUTURE" and cancelled_effect:
                # Vymažeme peeked_cards (pokud byly přidány touto akcí)
                # POZNÁMKA: Podle pravidel se aplikováním NOPE na SEE_FUTURE nic nezmění - balíček zůstane stejný
                # Ale pro konzistenci vymažeme peeked_cards, protože akce byla zrušena
                if session.peeked_cards:
                    session.peeked_cards = []
                    print(f"DEBUG NOPE: Zrušil SEE_FUTURE efekt, peeked_cards vymazány")
            
            elif cancelled_card_type == "REVERSE" and cancelled_effect:
                # Vrátíme směr tahu na původní hodnotu
                old_direction = cancelled_effect.get("old_direction", False)
                session.reverse_direction = old_direction
                print(f"DEBUG NOPE: Zrušil REVERSE efekt, směr vrácen na {'dozadu' if session.reverse_direction else 'dopředu'}")
            
            elif cancelled_card_type == "NOPE":
                # Zrušili jsme NOPE kartu - vymažeme last_action_for_nope
                # (zrušená NOPE už nemá žádný efekt, původní akce, která byla zrušena zrušenou NOPE, zůstává zrušená)
                session.last_action_for_nope = None
                print(f"DEBUG NOPE: Zrušil NOPE kartu")
            
            # Vymažeme last_action_for_nope, protože byla zrušena (pouze pokud to není NOPE - NOPE má vlastní handling výše)
            if cancelled_card_type != "NOPE":
                session.last_action_for_nope = None
        else:
            # Není žádná akce k zrušení
            result["error"] = "Není žádná akce k zrušení"
    
    # Uložíme akci pro NOPE (pouze pokud to není NOPE karta a není to DEFUSE - NOPE nemůže zrušit jiné NOPE ani DEFUSE)
    if card.type != CardType.NOPE and card.type != CardType.DEFUSE:
        session.last_action_for_nope = {
            "player_id": player.player_id,
            "card_type": card.type.value,
            "card_id": card.id,
            "effect": result.get("attack_effect") or result.get("skip_effect") or result.get("favor_effect") or result.get("see_future_effect") or result.get("reverse_effect")
        }
    
    return result


def end_turn(session: GameSession, force: bool = False) -> None:
    """Ukončí tah aktuálního hráče a přejde na dalšího
    
    Args:
        force: Pokud True, tah se ukončí bez ohledu na pending_turns (např. při ATTACK)
    """
    current = session.get_player(session.current_player_id)
    if not current:
        return
    
    # Pokud není force, snížíme pending_turns aktuálního hráče
    if not force:
        if session.current_player_id in session.pending_turns:
            session.pending_turns[session.current_player_id] -= 1
            remaining = session.pending_turns[session.current_player_id]
            print(f"DEBUG end_turn: Hráč {current.name if current else '?'} dokončil tah, zbývá {remaining} tahů")
            if remaining <= 0:
                # DŮLEŽITÉ: Nastavíme na 0 místo smazání, aby ATTACK mohl zjistit, že hráč dokončil tahy
                # Ale stále může přidat +1 (protože end_turn nastaví 1, ATTACK přidá +1 = 2)
                session.pending_turns[session.current_player_id] = 0
                print(f"DEBUG end_turn: Hráč {current.name if current else '?'} dokončil všechny tahy, pending_turns nastaven na 0")
    
    # Pokud má hráč ještě pending_turns a není force, zůstane na tahu
    # ALE: Pokud je hráč mrtvý, musíme přejít na dalšího hráče (i když má pending_turns)
    if not force and current and current.alive and session.current_player_id in session.pending_turns and session.pending_turns[session.current_player_id] > 0:
        print(f"DEBUG end_turn: Hráč {current.name} má ještě {session.pending_turns[session.current_player_id]} tahů, zůstává na tahu")
        return
    
    # Pokud je hráč mrtvý, vymažeme jeho pending_turns a přejdeme na dalšího
    if current and not current.alive:
        if session.current_player_id in session.pending_turns:
            del session.pending_turns[session.current_player_id]
            print(f"DEBUG end_turn: Hráč {current.name} je mrtvý, vymazány pending_turns, přecházíme na dalšího hráče")
    
    # Přejdeme na dalšího hráče (pouze živého)
    next_player = session.get_next_player(session.current_player_id)
    if next_player:
        # DŮLEŽITÉ: Pokud je aktuální hráč mrtvý, musíme vymazat jeho pending_turns a přejít na dalšího
        if current and not current.alive:
            if session.current_player_id in session.pending_turns:
                del session.pending_turns[session.current_player_id]
                print(f"DEBUG end_turn: Aktuální hráč {current.name} je mrtvý, vymazány pending_turns")
        old_current_id = session.current_player_id
        session.current_player_id = next_player.player_id
        
        # Nastavíme pending_turns pro dalšího hráče (pokud ještě nemá nebo má 0)
        # DŮLEŽITÉ: Pokud už má pending_turns > 0 (např. z ATTACK karty), NESMÍME ho přepsat!
        # ATTACK karta nastavuje pending_turns PŘED voláním end_turn, takže pokud už má hodnotu > 0, necháme ji
        # KLÍČOVÉ: ATTACK nastavuje pending_turns PŘED tím, než se zavolá end_turn, takže pokud už existuje a je > 0, NEPŘEPISUJEME!
        existing_turns = session.pending_turns.get(session.current_player_id, 0)
        if existing_turns == 0:
            # Hráč nemá pending_turns nebo má 0 - nastavíme na 1
            session.pending_turns[session.current_player_id] = 1
            print(f"DEBUG end_turn: Přešli jsme z {current.name if current else old_current_id} na hráče {next_player.name}, nastavili jsme 1 tah (neměl pending_turns nebo měl 0)")
        else:
            # Hráč už má pending_turns > 0 (např. z ATTACK karty) - zachováme hodnotu
            print(f"DEBUG end_turn: Přešli jsme z {current.name if current else old_current_id} na hráče {next_player.name}, má {existing_turns} tahů (zachovali jsme hodnotu z ATTACK, NEPŘEPISUJEME!)")
    
    # Zkontrolujeme, jestli je konec hry
    alive_players = session.get_alive_players()
    if len(alive_players) <= 1:
        session.status = GameStatus.FINISHED


def check_game_end(session: GameSession) -> Optional[Player]:
    """Zkontroluje, jestli hra skončila"""
    alive_players = session.get_alive_players()
    if len(alive_players) == 1:
        return alive_players[0]
    return None

