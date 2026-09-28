"""Testy čisté herní logiky (app/game_logic.py, app/models.py)."""
from app.game_logic import (
    check_game_end, create_card, draw_card, end_turn, initialize_game, play_card,
)
from app.models import CardType, GameSession, GameStatus, Player


def make_session(*names: str, start: bool = True) -> GameSession:
    session = GameSession()
    session.players = [Player(player_id=n, name=n, token=f"t-{n}") for n in names]
    if start:
        initialize_game(session)
        session.current_player_id = names[0]
        session.pending_turns = {names[0]: 1}
    return session


def give(session: GameSession, pid: str, card_type: CardType):
    card = create_card(card_type)
    session.get_player(pid).hand.append(card)
    return card


def play(session: GameSession, pid: str, card_type: CardType, target=None) -> dict:
    """Zahraje kartu a stejně jako server případně ukončí tah."""
    card = give(session, pid, card_type)
    result = play_card(session, session.get_player(pid), card.id, target)
    if result.get("action_cancelled"):
        rp = session.get_player(result["return_turn_to"])
        if rp and rp.alive:
            session.current_player_id = rp.player_id
            if session.pending_turns.get(rp.player_id, 0) <= 0:
                session.pending_turns[rp.player_id] = 1
    elif result.get("end_turn"):
        end_turn(session, force=result.get("force_end_turn", False))
    return result


# ---------------------------------------------------------------------------
# Rozdání
# ---------------------------------------------------------------------------
def test_initialize_game_deals_seven_cards_plus_defuse_and_no_kittens():
    session = make_session("A", "B", "C", "D")
    for p in session.players:
        assert len(p.hand) == 8
        assert any(c.type == CardType.DEFUSE for c in p.hand)
        assert not any(c.type == CardType.EXPLODING_KITTEN for c in p.hand)
    kittens = [c for c in session.draw_pile if c.type == CardType.EXPLODING_KITTEN]
    assert len(kittens) == 3
    assert session.status == GameStatus.PLAYING


# ---------------------------------------------------------------------------
# Pořadí tahů
# ---------------------------------------------------------------------------
def test_turn_passes_to_next_player_after_current_player_dies():
    session = make_session("A", "B", "C", "D")
    session.current_player_id = "C"
    session.pending_turns = {"C": 1}
    session.get_player("C").alive = False
    end_turn(session)
    assert session.current_player_id == "D"


def test_turn_after_death_respects_reverse_direction():
    session = make_session("A", "B", "C", "D")
    session.reverse_direction = True
    session.current_player_id = "C"
    session.get_player("C").alive = False
    end_turn(session)
    assert session.current_player_id == "B"


def test_next_player_skips_all_dead_players_and_wraps_around():
    session = make_session("A", "B", "C", "D")
    session.get_player("D").alive = False
    session.get_player("C").alive = False
    session.current_player_id = "C"
    end_turn(session)
    assert session.current_player_id == "A"


def test_end_turn_does_not_finish_game_itself():
    """Konec hry vyhodnocuje server, aby vítěz vždy dostal game_end."""
    session = make_session("A", "B")
    session.get_player("A").alive = False
    end_turn(session, force=True)
    assert session.status == GameStatus.PLAYING
    assert check_game_end(session).player_id == "B"


def test_skip_ends_turn_without_drawing():
    session = make_session("A", "B", "C")
    pile_size = len(session.draw_pile)
    play(session, "A", CardType.SKIP)
    assert session.current_player_id == "B"
    assert len(session.draw_pile) == pile_size


# ---------------------------------------------------------------------------
# Zaútoč a Nené
# ---------------------------------------------------------------------------
def test_attack_gives_next_player_one_more_turn_cumulatively():
    session = make_session("A", "B", "C")
    play(session, "A", CardType.ATTACK)
    assert session.current_player_id == "B"
    assert session.pending_turns["B"] == 2
    play(session, "B", CardType.ATTACK)
    assert session.current_player_id == "C"
    assert session.pending_turns["C"] == 3


def test_nope_on_attack_returns_turn_and_restores_turn_counts():
    session = make_session("A", "B", "C")
    play(session, "A", CardType.ATTACK)
    result = play(session, "C", CardType.NOPE)
    assert result["action_cancelled"] is True
    assert result["original_card_type"] == "ATTACK"
    assert session.current_player_id == "A"
    assert session.pending_turns == {"A": 1}


