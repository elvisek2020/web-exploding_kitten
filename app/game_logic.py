import random
import json
import os
import uuid
import logging
from typing import List, Dict, Any, Optional
from .models import GameSession, Player, Card, CardType, GameStatus

logger = logging.getLogger("exploding_kittens.game")

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
    deck_path = os.path.join("app", "data", "decks", f"{deck_id}.json")
    if os.path.exists(deck_path):
        with open(deck_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "id": "base", "name": "Base MVP",
        "assets_root": "/static/cards/placeholder",
        "cards": [
            {"type": "SKIP", "count": 8}, {"type": "ATTACK", "count": 8},
            {"type": "SHUFFLE", "count": 8}, {"type": "SEE_FUTURE", "count": 8},
            {"type": "FAVOR", "count": 7}, {"type": "NOPE", "count": 7},
            {"type": "REVERSE", "count": 6}
        ]
    }


def create_card(card_type: CardType, card_id: Optional[str] = None) -> Card:
    if card_id is None:
        card_id = uuid.uuid4().hex[:8]
    d = CARD_DEFINITIONS[card_type]
    return Card(id=card_id, type=card_type, title=d["title"],
                description=d["description"], asset_path=d["asset_path"])


def create_deck(deck_config: Dict[str, Any], num_players: int) -> List[Card]:
    deck = []
    for spec in deck_config["cards"]:
        ct = CardType(spec["type"])
        if ct == CardType.DEFUSE:
            continue
        for _ in range(spec["count"]):
            deck.append(create_card(ct))
    for _ in range(num_players - 1):
        deck.append(create_card(CardType.EXPLODING_KITTEN))
    for _ in range(num_players - 1):
        deck.append(create_card(CardType.DEFUSE))
    random.shuffle(deck)
    return deck


def initialize_game(session: GameSession) -> None:
    num_players = len(session.players)
    if num_players < 2 or num_players > 5:
        return

    session.draw_pile = create_deck(load_deck_config(), num_players)
    session.discard_pile = []
    session.pending_turns = {}
    session.last_action_for_nope = None
    session.peeked_cards = []
    session.reverse_direction = False

    ek_return = []
    for player in session.players:
        player.hand = []
        drawn = 0
        while drawn < 7 and session.draw_pile:
            card = session.draw_pile.pop(0)
            if card.type == CardType.EXPLODING_KITTEN:
                ek_return.append(card)
            else:
                player.hand.append(card)
                drawn += 1
        player.hand.append(create_card(CardType.DEFUSE))
        player.alive = True
        player.ready = False

    session.draw_pile.extend(ek_return)
    random.shuffle(session.draw_pile)

    for player in session.players:
        ek_in_hand = [c for c in player.hand if c.type == CardType.EXPLODING_KITTEN]
        for ek in ek_in_hand:
            player.hand.remove(ek)
            session.draw_pile.append(ek)
        if ek_in_hand:
            random.shuffle(session.draw_pile)

    session.current_player_id = session.players[0].player_id
    session.pending_turns[session.current_player_id] = 1
    session.status = GameStatus.PLAYING
    logger.info("Game initialized with %d players", num_players)


def draw_card(session: GameSession, player: Player) -> Dict[str, Any]:
    """Lízne kartu. Vrací rozlišený výsledek:
    {"card": Card}                    - normální líznutí
    {"card": Card, "exploded": True}  - výbuch (hráč umírá)
    {"defused": True}                 - koťátko zneškodněno
    {"empty": True}                   - není co líznout
    """
    # Líznutí uzavírá okno pro NOPE - poslední akce už nejde zrušit
    session.last_action_for_nope = None

    if session.peeked_cards:
        card = session.peeked_cards.pop(0)
        for i, c in enumerate(session.draw_pile):
            if c.id == card.id:
                session.draw_pile.pop(i)
                break
    else:
        if not session.draw_pile:
            if session.discard_pile:
                session.draw_pile = session.discard_pile.copy()
                session.discard_pile = []
                random.shuffle(session.draw_pile)
                session.peeked_cards = []
            else:
                return {"empty": True}
        card = session.draw_pile.pop(0)

    if card.type == CardType.EXPLODING_KITTEN:
        defuse_idx = next((i for i, c in enumerate(player.hand) if c.type == CardType.DEFUSE), None)
        if defuse_idx is not None:
            player.hand.pop(defuse_idx)
            session.draw_pile.insert(random.randint(0, len(session.draw_pile)), card)
            # Koťátko se vrátilo na neznámou pozici - dřívější peek už neplatí
            session.peeked_cards = []
            logger.info("Player %s defused Exploding Kitten", player.name)
            return {"defused": True}
        else:
            player.alive = False
            if player.player_id in session.pending_turns:
                del session.pending_turns[player.player_id]
            logger.info("Player %s died from Exploding Kitten", player.name)
            return {"card": card, "exploded": True}

    player.hand.append(card)
    return {"card": card}


