import json
import uuid
import time
import asyncio
import logging
import os
from typing import Dict, Optional
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.models import GameSession, Player, GameStatus, Lobby
from app.game_logic import initialize_game, draw_card, play_card, end_turn, check_game_end

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("exploding_kittens")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "TajneHeslo")
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")]
TOKEN_EXPIRY_SECONDS = int(os.environ.get("TOKEN_EXPIRY_SECONDS", "3600"))
MAX_PLAYER_NAME_LENGTH = int(os.environ.get("MAX_PLAYER_NAME_LENGTH", "20"))
MAX_WS_MESSAGE_SIZE = int(os.environ.get("MAX_WS_MESSAGE_SIZE", "4096"))
MAX_CONNECTIONS_PER_IP = int(os.environ.get("MAX_CONNECTIONS_PER_IP", "10"))
RATE_LIMIT_PER_SECOND = int(os.environ.get("RATE_LIMIT_PER_SECOND", "10"))
MAX_LOBBIES = int(os.environ.get("MAX_LOBBIES", "10"))
MAX_LOBBY_NAME_LENGTH = int(os.environ.get("MAX_LOBBY_NAME_LENGTH", "30"))
LOBBY_INACTIVITY_TIMEOUT = int(os.environ.get("LOBBY_INACTIVITY_TIMEOUT", "1800"))  # 30 min
WS_HEARTBEAT_TIMEOUT = int(os.environ.get("WS_HEARTBEAT_TIMEOUT", "45"))  # seconds


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
class RateLimiter:
    def __init__(self, max_messages: int, window: float = 1.0):
        self.max_messages = max_messages
        self.window = window
        self._buckets: Dict[str, list] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window
        bucket = [t for t in self._buckets[key] if t > cutoff]
        if len(bucket) >= self.max_messages:
            self._buckets[key] = bucket
            return False
        bucket.append(now)
        self._buckets[key] = bucket
        return True

    def cleanup(self):
        now = time.monotonic()
        stale = [k for k, v in self._buckets.items()
                 if not v or v[-1] < now - self.window * 10]
        for k in stale:
            del self._buckets[k]


rate_limiter = RateLimiter(RATE_LIMIT_PER_SECOND)
ip_connections: Dict[str, int] = defaultdict(int)


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


# ---------------------------------------------------------------------------
# Global state (multi-lobby)
# ---------------------------------------------------------------------------
lobbies: Dict[str, Lobby] = {}
connected_clients: Dict[str, WebSocket] = {}
player_last_activity: Dict[str, float] = {}

# player_id -> {name, token, is_super_power, token_created_at, lobby_id}
player_registry: Dict[str, dict] = {}
token_map: Dict[str, str] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _client_ip(ws: WebSocket) -> str:
    return ws.client.host if ws.client else "unknown"


def _is_origin_allowed(ws: WebSocket) -> bool:
    if "*" in ALLOWED_ORIGINS:
        return True
    origin = ws.headers.get("origin", "")
    return origin in ALLOWED_ORIGINS


def _is_token_expired(info: dict) -> bool:
    if TOKEN_EXPIRY_SECONDS <= 0:
        return False
    return (time.time() - info.get("token_created_at", 0)) > TOKEN_EXPIRY_SECONDS


def _get_player_lobby(player_id: str) -> Optional[Lobby]:
    info = player_registry.get(player_id)
    if not info:
        return None
    lid = info.get("lobby_id")
    if not lid:
        return None
    return lobbies.get(lid)


def _build_lobby_list() -> list:
    result = []
    for lid, lobby in lobbies.items():
        result.append({
            "lobby_id": lid,
            "name": lobby.name,
            "player_count": len(lobby.session.players),
            "max_players": 5,
            "status": lobby.session.status.value,
        })
    return result


def _touch_lobby(lobby: Lobby) -> None:
    lobby.last_activity = time.time()


def _remove_player_from_lobby(player_id: str, lobby: Lobby) -> None:
    """Remove player from lobby, handle turn advancement if needed."""
    session = lobby.session
    player = session.get_player(player_id)
    if not player:
        return

    if session.status == GameStatus.PLAYING and player.alive:
        player.alive = False
        session.pending_turns.pop(player_id, None)
        if session.current_player_id == player_id:
            end_turn(session, force=True)

    session.players = [p for p in session.players if p.player_id != player_id]


