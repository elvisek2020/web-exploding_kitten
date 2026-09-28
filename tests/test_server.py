"""Integrační testy WebSocket serveru (main.py) přes testovací klienty z harness.py."""
import json
import time

import main
from app.models import CardType, GameStatus
from harness import (
    connect, create_room, give_card, login, reconnect, set_hand, settle, stack_deck, start_game,
)


# ---------------------------------------------------------------------------
# Soukromé informace se nesmí dostat k ostatním hráčům
# ---------------------------------------------------------------------------
async def test_see_future_cards_are_sent_only_to_the_player():
    lobby, (a, b, c) = await start_game("Alice", "Bob", "Cyril")
    card = give_card(lobby, a, CardType.SEE_FUTURE)
    b.clear(); c.clear()

    await a.send("play_card", card_id=card.id)

    assert a.last("see_future")["cards"], "hráč musí karty vidět"
    for other in (b, c):
        assert other.last("card_played")["card_type"] == "SEE_FUTURE"
        assert other.of_type("see_future") == []
        assert "see_future_cards" not in json.dumps(other.ws.sent)


async def test_stolen_card_is_known_only_to_thief_and_victim():
    lobby, (a, b, c) = await start_game("Alice", "Bob", "Cyril")
    set_hand(lobby, b, CardType.SHUFFLE)
    card = give_card(lobby, a, CardType.FAVOR)
    c.clear()

    await a.send("play_card", card_id=card.id, target_player_id=b.player_id)

    assert a.last("favor_card_received")["card_title"] == "Zamíchej"
    assert b.last("favor_card_taken")["card_title"] == "Zamíchej"
    public = c.last("card_played")
    assert public["target_player_name"] == "Bob"
    assert "Zamíchej" not in json.dumps(c.ws.sent)


async def test_shuffle_does_not_leak_deck_order():
    lobby, (a, b) = await start_game("Alice", "Bob")
    card = give_card(lobby, a, CardType.SHUFFLE)
    b.clear()

    await a.send("play_card", card_id=card.id)

    dump = json.dumps(b.ws.sent)
    assert not any(c.id in dump for c in lobby.session.draw_pile)


async def test_nope_broadcast_names_cancelled_card_without_private_details():
    lobby, (a, b) = await start_game("Alice", "Bob")
    shuffle = give_card(lobby, a, CardType.SHUFFLE)
    nope = give_card(lobby, b, CardType.NOPE)
    await a.send("play_card", card_id=shuffle.id)
    a.clear()

    await b.send("play_card", card_id=nope.id)

    result = a.last("card_played")["result"]
    assert result["action_cancelled"] is True
    assert result["original_card_type"] == "SHUFFLE"
    assert "nope_action" not in result


async def test_admin_flag_is_visible_only_to_admin_itself(monkeypatch):
    monkeypatch.setattr(main, "ADMIN_PASSWORD", "tajne")
    admin = await login("Admin", password="tajne")
    bob = await login("Bob")
    lobby_id = await create_room(admin)
    await bob.send("join_lobby", lobby_id=lobby_id)

    bob_view = {p["name"]: p["is_super_power"] for p in bob.last("lobby_state")["players"]}
    admin_view = {p["name"]: p["is_super_power"] for p in admin.last("lobby_state")["players"]}
    assert bob_view == {"Admin": False, "Bob": False}
    assert admin_view == {"Admin": True, "Bob": False}


# ---------------------------------------------------------------------------
# Admin heslo
# ---------------------------------------------------------------------------
async def test_admin_login_is_disabled_without_configured_password():
    client = await connect()
    await client.send("join", name="Hacker", password="TajneHeslo")
    assert client.last("join_ok") is None
    assert "není na tomto serveru zapnutý" in client.errors()[-1]


async def test_admin_login_with_configured_password(monkeypatch):
    monkeypatch.setattr(main, "ADMIN_PASSWORD", "spravne-heslo")
    admin = await login("Admin", password="spravne-heslo")
    assert admin.last("join_ok")["is_super_power"] is True