# ---------------------------------------------------------------------------
# NOPE helpers: cancel & re-apply action effects
# ---------------------------------------------------------------------------
def _cancel_action_effects(session: GameSession, action: dict) -> dict:
    """Reverse the effects of a previously applied action. Returns extra result keys."""
    result = {}
    card_type = action.get("card_type")
    effect = action.get("effect")

    if card_type == "ATTACK" and effect:
        nxt_id = effect.get("next_player_id")
        old_p = effect.get("old_pending", 0)
        old_pc = effect.get("old_pending_current", 0)
        if nxt_id:
            nxt = session.get_player(nxt_id)
            if nxt:
                if old_p == 0:
                    if session.current_player_id == nxt_id:
                        session.pending_turns[nxt_id] = 1
                    elif nxt_id in session.pending_turns:
                        del session.pending_turns[nxt_id]
                else:
                    session.pending_turns[nxt_id] = old_p
                if old_pc > 0:
                    session.pending_turns[action["player_id"]] = old_pc

    elif card_type == "SKIP" and effect:
        pid = effect.get("player_id")
        old_p = effect.get("old_pending", 0)
        if pid and old_p > 0:
            session.pending_turns[pid] = old_p

    elif card_type == "FAVOR" and effect:
        from_id = effect.get("from_player_id")
        to_id = effect.get("to_player_id")
        cid = effect.get("card_id")
        if from_id and to_id and cid:
            to_p = session.get_player(to_id)
            from_p = session.get_player(from_id)
            if to_p and from_p:
                c2r = next((c for c in to_p.hand if c.id == cid), None)
                if c2r:
                    to_p.hand.remove(c2r)
                    from_p.hand.append(c2r)

    elif card_type == "SEE_FUTURE":
        session.peeked_cards = []

    elif card_type == "SHUFFLE" and effect:
        old_order = effect.get("old_order")
        if old_order is not None:
            session.draw_pile = list(old_order)
        session.peeked_cards = []

    elif card_type == "REVERSE" and effect:
        session.reverse_direction = effect.get("old_direction", False)

    return result


def _reapply_action_effects(session: GameSession, action: dict) -> dict:
    """Re-apply effects of a previously cancelled action. Returns extra result keys."""
    result = {}
    card_type = action.get("card_type")
    effect = action.get("effect")

    if card_type == "ATTACK" and effect:
        nxt_id = effect.get("next_player_id")
        new_p = effect.get("new_pending", 2)
        if nxt_id:
            session.pending_turns[nxt_id] = new_p
            session.pending_turns[action["player_id"]] = 0
        result["end_turn"] = True
        result["force_end_turn"] = True

    elif card_type == "SKIP":
        result["end_turn"] = True

    elif card_type == "FAVOR" and effect:
        from_id = effect.get("from_player_id")
        to_id = effect.get("to_player_id")
        cid = effect.get("card_id")
        if from_id and to_id and cid:
            from_p = session.get_player(from_id)
            to_p = session.get_player(to_id)
            if from_p and to_p:
                c2t = next((c for c in from_p.hand if c.id == cid), None)
                if c2t:
                    from_p.hand.remove(c2t)
                    to_p.hand.append(c2t)

    elif card_type == "SEE_FUTURE" and effect:
        n = min(effect.get("peeked_count", 3), len(session.draw_pile))
        session.peeked_cards = session.draw_pile[:n].copy()

    elif card_type == "SHUFFLE" and effect:
        new_order = effect.get("new_order")
        if new_order is not None:
            session.draw_pile = list(new_order)
        session.peeked_cards = []

    elif card_type == "REVERSE" and effect:
        session.reverse_direction = effect.get("new_direction", True)
        result["end_turn"] = True

    return result


