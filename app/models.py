from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import uuid
import random
import time


class GameStatus(str, Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    FINISHED = "finished"


class CardType(str, Enum):
    EXPLODING_KITTEN = "EXPLODING_KITTEN"
    DEFUSE = "DEFUSE"
    SKIP = "SKIP"
    ATTACK = "ATTACK"
    SHUFFLE = "SHUFFLE"
    SEE_FUTURE = "SEE_FUTURE"
    FAVOR = "FAVOR"
    NOPE = "NOPE"
    REVERSE = "REVERSE"


@dataclass
class Card:
    id: str
    type: CardType
    title: str
    description: str
    asset_path: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "description": self.description,
            "asset_path": self.asset_path
        }


@dataclass
class Player:
    player_id: str
    name: str
    token: str
    hand: List[Card] = field(default_factory=list)
    alive: bool = True
    ready: bool = False
    is_super_power: bool = False

    def to_dict(self, hide_hand: bool = False) -> Dict[str, Any]:
        result = {
            "player_id": self.player_id,
            "name": self.name,
            "alive": self.alive,
            "ready": self.ready,
            "hand_size": len(self.hand),
            "is_super_power": self.is_super_power
        }
        if not hide_hand:
            # DŮLEŽITÉ: Výbušné koťátko se NESMÍ zobrazit v ruce - filtrujeme ho
            result["hand"] = [card.to_dict() for card in self.hand if card.type != CardType.EXPLODING_KITTEN]
        return result


@dataclass
class GameSession:
    status: GameStatus = GameStatus.WAITING
    players: List[Player] = field(default_factory=list)
    draw_pile: List[Card] = field(default_factory=list)
    discard_pile: List[Card] = field(default_factory=list)
    current_player_id: Optional[str] = None
    pending_turns: Dict[str, int] = field(default_factory=dict)
    last_action_for_nope: Optional[Dict[str, Any]] = None
    last_reset_time: float = field(default_factory=lambda: time.time())
    peeked_cards: List[Card] = field(default_factory=list)  # Globální karty viděné přes "Pohlédni do budoucnosti" - respektuje se pořadí pro všechny
    reverse_direction: bool = False  # Směr tahu: False = dopředu, True = dozadu

    def get_player(self, player_id: str) -> Optional[Player]:
        for player in self.players:
            if player.player_id == player_id:
                return player
        return None

    def get_player_by_token(self, token: str) -> Optional[Player]:
        for player in self.players:
            if player.token == token:
                return player
        return None

    def get_alive_players(self) -> List[Player]:
        return [p for p in self.players if p.alive]

    def get_next_player(self, current_id: str) -> Optional[Player]:
        alive = self.get_alive_players()
        if not alive:
            return None
        try:
            current_idx = next(i for i, p in enumerate(alive) if p.player_id == current_id)
            if self.reverse_direction:
                # Směr dozadu
                next_idx = (current_idx - 1) % len(alive)
            else:
                # Směr dopředu
                next_idx = (current_idx + 1) % len(alive)
            return alive[next_idx]
        except StopIteration:
            return alive[0] if alive else None