async def test_admin_password_is_locked_after_repeated_failures(monkeypatch):
    monkeypatch.setattr(main, "ADMIN_PASSWORD", "spravne-heslo")
    client = await connect(ip="192.0.2.1")
    for _ in range(3):  # limit v testech = 3 pokusy
        await client.send("join", name="Hacker", password="spatne")
    assert client.errors()[-1] == "Nesprávné heslo"

    await client.send("join", name="Hacker", password="spravne-heslo")
    assert client.last("join_ok") is None
    assert "Příliš mnoho neúspěšných pokusů" in client.errors()[-1]

    # Jiná IP blokovaná není
    other = await login("Admin", password="spravne-heslo", ip="192.0.2.2")
    assert other.last("join_ok")["is_super_power"] is True


async def test_regular_player_cannot_use_admin_commands():
    lobby, (a, b) = await start_game("Alice", "Bob")
    await a.send("remove_player", target_player_id=b.player_id)
    await a.send("view_deck")
    await a.send("end_game")
    assert "Nemáte oprávnění" in a.errors()
    assert a.of_type("deck_view") == []
    assert lobby.session.status == GameStatus.PLAYING
    assert lobby.session.get_player(b.player_id) is not None


# ---------------------------------------------------------------------------
# Origin
# ---------------------------------------------------------------------------
async def test_same_origin_is_allowed_by_default():
    client = await login("Alice", origin="https://kotatka.example.com", host="kotatka.example.com")
    assert not client.closed


async def test_foreign_origin_is_rejected_by_default():
    client = await connect(origin="https://evil.example.com", host="kotatka.example.com")
    assert client.closed
    assert client.ws.close_code == main.WS_CLOSE_ORIGIN_REJECTED


async def test_origin_matching_forwarded_host_is_allowed():
    client = await connect(
        origin="https://kotatka.example.com", host="vybusna-kotatka:8000",
        extra_headers={"x-forwarded-host": "kotatka.example.com"},
    )
    assert not client.closed


async def test_explicit_allowed_origins(monkeypatch):
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", ["https://kotatka.example.com"])
    ok = await connect(origin="https://kotatka.example.com", host="internal:8000")
    bad = await connect(origin="https://jinde.example.com", host="jinde.example.com")
    assert not ok.closed
    assert bad.closed


async def test_wildcard_origin_allows_everything(monkeypatch):
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", ["*"])
    client = await connect(origin="https://evil.example.com", host="kotatka.example.com")
    assert not client.closed


# ---------------------------------------------------------------------------
# Registrace a ochrana proti zahlcení
# ---------------------------------------------------------------------------
async def test_registrations_per_ip_are_limited(monkeypatch):
    monkeypatch.setattr(main, "MAX_REGISTRATIONS_PER_IP", 2)
    await login("P1", ip="198.51.100.7")
    await login("P2", ip="198.51.100.7")
    third = await connect(ip="198.51.100.7")
    await third.send("join", name="P3")
    assert third.last("join_ok") is None
    assert "příliš mnoho hráčů" in third.errors()[-1]


async def test_abandoned_registrations_do_not_block_new_players(monkeypatch):
    monkeypatch.setattr(main, "MAX_REGISTRATIONS_PER_IP", 2)
    monkeypatch.setattr(main, "MAX_REGISTERED_PLAYERS", 3)
    ghosts = [await login(f"Duch{i}", ip="198.51.100.9") for i in range(2)]
    for g in ghosts:
        await g.drop()  # připojil se a hned zmizel (útok nebo zavřená záložka)

    # Stejná IP - opuštěná registrace se uvolní
    again = await login("Novy", ip="198.51.100.9")
    assert again.player_id in main.player_registry

    # Plný server - uvolní se nejstarší opuštěná registrace
    await login("Dalsi1")
    await login("Dalsi2")
    assert len(main.player_registry) <= 3