def test_double_nope_reapplies_attack():
    session = make_session("A", "B", "C")
    play(session, "A", CardType.ATTACK)
    play(session, "C", CardType.NOPE)
    result = play(session, "B", CardType.NOPE)
    assert result["action_restored"] is True
    assert session.current_player_id == "B"
    assert session.pending_turns["B"] == 2


def test_nope_on_reverse_gives_back_the_consumed_turn():
    session = make_session("A", "B", "C")
    session.pending_turns = {"A": 2}  # A musí odehrát dva tahy (po útoku)
    play(session, "A", CardType.REVERSE)
    assert session.pending_turns["A"] == 1
    assert session.reverse_direction is True
    play(session, "B", CardType.NOPE)
    assert session.reverse_direction is False
    assert session.current_player_id == "A"
    assert session.pending_turns["A"] == 2


def test_nope_on_skip_returns_turn_to_skipping_player():
    session = make_session("A", "B", "C")
    play(session, "A", CardType.SKIP)
    assert session.current_player_id == "B"
    play(session, "C", CardType.NOPE)
    assert session.current_player_id == "A"
    assert session.pending_turns.get("A") == 1


def test_nope_without_action_is_rejected_and_card_kept():
    session = make_session("A", "B")
    card = give(session, "B", CardType.NOPE)
    result = play_card(session, session.get_player("B"), card.id)
    assert "error" in result
    assert card in session.get_player("B").hand


def test_draw_closes_nope_window():
    session = make_session("A", "B")
    play(session, "A", CardType.SHUFFLE)
    assert session.last_action_for_nope is not None
    draw_card(session, session.get_player("A"))
    assert session.last_action_for_nope is None


# ---------------------------------------------------------------------------
# Tohle si vezmu
# ---------------------------------------------------------------------------
def test_favor_on_yourself_is_rejected_and_card_kept():
    session = make_session("A", "B")
    card = give(session, "A", CardType.FAVOR)
    result = play_card(session, session.get_player("A"), card.id, "A")
    assert "error" in result
    assert card in session.get_player("A").hand


def test_favor_takes_card_from_target():
    session = make_session("A", "B")
    a, b = session.get_player("A"), session.get_player("B")
    b.hand = [create_card(CardType.SKIP)]
    stolen = b.hand[0]
    card = give(session, "A", CardType.FAVOR)
    result = play_card(session, a, card.id, "B")
    assert result["favor_card"]["id"] == stolen.id
    assert stolen in a.hand and b.hand == []


def test_favor_on_player_without_cards_is_rejected():
    session = make_session("A", "B")
    session.get_player("B").hand = []
    card = give(session, "A", CardType.FAVOR)
    result = play_card(session, session.get_player("A"), card.id, "B")
    assert "error" in result
    assert card in session.get_player("A").hand


# ---------------------------------------------------------------------------
# Lízání
# ---------------------------------------------------------------------------
def test_defuse_puts_kitten_back_into_deck():
    session = make_session("A", "B")
    a = session.get_player("A")
    kitten = create_card(CardType.EXPLODING_KITTEN)
    session.draw_pile.insert(0, kitten)
    defuses_before = sum(c.type == CardType.DEFUSE for c in a.hand)
    result = draw_card(session, a)
    assert result == {"defused": True}
    assert a.alive
    assert kitten in session.draw_pile
    assert sum(c.type == CardType.DEFUSE for c in a.hand) == defuses_before - 1


def test_kitten_without_defuse_kills_player():
    session = make_session("A", "B")
    a = session.get_player("A")
    a.hand = [c for c in a.hand if c.type != CardType.DEFUSE]
    session.draw_pile.insert(0, create_card(CardType.EXPLODING_KITTEN))
    result = draw_card(session, a)
    assert result["exploded"] is True
    assert not a.alive


def test_see_future_shows_top_three_cards_in_draw_order():
    session = make_session("A", "B")
    top = session.draw_pile[:3]
    result = play(session, "A", CardType.SEE_FUTURE)
    shown = result["see_future_cards"]
    assert len(shown) == 3
    for shown_card, real in zip(shown, top):
        assert shown_card["type"] == real.type.value
    drawn = draw_card(session, session.get_player("A"))
    if top[0].type != CardType.EXPLODING_KITTEN:
        assert drawn["card"].id == top[0].id
