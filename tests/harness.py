"""Testovací klienti pro WebSocket endpoint.

Místo skutečného síťového spojení se do `main.websocket_endpoint` podstrčí
FakeWebSocket s frontou příchozích zpráv a seznamem odeslaných. Endpoint tak
běží celý (validace, rate limity, broadcasty), ale deterministicky a bez
rizika, že test zamrzne na čekání na zprávu.
"""
import asyncio
import itertools
import json
from types import SimpleNamespace
from typing import List, Optional

from fastapi import WebSocketDisconnect

import main
from app.game_logic import create_card
from app.models import CardType, GameStatus, Lobby

_DISCONNECT = object()
_ip_counter = itertools.count(1)


def reset() -> None:
    global _ip_counter
    _ip_counter = itertools.count(1)


def next_ip() -> str:
    n = next(_ip_counter)
    return f"10.0.{n // 250}.{n % 250 + 1}"


async def settle(rounds: int = 50) -> None:
    """Nechá doběhnout všechno, co endpointy právě zpracovávají."""
    for _ in range(rounds):
        await asyncio.sleep(0)


class FakeWebSocket:
    def __init__(self, ip: str, headers: dict):
        self.client = SimpleNamespace(host=ip)
        self.headers = headers
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.sent: List[dict] = []
        self.close_code: Optional[int] = None
        self.fail_sends = False

    async def accept(self):
        pass

    async def receive_text(self) -> str:
        item = await self.incoming.get()
        if item is _DISCONNECT:
            raise WebSocketDisconnect(code=self.close_code or 1000)
        return item

    async def send_json(self, data) -> None:
        await self.send_text(json.dumps(data))

    async def send_text(self, text: str) -> None:
        if self.close_code is not None or self.fail_sends:
            raise RuntimeError("socket is closed")
        self.sent.append(json.loads(text))

    async def close(self, code: int = 1000) -> None:
        if self.close_code is None:
            self.close_code = code
            self.incoming.put_nowait(_DISCONNECT)


class Client:
    def __init__(self, ip: Optional[str] = None, origin: Optional[str] = "http://testserver",
                 host: str = "testserver", extra_headers: Optional[dict] = None):
        headers = {"host": host}
        if origin is not None:
            headers["origin"] = origin
        headers.update(extra_headers or {})
        self.ws = FakeWebSocket(ip or next_ip(), headers)
        self.task = asyncio.create_task(main.websocket_endpoint(self.ws))
        self.player_id: Optional[str] = None
        self.token: Optional[str] = None
        self.name: Optional[str] = None

    @property
    def ip(self) -> str:
        return self.ws.client.host

    async def send(self, msg_type: str, **data) -> None:
        await self.send_raw(json.dumps({"type": msg_type, **data}))

    async def send_raw(self, raw: str) -> None:
        await self.ws.incoming.put(raw)
        await settle()

    async def drop(self) -> None:
        """Klient zmizí (zavřený prohlížeč, spadlá síť)."""
        if self.ws.close_code is None:
            self.ws.close_code = 1001
            await self.ws.incoming.put(_DISCONNECT)
        await settle()

    @property
    def closed(self) -> bool:
        return self.task.done()

    def of_type(self, msg_type: str) -> List[dict]:
        return [m for m in self.ws.sent if m.get("type") == msg_type]

    def last(self, msg_type: str) -> Optional[dict]:
        msgs = self.of_type(msg_type)
        return msgs[-1] if msgs else None

    def errors(self) -> List[str]:
        return [m["message"] for m in self.of_type("error")]

    def clear(self) -> None:
        self.ws.sent.clear()


async def connect(**kwargs) -> Client:
    client = Client(**kwargs)
    await settle()
    return client


async def login(name: str, password: Optional[str] = None, **kwargs) -> Client:
    client = await connect(**kwargs)
    payload = {"name": name}
    if password is not None:
        payload["password"] = password
    await client.send("join", **payload)
    ok = client.last("join_ok")
    assert ok, f"přihlášení {name} selhalo: {client.errors()}"
    client.player_id = ok["player_id"]
    client.token = ok["token"]
    client.name = name
    return client


async def reconnect(token: str, **kwargs) -> Client:
    client = await connect(**kwargs)
    await client.send("reconnect", token=token)
    ok = client.last("reconnect_ok")
    if ok:
        client.player_id = ok["player_id"]
        client.token = token
    return client


async def create_room(host: Client, name: str = "Test") -> str:
    await host.send("create_lobby", name=name)
    joined = host.last("lobby_joined")
    assert joined, host.errors()
    return joined["lobby_id"]


async def start_game(*names: str) -> tuple:
    """Založí místnost, připojí hráče a spustí hru. Vrací (lobby, [klienti])."""
    clients = [await login(n) for n in names]
    lobby_id = await create_room(clients[0])
    for c in clients[1:]:
        await c.send("join_lobby", lobby_id=lobby_id)
    for c in clients:
        await c.send("set_ready", ready=True)
    lobby: Lobby = main.lobbies[lobby_id]
    assert lobby.session.status == GameStatus.PLAYING
    lobby.session.current_player_id = clients[0].player_id
    lobby.session.pending_turns = {clients[0].player_id: 1}
    return lobby, clients


def give_card(lobby: Lobby, client: Client, card_type: CardType):
    """Přidá hráči do ruky kartu daného typu a vrátí ji."""
    card = create_card(card_type)
    lobby.session.get_player(client.player_id).hand.append(card)
    return card


def set_hand(lobby: Lobby, client: Client, *card_types: CardType) -> list:
    player = lobby.session.get_player(client.player_id)
    player.hand = [create_card(t) for t in card_types]
    return player.hand


def stack_deck(lobby: Lobby, *card_types: CardType) -> list:
    """Nastaví dobírací balíček (první = vrchní karta)."""
    lobby.session.draw_pile = [create_card(t) for t in card_types]
    lobby.session.peeked_cards = []
    return lobby.session.draw_pile