# ---------------------------------------------------------------------------
# Broadcast helpers
# ---------------------------------------------------------------------------
async def broadcast_to_lobby(lobby: Lobby, message: dict):
    disconnected = []
    for p in lobby.session.players:
        ws = connected_clients.get(p.player_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(p.player_id)
    for pid in disconnected:
        connected_clients.pop(pid, None)


async def send_lobby_list_to(player_id: str):
    ws = connected_clients.get(player_id)
    if not ws:
        return
    try:
        await ws.send_json({"type": "lobby_list", "lobbies": _build_lobby_list()})
    except Exception:
        pass


async def broadcast_lobby_list():
    """Send lobby list to all players not currently in a room."""
    for pid, info in list(player_registry.items()):
        if not info.get("lobby_id") and pid in connected_clients:
            await send_lobby_list_to(pid)


async def send_room_state(lobby: Lobby, target_player_id: Optional[str] = None):
    can_start = (
        lobby.session.status == GameStatus.WAITING
        and 2 <= len(lobby.session.players) <= 5
        and all(p.ready for p in lobby.session.players)
    )
    message = {
        "type": "lobby_state",
        "lobby_id": lobby.lobby_id,
        "lobby_name": lobby.name,
        "status": lobby.session.status.value,
        "players": [p.to_dict(hide_hand=True) for p in lobby.session.players],
        "can_start": can_start,
    }

    if target_player_id:
        ws = connected_clients.get(target_player_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                pass
        return

    if lobby.session.status in (GameStatus.PLAYING, GameStatus.FINISHED):
        for p in lobby.session.players:
            if not p.alive:
                ws = connected_clients.get(p.player_id)
                if ws:
                    try:
                        await ws.send_json(message)
                    except Exception:
                        pass
    else:
        await broadcast_to_lobby(lobby, message)


async def send_game_state(lobby: Lobby):
    for player in lobby.session.players:
        if (not player.hand or len(player.hand) == 0) and player.alive:
            continue
        ws = connected_clients.get(player.player_id)
        if not ws:
            continue
        try:
            state = {
                "type": "game_state",
                "lobby_id": lobby.lobby_id,
                "lobby_name": lobby.name,
                "status": lobby.session.status.value,
                "current_player_id": lobby.session.current_player_id,
                "pending_turns": lobby.session.pending_turns.copy(),
                "draw_pile_size": len(lobby.session.draw_pile),
                "discard_pile_size": len(lobby.session.discard_pile),
                "reverse_direction": lobby.session.reverse_direction,
                "can_nope": lobby.session.last_action_for_nope is not None,
                "players": [],
            }
            for p in lobby.session.players:
                if (not p.hand or len(p.hand) == 0) and p.alive:
                    continue
                hide = p.player_id != player.player_id
                state["players"].append(p.to_dict(hide_hand=hide))
            await ws.send_json(state)
        except Exception:
            logger.warning("Failed to send game state to %s", player.name)


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------
async def cleanup_empty_lobbies():
    while True:
        await asyncio.sleep(30)
        now = time.time()
        to_delete = []
        for lid, lobby in list(lobbies.items()):
            if len(lobby.session.players) == 0 and now - lobby.created_at > 60:
                to_delete.append(lid)
            elif now - lobby.last_activity > LOBBY_INACTIVITY_TIMEOUT:
                to_delete.append(lid)
        for lid in to_delete:
            lobby = lobbies.pop(lid, None)
            if lobby:
                for p in list(lobby.session.players):
                    pinfo = player_registry.get(p.player_id)
                    if pinfo:
                        pinfo["lobby_id"] = None
                    pws = connected_clients.get(p.player_id)
                    if pws:
                        try:
                            await pws.send_json({
                                "type": "you_were_removed",
                                "message": "Místnost byla ukončena z důvodu neaktivity",
                            })
                        except Exception:
                            pass
                logger.info("Removed lobby %s (empty or inactive)", lid)
        if to_delete:
            await broadcast_lobby_list()


async def periodic_cleanup():
    while True:
        await asyncio.sleep(60)
        rate_limiter.cleanup()
        stale_ips = [ip for ip, cnt in ip_connections.items() if cnt <= 0]
        for ip in stale_ips:
            del ip_connections[ip]
        now = time.time()
        stale_players = [
            pid for pid, info in list(player_registry.items())
            if pid not in connected_clients
            and _is_token_expired(info)
            and not info.get("lobby_id")
        ]
        for pid in stale_players:
            t = player_registry.pop(pid, {}).get("token")
            if t:
                token_map.pop(t, None)


async def _force_disconnect_player(pid: str) -> None:
    """Clean up a player who stopped responding (heartbeat expired).

    Removes them from connected_clients, their lobby, handles game-end
    checks, and broadcasts updated state.  Designed to be called from the
    heartbeat monitor *and* from the finally-block (idempotent).
    """
    ws = connected_clients.pop(pid, None)
    player_last_activity.pop(pid, None)

    info = player_registry.get(pid)
    if not info:
        logger.info("_force_disconnect: pid=%s not in registry, skip", pid)
        return

    pname = info.get("name", "?")
    lobby_id = info.get("lobby_id")
    logger.info("_force_disconnect: player=%s (%s) lobby=%s", pname, pid, lobby_id)

    if lobby_id and lobby_id in lobbies:
        lobby = lobbies[lobby_id]
        _remove_player_from_lobby(pid, lobby)
        info["lobby_id"] = None
        remaining = len(lobby.session.players)
        alive_count = len(lobby.session.get_alive_players())
        logger.info(
            "_force_disconnect: removed from lobby %s, remaining=%d alive=%d status=%s",
            lobby.lobby_id, remaining, alive_count, lobby.session.status.value,
        )

        if remaining == 0:
            lobbies.pop(lobby.lobby_id, None)
            logger.info("Lobby %s deleted (empty after disconnect)", lobby.lobby_id)
        else:
            if lobby.session.status == GameStatus.PLAYING:
                winner = check_game_end(lobby.session)
                if winner:
                    logger.info("_force_disconnect: game_end winner=%s (%s)", winner.name, winner.player_id)
                    await broadcast_to_lobby(lobby, {
                        "type": "game_end",
                        "winner_id": winner.player_id,
                        "winner_name": winner.name,
                    })
                    lobby.session.status = GameStatus.FINISHED
                    for p in lobby.session.players:
                        p.ready = False
                else:
                    logger.info("_force_disconnect: no winner yet")
                await send_game_state(lobby)
            await send_room_state(lobby)
        await broadcast_lobby_list()
    else:
        logger.info("_force_disconnect: player=%s not in any lobby", pname)

    if ws:
        try:
            await ws.close(code=4000)
        except Exception:
            pass


async def monitor_heartbeats():
    """Periodically check for players who stopped sending pings and
    force-disconnect them.  This runs independently of the per-connection
    receive loop and does not rely on WebSocket close detection."""
    while True:
        await asyncio.sleep(10)
        now = time.time()
        stale = [
            pid for pid, last in list(player_last_activity.items())
            if now - last > WS_HEARTBEAT_TIMEOUT and pid in connected_clients
        ]
        for pid in stale:
            pname = player_registry.get(pid, {}).get("name", "?")
            logger.info("Heartbeat expired: player=%s (%s), forcing disconnect", pid, pname)
            try:
                await _force_disconnect_player(pid)
            except Exception:
                logger.exception("Error in heartbeat disconnect for %s", pid)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    lobby_task = asyncio.create_task(cleanup_empty_lobbies())
    cleanup_task = asyncio.create_task(periodic_cleanup())
    heartbeat_task = asyncio.create_task(monitor_heartbeats())
    logger.info("Server started (log_level=%s, token_expiry=%ds)", LOG_LEVEL, TOKEN_EXPIRY_SECONDS)
    yield
    lobby_task.cancel()
    cleanup_task.cancel()
    heartbeat_task.cancel()
    logger.info("Server stopped")


# ---------------------------------------------------------------------------
# App + middleware
# ---------------------------------------------------------------------------
app = FastAPI(title="Výbušná koťátka", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------
@app.get("/")
async def get_index():
    return FileResponse("static/index.html")


@app.get("/super_power")
async def get_super_power():
    return FileResponse("static/super_power.html")


@app.get("/health")
async def health_check():
    return JSONResponse({
        "status": "ok",
        "lobbies": len(lobbies),
        "players": len(player_registry),
        "connections": len(connected_clients),
    })


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_ip = _client_ip(websocket)
    await websocket.accept()

    if not _is_origin_allowed(websocket):
        logger.warning("Rejected WS: disallowed origin (ip=%s)", client_ip)
        await websocket.close(code=4003)
        return

    if ip_connections[client_ip] >= MAX_CONNECTIONS_PER_IP:
        logger.warning("Rejected WS: connection limit for %s", client_ip)
        await websocket.close(code=4029)
        return

    ip_connections[client_ip] += 1
    logger.info("WS connected (ip=%s, active=%d)", client_ip, ip_connections[client_ip])
    player_id: Optional[str] = None

    try:
        while True:
            raw = await websocket.receive_text()

            if player_id:
                player_last_activity[player_id] = time.time()

            if len(raw) > MAX_WS_MESSAGE_SIZE:
                await websocket.send_json({"type": "error", "message": "Zpráva je příliš velká"})
                continue

            if not rate_limiter.is_allowed(client_ip):
                await websocket.send_json({"type": "error", "message": "Příliš mnoho zpráv, zpomal"})
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Neplatný formát zprávy"})
                continue

            if not isinstance(data, dict) or not isinstance(data.get("type"), str):
                await websocket.send_json({"type": "error", "message": "Neplatný formát zprávy"})
                continue

            msg_type = data["type"]

            if msg_type == "ping":
                try:
                    await websocket.send_json({"type": "pong"})
                except Exception:
                    pass
                continue

            logger.debug("WS msg=%s player=%s ip=%s", msg_type, player_id, client_ip)

            # ==============================================================
            # JOIN (authenticate, show lobby browser)
            # ==============================================================
            if msg_type == "join":
                name = str(data.get("name", "")).strip()
                password = str(data.get("password", "")).strip()
                is_super_power = False

                if not name:
                    await websocket.send_json({"type": "error", "message": "Jméno je povinné"})
                    continue
                if len(name) > MAX_PLAYER_NAME_LENGTH:
                    await websocket.send_json({"type": "error", "message": f"Jméno je příliš dlouhé (max {MAX_PLAYER_NAME_LENGTH} znaků)"})
                    continue
                if password:
                    if password != ADMIN_PASSWORD:
                        logger.warning("Invalid admin password attempt (ip=%s)", client_ip)
                        await websocket.send_json({"type": "error", "message": "Nesprávné heslo"})
                        continue
                    is_super_power = True

                existing_names = [i["name"].lower() for i in player_registry.values()]
                if name.lower() in existing_names:
                    await websocket.send_json({"type": "error", "message": "Jméno je již obsazené"})
                    continue

                player_id = str(uuid.uuid4())
                new_token = str(uuid.uuid4())
                player_registry[player_id] = {
                    "name": name,
                    "token": new_token,
                    "is_super_power": is_super_power,
                    "token_created_at": time.time(),
                    "lobby_id": None,
                }
                token_map[new_token] = player_id
                connected_clients[player_id] = websocket
                player_last_activity[player_id] = time.time()
                logger.info("Player joined: %s (id=%s, super=%s)", name, player_id, is_super_power)

                await websocket.send_json({
                    "type": "join_ok",
                    "player_id": player_id,
                    "token": new_token,
                    "is_super_power": is_super_power,
                })
                await send_lobby_list_to(player_id)

            # ==============================================================
            # RECONNECT
            # ==============================================================
            elif msg_type == "reconnect":
                rec_token = data.get("token")
                if not rec_token or not isinstance(rec_token, str):
                    await websocket.send_json({"type": "error", "message": "Token je povinný"})
                    continue

                rec_pid = token_map.get(rec_token)
                if not rec_pid or rec_pid not in player_registry:
                    await websocket.send_json({"type": "error", "message": "Neplatný token"})
                    continue

                info = player_registry[rec_pid]
                if _is_token_expired(info):
                    await websocket.send_json({"type": "error", "message": "Token vypršel, přihlaš se znovu"})
                    continue

                player_id = rec_pid
                connected_clients[player_id] = websocket
                player_last_activity[player_id] = time.time()
                logger.info("Player reconnected: %s (id=%s)", info["name"], player_id)

                await websocket.send_json({
                    "type": "reconnect_ok",
                    "player_id": player_id,
                    "is_super_power": info.get("is_super_power", False),
                })

                lobby_id = info.get("lobby_id")
                if lobby_id and lobby_id in lobbies:
                    lobby = lobbies[lobby_id]
                    await websocket.send_json({
                        "type": "lobby_joined",
                        "lobby_id": lobby.lobby_id,
                        "lobby_name": lobby.name,
                    })
                    if lobby.session.status == GameStatus.PLAYING:
                        player = lobby.session.get_player(player_id)
                        if player and player.hand:
                            await send_game_state(lobby)
                        else:
                            await send_room_state(lobby, target_player_id=player_id)
                    else:
                        await send_room_state(lobby)
                else:
                    if lobby_id:
                        info["lobby_id"] = None
                    await send_lobby_list_to(player_id)

            # ==============================================================
            # LIST LOBBIES
            # ==============================================================
            elif msg_type == "list_lobbies":
                if player_id:
                    await send_lobby_list_to(player_id)

            # ==============================================================
            # CREATE LOBBY
            # ==============================================================
            elif msg_type == "create_lobby":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue

                info = player_registry.get(player_id)
                if not info:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue

                if info.get("lobby_id"):
                    await websocket.send_json({"type": "error", "message": "Již jste v místnosti"})
                    continue

                if len(lobbies) >= MAX_LOBBIES:
                    await websocket.send_json({"type": "error", "message": f"Maximální počet místností ({MAX_LOBBIES}) dosažen"})
                    continue

                lobby_name = str(data.get("name", "")).strip()
                if not lobby_name:
                    lobby_name = f"Místnost {len(lobbies) + 1}"
                if len(lobby_name) > MAX_LOBBY_NAME_LENGTH:
                    lobby_name = lobby_name[:MAX_LOBBY_NAME_LENGTH]

                lobby_id = str(uuid.uuid4())[:8]
                lobby = Lobby(lobby_id=lobby_id, name=lobby_name)
                lobbies[lobby_id] = lobby

                player = Player(
                    player_id=player_id,
                    name=info["name"],
                    token=info["token"],
                    is_super_power=info.get("is_super_power", False),
                )
                lobby.session.players.append(player)
                info["lobby_id"] = lobby_id

                logger.info("Lobby created: %s (%s) by %s", lobby_name, lobby_id, info["name"])

                await websocket.send_json({
                    "type": "lobby_joined",
                    "lobby_id": lobby_id,
                    "lobby_name": lobby_name,
                })
                await send_room_state(lobby)
                await broadcast_lobby_list()

            # ==============================================================
            # JOIN LOBBY
            # ==============================================================
            elif msg_type == "join_lobby":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue

                info = player_registry.get(player_id)
                if not info:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue

                if info.get("lobby_id"):
                    await websocket.send_json({"type": "error", "message": "Již jste v místnosti"})
                    continue

                target_lid = data.get("lobby_id")
                if not target_lid or target_lid not in lobbies:
                    await websocket.send_json({"type": "error", "message": "Místnost neexistuje"})
                    continue

                lobby = lobbies[target_lid]
                if lobby.session.status != GameStatus.WAITING:
                    await websocket.send_json({"type": "error", "message": "V této místnosti již probíhá hra"})
                    continue
                if len(lobby.session.players) >= 5:
                    await websocket.send_json({"type": "error", "message": "Místnost je plná (max 5)"})
                    continue

                player = Player(
                    player_id=player_id,
                    name=info["name"],
                    token=info["token"],
                    is_super_power=info.get("is_super_power", False),
                )
                lobby.session.players.append(player)
                info["lobby_id"] = target_lid

                logger.info("Player %s joined lobby %s", info["name"], lobby.name)

                await websocket.send_json({
                    "type": "lobby_joined",
                    "lobby_id": lobby.lobby_id,
                    "lobby_name": lobby.name,
                })
                await send_room_state(lobby)
                if lobby.session.status == GameStatus.PLAYING:
                    await send_game_state(lobby)
                await broadcast_lobby_list()

            # ==============================================================
            # LEAVE ROOM (back to lobby browser)
            # ==============================================================
            elif msg_type == "leave_room":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue

                info = player_registry.get(player_id)
                lobby = _get_player_lobby(player_id)

                if lobby:
                    _remove_player_from_lobby(player_id, lobby)
                    if info:
                        info["lobby_id"] = None

                    await websocket.send_json({"type": "lobby_left"})

                    if len(lobby.session.players) == 0:
                        lobbies.pop(lobby.lobby_id, None)
                        logger.info("Lobby %s deleted (empty)", lobby.lobby_id)
                    else:
                        winner = check_game_end(lobby.session)
                        if winner and lobby.session.status == GameStatus.PLAYING:
                            await broadcast_to_lobby(lobby, {
                                "type": "game_end",
                                "winner_id": winner.player_id,
                                "winner_name": winner.name,
                            })
                            lobby.session.status = GameStatus.FINISHED
                            for p in lobby.session.players:
                                p.ready = False
                            await send_game_state(lobby)
                        else:
                            await send_room_state(lobby)
                            if lobby.session.status == GameStatus.PLAYING:
                                await send_game_state(lobby)

                    await send_lobby_list_to(player_id)
                    await broadcast_lobby_list()
                else:
                    await websocket.send_json({"type": "lobby_left"})

            # ==============================================================
            # LOGOUT (disconnect completely)
            # ==============================================================
            elif msg_type == "logout":
                if player_id:
                    lobby = _get_player_lobby(player_id)
                    if lobby:
                        _remove_player_from_lobby(player_id, lobby)
                        info = player_registry.get(player_id)
                        if info:
                            info["lobby_id"] = None
                        if len(lobby.session.players) == 0:
                            lobbies.pop(lobby.lobby_id, None)
                        else:
                            winner = check_game_end(lobby.session)
                            if winner and lobby.session.status == GameStatus.PLAYING:
                                await broadcast_to_lobby(lobby, {
                                    "type": "game_end",
                                    "winner_id": winner.player_id,
                                    "winner_name": winner.name,
                                })
                                lobby.session.status = GameStatus.FINISHED
                                for p in lobby.session.players:
                                    p.ready = False
                                await send_game_state(lobby)
                            else:
                                await send_room_state(lobby)

                    t = player_registry.pop(player_id, {}).get("token")
                    if t:
                        token_map.pop(t, None)
                    connected_clients.pop(player_id, None)
                    await broadcast_lobby_list()

                await websocket.send_json({"type": "leave_ok"})
                player_id = None
                break

            # ==============================================================
            # SET READY
            # ==============================================================
            elif msg_type == "set_ready":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue

                lobby = _get_player_lobby(player_id)
                if not lobby:
                    await websocket.send_json({"type": "error", "message": "Nejste v žádné místnosti"})
                    continue

                player = lobby.session.get_player(player_id)
                if not player:
                    await websocket.send_json({"type": "error", "message": "Hráč nenalezen"})
                    continue

                player.ready = bool(data.get("ready", False))
                _touch_lobby(lobby)
                await send_room_state(lobby)

                if (
                    lobby.session.status == GameStatus.WAITING
                    and 2 <= len(lobby.session.players) <= 5
                    and all(p.ready for p in lobby.session.players)
                ):
                    initialize_game(lobby.session)
                    await send_game_state(lobby)

            # ==============================================================
            # PLAY CARD
            # ==============================================================
            elif msg_type == "play_card":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue

                lobby = _get_player_lobby(player_id)
                if not lobby:
                    await websocket.send_json({"type": "error", "message": "Nejste v žádné místnosti"})
                    continue

                session = lobby.session
                if session.status != GameStatus.PLAYING:
                    await websocket.send_json({"type": "error", "message": "Hra neprobíhá"})
                    continue

                player = session.get_player(player_id)
                if not player or not player.alive:
                    await websocket.send_json({"type": "error", "message": "Hráč není aktivní"})
                    continue

                card_id = data.get("card_id")
                target_pid = data.get("target_player_id")

                card_in_hand = next((c for c in player.hand if c.id == card_id), None)
                if not card_in_hand:
                    await websocket.send_json({"type": "error", "message": "Karta není v ruce"})
                    continue

                if session.current_player_id != player_id:
                    if card_in_hand.type.value != "NOPE":
                        await websocket.send_json({"type": "error", "message": "Není váš tah"})
                        continue
                    if not session.last_action_for_nope:
                        await websocket.send_json({"type": "error", "message": "Není žádná akce k zrušení"})
                        continue

                _touch_lobby(lobby)
                result = play_card(session, player, card_id, target_pid)

                if "error" in result:
                    await websocket.send_json({"type": "error", "message": result["error"]})
                else:
                    await broadcast_to_lobby(lobby, {
                        "type": "card_played",
                        "player_id": player_id,
                        "player_name": player.name,
                        "card_type": result.get("card_type"),
                        "result": result,
                        "can_nope": session.last_action_for_nope is not None,
                    })

                    if result.get("card_type") == "FAVOR" and result.get("favor_card"):
                        tp = result.get("target_player_id")
                        if tp and tp in connected_clients:
                            await asyncio.sleep(0.1)
                            try:
                                await connected_clients[tp].send_json({
                                    "type": "favor_card_taken",
                                    "from_player_name": player.name,
                                    "card_title": result["favor_card"]["title"],
                                })
                            except Exception:
                                pass

                    if result.get("action_cancelled") and result.get("return_turn_to"):
                        return_pid = result["return_turn_to"]
                        rp = session.get_player(return_pid)
                        if rp and rp.alive:
                            session.current_player_id = return_pid
                            if return_pid not in session.pending_turns:
                                session.pending_turns[return_pid] = 1
                            logger.debug("NOPE: turn returned to %s", rp.name)
                    elif result.get("action_restored"):
                        if result.get("end_turn"):
                            force_end = result.get("force_end_turn", False)
                            end_turn(session, force=force_end)
                    elif result.get("end_turn"):
                        force_end = result.get("force_end_turn", False)
                        end_turn(session, force=force_end)

                    winner = check_game_end(session)
                    if winner:
                        await broadcast_to_lobby(lobby, {
                            "type": "game_end",
                            "winner_id": winner.player_id,
                            "winner_name": winner.name,
                        })
                        session.status = GameStatus.FINISHED
                        for p in session.players:
                            p.ready = False
                    await send_game_state(lobby)

            # ==============================================================
            # DRAW CARD
            # ==============================================================
            elif msg_type == "draw_card":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue

                lobby = _get_player_lobby(player_id)
                if not lobby:
                    await websocket.send_json({"type": "error", "message": "Nejste v žádné místnosti"})
                    continue

                session = lobby.session
                if session.status != GameStatus.PLAYING:
                    await websocket.send_json({"type": "error", "message": "Hra neprobíhá"})
                    continue
                if session.current_player_id != player_id:
                    await websocket.send_json({"type": "error", "message": "Není váš tah"})
                    continue

                player = session.get_player(player_id)
                if not player or not player.alive:
                    await websocket.send_json({"type": "error", "message": "Hráč není aktivní"})
                    continue

                _touch_lobby(lobby)
                card = draw_card(session, player)

                if card and card.type.value == "EXPLODING_KITTEN":
                    await broadcast_to_lobby(lobby, {
                        "type": "player_died",
                        "player_id": player_id,
                        "player_name": player.name,
                    })
                    winner = check_game_end(session)
                    if winner:
                        await broadcast_to_lobby(lobby, {
                            "type": "game_end",
                            "winner_id": winner.player_id,
                            "winner_name": winner.name,
                        })
                        session.status = GameStatus.FINISHED
                        for p in session.players:
                            p.ready = False
                    else:
                        end_turn(session)
                        winner = check_game_end(session)
                        if winner:
                            await broadcast_to_lobby(lobby, {
                                "type": "game_end",
                                "winner_id": winner.player_id,
                                "winner_name": winner.name,
                            })
                            session.status = GameStatus.FINISHED
                            for p in session.players:
                                p.ready = False
                    await send_game_state(lobby)
                else:
                    if card:
                        await websocket.send_json({"type": "card_drawn", "card": card.to_dict()})
                    else:
                        await broadcast_to_lobby(lobby, {
                            "type": "exploding_kitten_defused",
                            "player_id": player_id,
                            "player_name": player.name,
                        })
                    end_turn(session)
                    await send_game_state(lobby)

            # ==============================================================
            # END TURN
            # ==============================================================
            elif msg_type == "end_turn":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue
                lobby = _get_player_lobby(player_id)
                if not lobby:
                    continue
                session = lobby.session
                if session.status != GameStatus.PLAYING or session.current_player_id != player_id:
                    continue
                end_turn(session)
                await send_game_state(lobby)

            # ==============================================================
            # RESTART GAME
            # ==============================================================
            elif msg_type == "restart_game":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue

                lobby = _get_player_lobby(player_id)
                if not lobby:
                    await websocket.send_json({"type": "error", "message": "Nejste v žádné místnosti"})
                    continue

                _touch_lobby(lobby)
                logger.info("Game restart in lobby %s by %s", lobby.lobby_id, player_id)

                lobby.session.status = GameStatus.WAITING
                for p in lobby.session.players:
                    p.ready = False
                    p.alive = True
                lobby.session.draw_pile = []
                lobby.session.discard_pile = []
                lobby.session.pending_turns = {}
                lobby.session.last_action_for_nope = None
                lobby.session.peeked_cards = []
                lobby.session.current_player_id = None
                lobby.session.reverse_direction = False

                await send_room_state(lobby)
                await broadcast_lobby_list()

            # ==============================================================
            # REMOVE PLAYER (admin)
            # ==============================================================
            elif msg_type == "remove_player":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue

                info = player_registry.get(player_id)
                if not info or not info.get("is_super_power"):
                    await websocket.send_json({"type": "error", "message": "Nemáte oprávnění"})
                    continue

                lobby = _get_player_lobby(player_id)
                if not lobby:
                    await websocket.send_json({"type": "error", "message": "Nejste v žádné místnosti"})
                    continue

                target_pid = data.get("target_player_id")
                if not target_pid:
                    continue

                target = lobby.session.get_player(target_pid)
                if not target:
                    await websocket.send_json({"type": "error", "message": "Hráč nenalezen"})
                    continue

                if target.is_super_power:
                    await websocket.send_json({"type": "error", "message": "Nelze odebrat admina"})
                    continue

                _remove_player_from_lobby(target_pid, lobby)
                tinfo = player_registry.get(target_pid)
                if tinfo:
                    tinfo["lobby_id"] = None

                target_ws = connected_clients.get(target_pid)
                if target_ws:
                    try:
                        await target_ws.send_json({
                            "type": "you_were_removed",
                            "message": "Byli jste odebráni z místnosti administrátorem",
                        })
                    except Exception:
                        pass

                await broadcast_to_lobby(lobby, {
                    "type": "player_removed",
                    "player_id": target_pid,
                    "player_name": target.name,
                })

                winner = check_game_end(lobby.session)
                if winner and lobby.session.status == GameStatus.PLAYING:
                    await broadcast_to_lobby(lobby, {
                        "type": "game_end",
                        "winner_id": winner.player_id,
                        "winner_name": winner.name,
                    })
                    lobby.session.status = GameStatus.FINISHED
                    for p in lobby.session.players:
                        p.ready = False
                    await send_game_state(lobby)
                else:
                    await send_room_state(lobby)
                    if lobby.session.status == GameStatus.PLAYING:
                        await send_game_state(lobby)
                await broadcast_lobby_list()

            # ==============================================================
            # VIEW DECK (admin)
            # ==============================================================
            elif msg_type == "view_deck":
                if not player_id:
                    continue
                info = player_registry.get(player_id)
                if not info or not info.get("is_super_power"):
                    continue
                lobby = _get_player_lobby(player_id)
                if not lobby or lobby.session.status != GameStatus.PLAYING:
                    continue
                await websocket.send_json({
                    "type": "deck_view",
                    "cards": [c.to_dict() for c in lobby.session.draw_pile],
                    "count": len(lobby.session.draw_pile),
                })

            # ==============================================================
            # END GAME (admin)
            # ==============================================================
            elif msg_type == "end_game":
                if not player_id:
                    continue
                info = player_registry.get(player_id)
                if not info or not info.get("is_super_power"):
                    continue
                lobby = _get_player_lobby(player_id)
                if not lobby or lobby.session.status != GameStatus.PLAYING:
                    continue

                alive = lobby.session.get_alive_players()
                winner = alive[0] if alive else None
                lobby.session.status = GameStatus.FINISHED
                for p in lobby.session.players:
                    p.ready = False

                await broadcast_to_lobby(lobby, {
                    "type": "game_end",
                    "winner_id": winner.player_id if winner else None,
                    "winner_name": winner.name if winner else None,
                    "ended_by_admin": True,
                })
                await send_game_state(lobby)

            # ==============================================================
            # DELETE LOBBY (admin, from browser)
            # ==============================================================
            elif msg_type == "delete_lobby":
                if not player_id:
                    continue
                info = player_registry.get(player_id)
                if not info or not info.get("is_super_power"):
                    await websocket.send_json({"type": "error", "message": "Nemáte oprávnění"})
                    continue

                target_lid = data.get("lobby_id")
                if not target_lid or target_lid not in lobbies:
                    await websocket.send_json({"type": "error", "message": "Místnost neexistuje"})
                    continue

                lobby = lobbies[target_lid]
                for p in list(lobby.session.players):
                    pinfo = player_registry.get(p.player_id)
                    if pinfo:
                        pinfo["lobby_id"] = None
                    pws = connected_clients.get(p.player_id)
                    if pws:
                        try:
                            await pws.send_json({
                                "type": "you_were_removed",
                                "message": "Místnost byla smazána administrátorem",
                            })
                        except Exception:
                            pass

                del lobbies[target_lid]
                logger.info("Lobby %s deleted by admin %s", target_lid, player_id)
                await broadcast_lobby_list()

            # ==============================================================
            # UNKNOWN
            # ==============================================================
            else:
                await websocket.send_json({"type": "error", "message": f"Neznámý typ zprávy: {msg_type}"})

    except WebSocketDisconnect:
        logger.info("WS disconnected: player=%s ip=%s", player_id, client_ip)
    except Exception as e:
        logger.error("WS error: player=%s ip=%s error=%s", player_id, client_ip, e, exc_info=True)
    finally:
        ip_connections[client_ip] = max(0, ip_connections[client_ip] - 1)
        if player_id:
            current_ws = connected_clients.get(player_id)
            if current_ws is websocket:
                logger.info("Finally cleanup: calling _force_disconnect for player=%s", player_id)
                try:
                    await _force_disconnect_player(player_id)
                except Exception as cleanup_err:
                    logger.error("Error in _force_disconnect_player: %s", cleanup_err, exc_info=True)
            else:
                already_gone = current_ws is None
                logger.info(
                    "Finally cleanup: player=%s already handled (ws_gone=%s)",
                    player_id, already_gone,
                )
                player_last_activity.pop(player_id, None)