async def test_name_of_abandoned_registration_can_be_reused():
    first = await login("Alice")
    await first.drop()
    second = await login("Alice")
    assert second.player_id != first.player_id


async def test_name_of_active_player_cannot_be_taken():
    await login("Alice")
    client = await connect()
    await client.send("join", name="alice")
    assert client.errors()[-1] == "Jméno je již obsazené"


async def test_invisible_characters_in_name_are_rejected():
    client = await connect()
    await client.send("join", name="Ali​ce")
    assert client.last("join_ok") is None
    assert "nepovolené znaky" in client.errors()[-1]


async def test_invalid_field_types_do_not_break_connection():
    client = await login("Alice")
    await client.send("join_lobby", lobby_id=["seznam"])
    await client.send("delete_lobby", lobby_id={"a": 1})
    await client.send("play_card", card_id=[1, 2])
    assert not client.closed
    assert "Místnost neexistuje" in client.errors()


async def test_lobby_name_is_limited_to_22_characters():
    client = await login("Alice")
    await client.send("create_lobby", name="X" * 40)
    assert main.MAX_LOBBY_NAME_LENGTH == 22
    assert len(client.last("lobby_joined")["lobby_name"]) == 22


# ---------------------------------------------------------------------------
# Tokeny a znovupřipojení
# ---------------------------------------------------------------------------
async def test_token_errors_carry_machine_readable_code():
    client = await connect()
    await client.send("reconnect", token="neexistuje")
    assert client.last("error")["code"] == main.ERR_INVALID_TOKEN


async def test_ordinary_errors_have_no_token_code():
    """Klient dřív považoval každou chybu se slovem "neplatný" za neplatný token
    a hráče odhlásil (např. u Tohle si vezmu na hráče bez karet)."""
    lobby, (a, b) = await start_game("Alice", "Bob")
    set_hand(lobby, b)
    card = give_card(lobby, a, CardType.FAVOR)
    await a.send("play_card", card_id=card.id, target_player_id=b.player_id)
    error = a.last("error")
    assert error["message"] == "Neplatný cíl pro FAVOR"
    assert "code" not in error


async def test_token_expiry_is_counted_from_last_activity():
    alice = await login("Alice")
    info = main.player_registry[alice.player_id]
    info["token_created_at"] = time.time() - main.TOKEN_EXPIRY_SECONDS - 100
    info["last_seen"] = time.time() - 10
    await alice.drop()
    back = await reconnect(alice.token)
    assert back.last("reconnect_ok")

    info["last_seen"] = time.time() - main.TOKEN_EXPIRY_SECONDS - 1
    await back.drop()
    late = await reconnect(alice.token)
    assert late.last("error")["code"] == main.ERR_TOKEN_EXPIRED


async def test_reconnect_from_another_window_replaces_old_connection():
    lobby, (a, b) = await start_game("Alice", "Bob")
    second = await reconnect(a.token)
    assert second.last("reconnect_ok")
    assert a.ws.close_code == main.WS_CLOSE_REPLACED

    # Staré spojení už hráče ovládat nesmí a nesmí mu smazat aktivitu
    card = give_card(lobby, a, CardType.SKIP)
    await a.send("play_card", card_id=card.id)
    await settle()
    assert card in lobby.session.get_player(a.player_id).hand
    assert main.connected_clients[a.player_id] is second.ws
    assert a.player_id in main.player_last_activity


async def test_resume_after_browser_restart_is_refused_while_session_is_active():
    alice = await login("Alice")
    tab = await connect()
    await tab.send("reconnect", token=alice.token, resume=True)
    error = tab.last("error")
    assert error["code"] == main.ERR_SESSION_ACTIVE
    assert error["player_name"] == "Alice"
    assert main.connected_clients[alice.player_id] is alice.ws