# ---------------------------------------------------------------------------
# play_card
# ---------------------------------------------------------------------------
def play_card(session: GameSession, player: Player, card_id: str,
              target_player_id: Optional[str] = None) -> Dict[str, Any]:
    card_idx = next((i for i, c in enumerate(player.hand) if c.id == card_id), None)
    if card_idx is None:
        return {"error": "Karta není v ruce"}

    card = player.hand[card_idx]

    if card.type == CardType.DEFUSE:
        return {"error": "Zneškodni nelze normálně zahrat. Používá se automaticky při líznutí výbušného koťátka."}

    # Validace specifické pro typ karty PŘED odebráním z ruky,
    # aby se karta při chybě "nespálila".
    if card.type == CardType.FAVOR:
        if not target_player_id:
            return {"error": "FAVOR vyžaduje cílového hráče"}
        favor_target = session.get_player(target_player_id)
        if not favor_target or not favor_target.alive or len(favor_target.hand) == 0:
            return {"error": "Neplatný cíl pro FAVOR"}
        if all(c.type == CardType.EXPLODING_KITTEN for c in favor_target.hand):
            return {"error": "Protihráč má pouze výbušná koťátka, nelze vzít kartu"}

    if card.type == CardType.NOPE:
        if not session.last_action_for_nope:
            return {"error": "Není žádná akce k zrušení"}
        if session.last_action_for_nope.get("card_type") == "DEFUSE":
            return {"error": "Nené nelze použít na kartu Zneškodni"}

    card = player.hand.pop(card_idx)
    session.discard_pile.append(card)
    logger.debug("Player %s played %s", player.name, card.type.value)

    result: Dict[str, Any] = {"success": True, "card_type": card.type.value}

    # ----- SKIP -----
    if card.type == CardType.SKIP:
        result["end_turn"] = True
        result["skip_effect"] = {
            "player_id": player.player_id,
            "old_pending": session.pending_turns.get(player.player_id, 0),
        }

    # ----- ATTACK -----
    elif card.type == CardType.ATTACK:
        result["end_turn"] = True
        result["force_end_turn"] = True
        cur_turns = session.pending_turns.get(player.player_id, 1)
        old_pc = session.pending_turns.get(player.player_id, 0)
        session.pending_turns[player.player_id] = 0
        nxt = session.get_next_player(player.player_id)
        if nxt:
            old_pn = session.pending_turns.get(nxt.player_id, 0)
            new_turns = cur_turns + 1
            session.pending_turns[nxt.player_id] = new_turns
            result["attack_effect"] = {
                "next_player_id": nxt.player_id,
                "old_pending": old_pn,
                "new_pending": new_turns,
                "old_pending_current": old_pc,
            }

    # ----- SHUFFLE -----
    elif card.type == CardType.SHUFFLE:
        old_order = session.draw_pile.copy()
        random.shuffle(session.draw_pile)
        session.peeked_cards = []
        result["message"] = "Balíček byl zamíchán"
        # Uložené pořadí umožňuje NOPE zamíchání skutečně vrátit
        result["shuffle_effect"] = {
            "old_order": old_order,
            "new_order": session.draw_pile.copy(),
        }

    # ----- SEE FUTURE -----
    elif card.type == CardType.SEE_FUTURE:
        n = min(3, len(session.draw_pile))
        top = session.draw_pile[:n]
        session.peeked_cards = top.copy()
        display = []
        for i, c in enumerate(top):
            if c.type == CardType.EXPLODING_KITTEN:
                display.append(Card(id=f"hidden_{i}", type=CardType.EXPLODING_KITTEN,
                                    title="Výbušné koťátko",
                                    description="Pokud si ho lízneš a nemáš Zneškodni, okamžitě prohráváš.",
                                    asset_path="/static/cards/placeholder/exploding_kitten.png").to_dict())
            else:
                display.append(c.to_dict())
        result["see_future_cards"] = display
        result["see_future_effect"] = {"peeked_count": len(top)}

    # ----- FAVOR (cíl už zvalidován výše) -----
    elif card.type == CardType.FAVOR:
        target = session.get_player(target_player_id)
        available = [c for c in target.hand if c.type != CardType.EXPLODING_KITTEN]
        rc = random.choice(available)
        target.hand.remove(rc)
        player.hand.append(rc)
        result["favor_card"] = rc.to_dict()
        result["target_player_id"] = target_player_id
        result["favor_effect"] = {
            "from_player_id": target_player_id,
            "to_player_id": player.player_id,
            "card_id": rc.id, "card_title": rc.title,
        }

    # ----- REVERSE -----
    elif card.type == CardType.REVERSE:
        old_dir = session.reverse_direction
        session.reverse_direction = not session.reverse_direction
        result["end_turn"] = True
        result["reverse_effect"] = {
            "new_direction": session.reverse_direction,
            "old_direction": old_dir,
        }
        result["message"] = f"Směr tahu změněn na {'dozadu' if session.reverse_direction else 'dopředu'}"

    # ----- NOPE (with double-NOPE chain support; existence akce zvalidována výše) -----
    elif card.type == CardType.NOPE:
        last = session.last_action_for_nope

        if last.get("card_type") == "NOPE":
            # Double-NOPE chain: toggle state of original action
            original = last["original_action"]
            currently_cancelled = last.get("is_cancelled", True)

            if currently_cancelled:
                extra = _reapply_action_effects(session, original)
                result.update(extra)
                result["action_restored"] = True
                result["original_card_type"] = original.get("card_type")
                logger.debug("Double-NOPE: restored %s", original.get("card_type"))
                new_cancelled = False
            else:
                _cancel_action_effects(session, original)
                result["action_cancelled"] = True
                result["return_turn_to"] = original.get("player_id")
                result["original_card_type"] = original.get("card_type")
                logger.debug("Triple-NOPE: cancelled %s again", original.get("card_type"))
                new_cancelled = True

            session.last_action_for_nope = {
                "player_id": player.player_id,
                "card_type": "NOPE",
                "original_action": original,
                "is_cancelled": new_cancelled,
            }
        else:
            # First NOPE on a non-NOPE action
            _cancel_action_effects(session, last)
            result["nope_action"] = last
            result["action_cancelled"] = True
            result["return_turn_to"] = last.get("player_id")

            session.last_action_for_nope = {
                "player_id": player.player_id,
                "card_type": "NOPE",
                "original_action": last,
                "is_cancelled": True,
            }

        return result

    # Store action for potential NOPE (not for NOPE/DEFUSE)
    if card.type not in (CardType.NOPE, CardType.DEFUSE):
        session.last_action_for_nope = {
            "player_id": player.player_id,
            "card_type": card.type.value,
            "card_id": card.id,
            "effect": (result.get("attack_effect") or result.get("skip_effect")
                       or result.get("favor_effect") or result.get("see_future_effect")
                       or result.get("reverse_effect") or result.get("shuffle_effect")),
        }

    return result


def end_turn(session: GameSession, force: bool = False) -> None:
    current = session.get_player(session.current_player_id)
    if not current:
        return

    if not force:
        if session.current_player_id in session.pending_turns:
            session.pending_turns[session.current_player_id] -= 1
            if session.pending_turns[session.current_player_id] <= 0:
                session.pending_turns[session.current_player_id] = 0

    if (not force and current and current.alive
            and session.current_player_id in session.pending_turns
            and session.pending_turns[session.current_player_id] > 0):
        return

    if current and not current.alive:
        session.pending_turns.pop(session.current_player_id, None)

    nxt = session.get_next_player(session.current_player_id)
    if nxt:
        if current and not current.alive:
            session.pending_turns.pop(session.current_player_id, None)
        session.current_player_id = nxt.player_id
        if session.pending_turns.get(session.current_player_id, 0) == 0:
            session.pending_turns[session.current_player_id] = 1

    if len(session.get_alive_players()) <= 1:
        session.status = GameStatus.FINISHED


def check_game_end(session: GameSession) -> Optional[Player]:
    alive = session.get_alive_players()
    return alive[0] if len(alive) == 1 else None