async def test_resume_after_browser_crash_returns_player_to_running_game():
    lobby, (a, b) = await start_game("Alice", "Bob")
    await a.drop()  # prohlížeč spadl
    assert lobby.session.get_player(a.player_id).connected is False
    assert b.last("player_disconnected")["grace_seconds"] == 15

    back = await connect()
    await back.send("reconnect", token=a.token, resume=True)
    assert back.last("reconnect_ok")
    assert back.last("lobby_joined")["lobby_id"] == lobby.lobby_id
    assert back.last("game_state")["status"] == "playing"
    assert lobby.session.get_player(a.player_id).connected is True
    assert b.last("player_reconnected")["player_name"] == "Alice"
    assert a.player_id not in main.disconnected_at


async def test_page_reload_in_waiting_room_keeps_player_in_room():
    alice = await login("Alice")
    bob = await login("Bob")
    lobby_id = await create_room(alice)
    await bob.send("join_lobby", lobby_id=lobby_id)
    await bob.drop()
    assert len(main.lobbies[lobby_id].session.players) == 2

    back = await reconnect(bob.token)
    assert back.last("lobby_joined")["lobby_id"] == lobby_id


async def test_reconnect_into_finished_game_shows_game_screen():
    lobby, (a, b) = await start_game("Alice", "Bob")
    lobby.session.status = GameStatus.FINISHED
    await a.drop()
    back = await reconnect(a.token)
    assert back.last("game_state")["status"] == "finished"


async def test_logout_closes_connection_cleanly():
    alice = await login("Alice")
    await alice.send("logout")
    assert alice.last("leave_ok")
    assert alice.ws.close_code == 1000
    assert alice.player_id not in main.player_registry


# ---------------------------------------------------------------------------
# Odpojení během hry a odpočet
# ---------------------------------------------------------------------------
async def test_disconnected_player_has_countdown_in_game_state():
    lobby, (a, b, c) = await start_game("Alice", "Bob", "Cyril")
    await b.drop()
    players = {p["name"]: p for p in a.last("game_state")["players"]}
    assert players["Bob"]["connected"] is False
    assert players["Bob"]["reconnect_seconds_left"] == 15
    assert "reconnect_seconds_left" not in players["Alice"]


async def test_player_who_does_not_return_is_removed_after_grace():
    lobby, (a, b, c) = await start_game("Alice", "Bob", "Cyril")
    await b.drop()
    await main._process_heartbeats(time.time() + 10)
    assert lobby.session.get_player(b.player_id) is not None

    await main._process_heartbeats(time.time() + 16)
    assert lobby.session.get_player(b.player_id) is None
    left = a.last("player_left")
    assert left["player_name"] == "Bob" and left["reason"] == "timeout"
    assert lobby.session.status == GameStatus.PLAYING


async def test_grace_expiry_of_player_on_turn_passes_the_turn():
    lobby, (a, b, c) = await start_game("Alice", "Bob", "Cyril")
    await a.drop()  # Alice je na tahu
    await main._process_heartbeats(time.time() + 16)
    assert lobby.session.current_player_id == b.player_id
    assert b.last("game_state")["current_player_id"] == b.player_id


async def test_winner_is_announced_when_last_opponent_times_out():
    lobby, (a, b) = await start_game("Alice", "Bob")
    await a.drop()  # hráč na tahu zavřel prohlížeč
    await main._process_heartbeats(time.time() + 16)
    end = b.last("game_end")
    assert end and end["winner_name"] == "Bob"
    assert lobby.session.status == GameStatus.FINISHED


async def test_winner_is_announced_when_player_on_turn_leaves():
    lobby, (a, b) = await start_game("Alice", "Bob")
    await a.send("leave_room")
    end = b.last("game_end")
    assert end and end["winner_id"] == b.player_id
    assert b.last("game_state")["status"] == "finished"
    assert b.last("player_left")["reason"] == "left"


async def test_failed_send_does_not_turn_player_into_ghost():
    lobby, (a, b, c) = await start_game("Alice", "Bob", "Cyril")
    b.ws.fail_sends = True
    card = give_card(lobby, a, CardType.SHUFFLE)
    await a.send("play_card", card_id=card.id)
    assert main.connected_clients.get(b.player_id) is b.ws

    await b.drop()
    assert b.player_id in main.disconnected_at, "odpojení se musí normálně obsloužit"


# ---------------------------------------------------------------------------
# Průběh hry
# ---------------------------------------------------------------------------
async def test_turn_goes_to_next_player_after_explosion():
    lobby, (a, b, c) = await start_game("Alice", "Bob", "Cyril")
    lobby.session.current_player_id = b.player_id
    lobby.session.pending_turns = {b.player_id: 1}
    set_hand(lobby, b)  # bez Zneškodni
    stack_deck(lobby, CardType.EXPLODING_KITTEN, CardType.SKIP, CardType.SKIP)

    await b.send("draw_card")

    assert a.last("player_died")["player_name"] == "Bob"
    assert lobby.session.current_player_id == c.player_id


async def test_explosion_of_second_to_last_player_ends_game():
    lobby, (a, b) = await start_game("Alice", "Bob")
    set_hand(lobby, a)
    stack_deck(lobby, CardType.EXPLODING_KITTEN, CardType.SKIP)
    await a.send("draw_card")
    assert b.last("game_end")["winner_name"] == "Bob"


async def test_game_starts_when_last_unready_player_leaves():
    alice, bob, cyril = await login("Alice"), await login("Bob"), await login("Cyril")
    lobby_id = await create_room(alice)
    for c in (bob, cyril):
        await c.send("join_lobby", lobby_id=lobby_id)
    await alice.send("set_ready", ready=True)
    await bob.send("set_ready", ready=True)
    assert main.lobbies[lobby_id].session.status == GameStatus.WAITING

    await cyril.send("leave_room")

    assert main.lobbies[lobby_id].session.status == GameStatus.PLAYING
    assert alice.last("game_state")["status"] == "playing"


async def test_set_ready_is_rejected_during_game():
    lobby, (a, b) = await start_game("Alice", "Bob")
    await a.send("set_ready", ready=False)
    assert a.errors()[-1] == "Hra už probíhá"


async def test_restart_clears_hands():
    lobby, (a, b) = await start_game("Alice", "Bob")
    lobby.session.status = GameStatus.FINISHED
    await a.send("restart_game")
    assert lobby.session.status == GameStatus.WAITING
    assert all(p["hand_size"] == 0 for p in b.last("lobby_state")["players"])


async def test_restart_is_rejected_while_game_is_running():
    lobby, (a, b) = await start_game("Alice", "Bob")
    await b.send("restart_game")
    assert lobby.session.status == GameStatus.PLAYING
    assert "až po skončení" in b.errors()[-1]


async def test_admin_end_game_without_single_survivor_has_no_winner(monkeypatch):
    monkeypatch.setattr(main, "ADMIN_PASSWORD", "tajne")
    admin = await login("Admin", password="tajne")
    lobby_id = await create_room(admin)
    others = [await login(n) for n in ("Bob", "Cyril")]
    for c in others:
        await c.send("join_lobby", lobby_id=lobby_id)
    for c in (admin, *others):
        await c.send("set_ready", ready=True)

    await admin.send("end_game")

    end = others[0].last("game_end")
    assert end["winner_id"] is None and end["ended_by_admin"] is True
    assert main.lobbies[lobby_id].session.status == GameStatus.FINISHED


async def test_admin_can_remove_player_during_game(monkeypatch):
    monkeypatch.setattr(main, "ADMIN_PASSWORD", "tajne")
    admin = await login("Admin", password="tajne")
    bob = await login("Bob")
    lobby_id = await create_room(admin)
    await bob.send("join_lobby", lobby_id=lobby_id)
    for c in (admin, bob):
        await c.send("set_ready", ready=True)

    await admin.send("remove_player", target_player_id=bob.player_id)

    assert bob.last("you_were_removed")
    assert admin.last("game_end")["winner_name"] == "Admin"
