import json
import math
import uuid
import time
import asyncio
import logging
import os
import secrets
import unicodedata
from typing import Dict, Optional
from collections import defaultdict
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.models import GameSession, Player, GameStatus, Lobby
from app.game_logic import initialize_game, draw_card, play_card, end_turn

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
# Heslo pro admin režim Super Power se bere jen z prostředí (.env nebo
# docker-compose.yml). Bez nastaveného hesla je admin přihlášení vypnuté.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_MAX_FAILED_ATTEMPTS = max(1, int(os.environ.get("ADMIN_MAX_FAILED_ATTEMPTS", "5")))
ADMIN_LOCKOUT_SECONDS = int(os.environ.get("ADMIN_LOCKOUT_SECONDS", "900"))
# Prázdné = WebSocket jen ze stejného originu, na kterém běží server;
# "*" = libovolný origin; jinak čárkami oddělený seznam originů
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
TOKEN_EXPIRY_SECONDS = int(os.environ.get("TOKEN_EXPIRY_SECONDS", "3600"))
MAX_PLAYER_NAME_LENGTH = int(os.environ.get("MAX_PLAYER_NAME_LENGTH", "20"))
MAX_WS_MESSAGE_SIZE = int(os.environ.get("MAX_WS_MESSAGE_SIZE", "4096"))
MAX_CONNECTIONS_PER_IP = int(os.environ.get("MAX_CONNECTIONS_PER_IP", "10"))
MAX_REGISTRATIONS_PER_IP = int(os.environ.get("MAX_REGISTRATIONS_PER_IP", str(MAX_CONNECTIONS_PER_IP)))
RATE_LIMIT_PER_SECOND = int(os.environ.get("RATE_LIMIT_PER_SECOND", "10"))
MAX_LOBBIES = int(os.environ.get("MAX_LOBBIES", "10"))
MAX_LOBBY_NAME_LENGTH = int(os.environ.get("MAX_LOBBY_NAME_LENGTH", "22"))
LOBBY_INACTIVITY_TIMEOUT = int(os.environ.get("LOBBY_INACTIVITY_TIMEOUT", "1800"))  # 30 min
WS_HEARTBEAT_TIMEOUT = int(os.environ.get("WS_HEARTBEAT_TIMEOUT", "45"))  # seconds
# Jak dlouho se po výpadku spojení čeká na návrat hráče do běžící hry
DISCONNECT_GRACE_SECONDS = int(os.environ.get("DISCONNECT_GRACE_SECONDS", "15"))
MAX_REGISTERED_PLAYERS = int(os.environ.get("MAX_REGISTERED_PLAYERS", "200"))
# sekundy, po kterých se uklidí registrace hráče bez spojení a mimo lobby
REGISTRY_DISCONNECT_TTL = int(os.environ.get("REGISTRY_DISCONNECT_TTL", "300"))

# WebSocket close kódy (klient podle nich pozná, zda se má znovu připojit)
WS_CLOSE_CONNECTION_LOST = 4000
WS_CLOSE_REPLACED = 4001  # hráč se připojil z jiného okna/záložky
WS_CLOSE_ORIGIN_REJECTED = 4003
WS_CLOSE_TOO_MANY_CONNECTIONS = 4029

# Chybové kódy, podle kterých klient pozná neplatnou session
ERR_TOKEN_REQUIRED = "token_required"
ERR_INVALID_TOKEN = "invalid_token"
ERR_TOKEN_EXPIRED = "token_expired"
# Obnovení session po restartu prohlížeče, ale hráč je připojený v jiném okně
ERR_SESSION_ACTIVE = "session_active"

# Neviditelné znaky a znaky měnící směr textu - umožnily by vytvořit jméno,
# které vypadá stejně jako jméno jiného hráče
_FORBIDDEN_NAME_CHARS = frozenset(
    "​‎‏‪‫‬‭‮"
    "⁠⁡⁢⁣⁤⁦⁧⁨⁩﻿"
)

# Klíče výsledku zahrané karty, které smí vidět všichni hráči v místnosti.
# Soukromé údaje (karty z Pohlédni do budoucnosti, ukradená karta, pořadí
# balíčku po zamíchání) se posílají jen dotčeným hráčům.
PUBLIC_RESULT_KEYS = ("card_type", "message", "action_cancelled", "action_restored", "original_card_type")


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


class LoginThrottle:
    """Počítá neúspěšné pokusy o admin heslo (per IP). Po ADMIN_MAX_FAILED_ATTEMPTS
    pokusech během ADMIN_LOCKOUT_SECONDS je další přihlašování na stejnou dobu
    zablokované."""

    def __init__(self, max_failures: int, lockout_seconds: float):
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self._failures: Dict[str, list] = defaultdict(list)
        self._locked_until: Dict[str, float] = {}

    def lockout_remaining(self, key: str) -> float:
        until = self._locked_until.get(key)
        if until is None:
            return 0.0
        remaining = until - time.monotonic()
        if remaining <= 0:
            del self._locked_until[key]
            return 0.0
        return remaining

    def register_failure(self, key: str) -> None:
        now = time.monotonic()
        attempts = [t for t in self._failures[key] if t > now - self.lockout_seconds]
        attempts.append(now)
        if len(attempts) >= self.max_failures:
            self._locked_until[key] = now + self.lockout_seconds
            attempts = []
        self._failures[key] = attempts

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
        self._locked_until.pop(key, None)

    def cleanup(self) -> None:
        now = time.monotonic()
        for key in [k for k, v in self._failures.items() if not v or v[-1] < now - self.lockout_seconds]:
            del self._failures[key]
        for key in [k for k, until in self._locked_until.items() if until <= now]:
            del self._locked_until[key]


rate_limiter = RateLimiter(RATE_LIMIT_PER_SECOND)
admin_login_throttle = LoginThrottle(ADMIN_MAX_FAILED_ATTEMPTS, ADMIN_LOCKOUT_SECONDS)
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
# player_id -> čas odpojení během běžící hry (grace period pro reconnect)
disconnected_at: Dict[str, float] = {}

# player_id -> {name, token, is_super_power, token_created_at, last_seen, lobby_id, ip}
player_registry: Dict[str, dict] = {}
token_map: Dict[str, str] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _client_ip(ws: WebSocket) -> str:
    return ws.client.host if ws.client else "unknown"


def _host_key(netloc: str, scheme: str) -> str:
    """Normalizuje host[:port] pro porovnání - výchozí port schématu se vynechá."""
    netloc = netloc.strip().lower()
    default_port = {"http": "80", "https": "443", "ws": "80", "wss": "443"}.get(scheme)
    if default_port and netloc.endswith(":" + default_port):
        netloc = netloc[: -(len(default_port) + 1)]
    return netloc


def _is_origin_allowed(ws: WebSocket) -> bool:
    if "*" in ALLOWED_ORIGINS:
        return True
    origin = ws.headers.get("origin")
    if not origin:
        # Prohlížeč u WebSocketu Origin posílá vždy. Klienta mimo prohlížeč
        # kontrola originu stejně neomezí (hlavičku si nastaví libovolně).
        return True
    origin = origin.rstrip("/")
    if origin in ALLOWED_ORIGINS:
        return True
    if ALLOWED_ORIGINS:
        return False
    # Výchozí režim: jen stejný origin, na jakém server běží (i za reverse proxy)
    parts = urlsplit(origin)
    origin_host = _host_key(parts.netloc, parts.scheme)
    if not origin_host:
        return False
    server_hosts = [ws.headers.get("host", "")]
    forwarded_host = ws.headers.get("x-forwarded-host")
    if forwarded_host:
        server_hosts.extend(forwarded_host.split(","))
    return any(origin_host == _host_key(h, parts.scheme) for h in server_hosts if h.strip())


def _is_token_expired(info: dict) -> bool:
    """Token platí TOKEN_EXPIRY_SECONDS od poslední aktivity hráče (klouzavě),
    takže nevyprší uprostřed dlouhé hry."""
    if TOKEN_EXPIRY_SECONDS <= 0:
        return False
    last = max(info.get("token_created_at", 0), info.get("last_seen", 0))
    return (time.time() - last) > TOKEN_EXPIRY_SECONDS


def _has_forbidden_chars(text: str) -> bool:
    return any(ch in _FORBIDDEN_NAME_CHARS or unicodedata.category(ch) == "Cc" for ch in text)


def _drop_registration(pid: str) -> None:
    info = player_registry.pop(pid, None)
    if info and info.get("token"):
        token_map.pop(info["token"], None)


def _is_stale_registration(pid: str, info: dict) -> bool:
    """Registrace bez aktivního spojení a mimo místnost - lze ji uvolnit."""
    return pid not in connected_clients and not info.get("lobby_id")


def _evict_oldest_stale_registration(ip: Optional[str] = None) -> bool:
    """Uvolní nejstarší opuštěnou registraci (volitelně jen z dané IP).
    Opuštěné registrace tak neblokují místo novým hráčům."""
    candidates = [
        (info.get("disconnected_at", 0), pid)
        for pid, info in player_registry.items()
        if _is_stale_registration(pid, info) and (ip is None or info.get("ip") == ip)
    ]
    if not candidates:
        return False
    _, pid = min(candidates)
    _drop_registration(pid)
    return True


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


def _default_lobby_name() -> str:
    used = {lobby.name for lobby in lobbies.values()}
    n = 1
    while f"Místnost {n}" in used:
        n += 1
    return f"Místnost {n}"


def _touch_lobby(lobby: Lobby) -> None:
    lobby.last_activity = time.time()


def _can_start(session: GameSession) -> bool:
    return (
        session.status == GameStatus.WAITING
        and 2 <= len(session.players) <= 5
        and all(p.ready for p in session.players)
    )


def _reveal_admin(viewer: Player, player: Player) -> bool:
    """Příznak admina vidí jen hráč sám o sobě, případně jiný admin."""
    return viewer.player_id == player.player_id or viewer.is_super_power


def _public_play_result(result: dict) -> dict:
    return {k: result[k] for k in PUBLIC_RESULT_KEYS if k in result}


def _remove_player_from_lobby(player_id: str, lobby: Lobby) -> Optional[Player]:
    """Remove player from lobby, handle turn advancement if needed.
    Vrací odebraného hráče (None, pokud v místnosti nebyl)."""
    session = lobby.session
    player = session.get_player(player_id)
    if not player:
        return None

    if session.status == GameStatus.PLAYING and player.alive:
        player.alive = False
        session.pending_turns.pop(player_id, None)
        if session.current_player_id == player_id:
            end_turn(session, force=True)

    # Akci odcházejícího hráče už nejde zrušit přes Nené - tah by se vracel
    # hráči, který ve hře není
    last = session.last_action_for_nope
    if last and (last.get("original_action") or last).get("player_id") == player_id:
        session.last_action_for_nope = None

    session.players = [p for p in session.players if p.player_id != player_id]
    disconnected_at.pop(player_id, None)
    return player


# ---------------------------------------------------------------------------
# Broadcast helpers
# ---------------------------------------------------------------------------
async def send_to_player(player_id: str, message: dict) -> None:
    ws = connected_clients.get(player_id)
    if not ws:
        return
    try:
        await ws.send_json(message)
    except Exception as e:
        logger.warning("send_to_player: send to %s failed: %s", player_id, e)


async def broadcast_to_lobby(lobby: Lobby, message: dict):
    # Neserializovatelná zpráva je chyba programu - nesmí se tiše zahodit
    # a už vůbec ne interpretovat jako rozpad spojení všech hráčů
    try:
        payload = json.dumps(message)
    except (TypeError, ValueError):
        logger.exception("broadcast_to_lobby: message is not JSON serializable (type=%s)", message.get("type"))
        return

    for p in list(lobby.session.players):
        ws = connected_clients.get(p.player_id)
        if ws:
            try:
                await ws.send_text(payload)
            except Exception as e:
                # Rozpad spojení obslouží smyčka daného spojení nebo heartbeat.
                # Záznam tady nemažeme - hráč by jinak zůstal ve hře jako "duch",
                # kterého už nic neuklidí.
                logger.warning("broadcast_to_lobby: send to %s failed: %s", p.name, e)


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


def _player_state(viewer: Player, p: Player, now: float, hide_hand: bool) -> dict:
    d = p.to_dict(hide_hand=hide_hand, reveal_admin=_reveal_admin(viewer, p))
    if p.player_id in disconnected_at:
        # Zbývající čas na návrat odpojeného hráče (klient z něj odpočítává)
        left = disconnected_at[p.player_id] + DISCONNECT_GRACE_SECONDS - now
        d["reconnect_seconds_left"] = max(0, math.ceil(left))
    return d


async def send_room_state(lobby: Lobby):
    session = lobby.session
    can_start = _can_start(session)
    now = time.time()
    for viewer in list(session.players):
        ws = connected_clients.get(viewer.player_id)
        if not ws:
            continue
        try:
            await ws.send_json({
                "type": "lobby_state",
                "lobby_id": lobby.lobby_id,
                "lobby_name": lobby.name,
                "status": session.status.value,
                "players": [_player_state(viewer, p, now, hide_hand=True) for p in session.players],
                "can_start": can_start,
            })
        except Exception:
            logger.warning("Failed to send lobby state to %s", viewer.name)


async def send_game_state(lobby: Lobby):
    session = lobby.session
    now = time.time()
    for viewer in list(session.players):
        ws = connected_clients.get(viewer.player_id)
        if not ws:
            continue
        try:
            await ws.send_json({
                "type": "game_state",
                "lobby_id": lobby.lobby_id,
                "lobby_name": lobby.name,
                "status": session.status.value,
                "current_player_id": session.current_player_id,
                "pending_turns": session.pending_turns.copy(),
                "draw_pile_size": len(session.draw_pile),
                "discard_pile_size": len(session.discard_pile),
                "reverse_direction": session.reverse_direction,
                "can_nope": session.last_action_for_nope is not None,
                "players": [
                    _player_state(viewer, p, now, hide_hand=p.player_id != viewer.player_id)
                    for p in session.players
                ],
            })
        except Exception:
            logger.warning("Failed to send game state to %s", viewer.name)


# ---------------------------------------------------------------------------
# Game flow helpers
# ---------------------------------------------------------------------------
async def _announce_game_end_if_over(lobby: Lobby) -> bool:
    """Pokud ve hře zbyl poslední živý hráč, ukončí hru a oznámí vítěze.
    Vrací True, pokud hra právě skončila."""
    session = lobby.session
    if session.status != GameStatus.PLAYING:
        return False
    alive = session.get_alive_players()
    if len(alive) > 1:
        return False
    winner = alive[0] if alive else None
    session.status = GameStatus.FINISHED
    session.last_action_for_nope = None
    for p in session.players:
        p.ready = False
    logger.info("Game over in lobby %s, winner=%s", lobby.lobby_id, winner.name if winner else None)
    await broadcast_to_lobby(lobby, {
        "type": "game_end",
        "winner_id": winner.player_id if winner else None,
        "winner_name": winner.name if winner else None,
    })
    return True


async def _maybe_start_game(lobby: Lobby) -> bool:
    """Spustí hru, pokud jsou v místnosti 2-5 hráči a všichni jsou připraveni."""
    if not _can_start(lobby.session):
        return False
    initialize_game(lobby.session)
    logger.info("Game started in lobby %s (%d players)", lobby.lobby_id, len(lobby.session.players))
    await send_game_state(lobby)
    await broadcast_lobby_list()
    return True


async def _notify_player_left(lobby: Lobby, player: Optional[Player], reason: str) -> None:
    """Oznámí zbylým hráčům v rozehrané/dohrané hře, že hráč odešel.
    reason: "left" (odešel sám), "disconnected" (spadlo spojení),
    "timeout" (nevrátil se včas po výpadku)."""
    if not player or not lobby.session.players or lobby.session.status == GameStatus.WAITING:
        return
    await broadcast_to_lobby(lobby, {
        "type": "player_left",
        "player_id": player.player_id,
        "player_name": player.name,
        "reason": reason,
    })


async def _after_player_left(lobby: Lobby) -> None:
    """Společná obsluha místnosti po odchodu, odpojení nebo odebrání hráče:
    smaže prázdnou místnost, vyhodnotí konec hry a rozešle aktuální stav."""
    if not lobby.session.players:
        lobbies.pop(lobby.lobby_id, None)
        logger.info("Lobby %s deleted (empty)", lobby.lobby_id)
        return
    await _announce_game_end_if_over(lobby)
    await send_room_state(lobby)
    if lobby.session.status == GameStatus.WAITING:
        # Odešel poslední nepřipravený hráč -> zbytek může rovnou hrát
        await _maybe_start_game(lobby)
    else:
        await send_game_state(lobby)


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
                    disconnected_at.pop(p.player_id, None)
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
        admin_login_throttle.cleanup()
        stale_ips = [ip for ip, cnt in ip_connections.items() if cnt <= 0]
        for ip in stale_ips:
            del ip_connections[ip]
        now = time.time()
        stale_players = [
            pid for pid, info in list(player_registry.items())
            if _is_stale_registration(pid, info)
            and (
                _is_token_expired(info)
                # Odpojen bez lobby déle než TTL - nečekat na expiraci tokenu,
                # ať se neblokují jména a neplní paměť
                or now - info.get("disconnected_at", now) > REGISTRY_DISCONNECT_TTL
            )
        ]
        for pid in stale_players:
            _drop_registration(pid)


async def _force_disconnect_player(pid: str, reason: str = "disconnected") -> None:
    """Clean up a player who stopped responding (heartbeat expired).

    Removes them from connected_clients, their lobby, handles game-end
    checks, and broadcasts updated state.  Designed to be called from the
    heartbeat monitor *and* from the finally-block (idempotent).
    """
    ws = connected_clients.pop(pid, None)
    player_last_activity.pop(pid, None)
    disconnected_at.pop(pid, None)

    try:
        info = player_registry.get(pid)
        if not info:
            logger.info("_force_disconnect: pid=%s not in registry, skip", pid)
            return

        info["disconnected_at"] = time.time()

        pname = info.get("name", "?")
        lobby = _get_player_lobby(pid)
        logger.info("_force_disconnect: player=%s (%s) lobby=%s", pname, pid, info.get("lobby_id"))
        info["lobby_id"] = None

        if lobby:
            removed = _remove_player_from_lobby(pid, lobby)
            await _notify_player_left(lobby, removed, reason)
            logger.info(
                "_force_disconnect: removed from lobby %s, remaining=%d alive=%d status=%s",
                lobby.lobby_id, len(lobby.session.players),
                len(lobby.session.get_alive_players()), lobby.session.status.value,
            )
            await _after_player_left(lobby)
            await broadcast_lobby_list()
        else:
            logger.info("_force_disconnect: player=%s not in any lobby", pname)
    finally:
        if ws:
            try:
                await ws.close(code=WS_CLOSE_CONNECTION_LOST)
            except Exception:
                pass


async def _handle_connection_lost(pid: str) -> None:
    """Called when a player's connection drops (socket closed or heartbeat
    expired).  If the player is in a room, keep them there for
    DISCONNECT_GRACE_SECONDS so they can reconnect (reload stránky, pád
    prohlížeče); otherwise remove them immediately via _force_disconnect_player."""
    info = player_registry.get(pid)
    lobby = _get_player_lobby(pid)
    player = lobby.session.get_player(pid) if lobby else None

    if info and lobby and player:
        ws = connected_clients.pop(pid, None)
        player_last_activity.pop(pid, None)
        disconnected_at[pid] = time.time()
        info["disconnected_at"] = time.time()
        player.connected = False
        logger.info(
            "Player %s (%s) disconnected from lobby %s, grace period %ds",
            info.get("name", "?"), pid, lobby.lobby_id, DISCONNECT_GRACE_SECONDS,
        )
        if ws:
            try:
                await ws.close(code=WS_CLOSE_CONNECTION_LOST)
            except Exception:
                pass
        await send_room_state(lobby)
        if lobby.session.status != GameStatus.WAITING:
            await broadcast_to_lobby(lobby, {
                "type": "player_disconnected",
                "player_id": pid,
                "player_name": player.name,
                "grace_seconds": DISCONNECT_GRACE_SECONDS,
            })
            await send_game_state(lobby)
    else:
        await _force_disconnect_player(pid)


async def _process_heartbeats(now: float) -> None:
    """Jeden průchod kontroly heartbeatů a vypršených grace period."""
    stale = [
        pid for pid, last in list(player_last_activity.items())
        if now - last > WS_HEARTBEAT_TIMEOUT and pid in connected_clients
    ]
    for pid in stale:
        pname = player_registry.get(pid, {}).get("name", "?")
        logger.info("Heartbeat expired: player=%s (%s), handling disconnect", pid, pname)
        try:
            await _handle_connection_lost(pid)
        except Exception:
            logger.exception("Error in heartbeat disconnect for %s", pid)

    expired = [
        pid for pid, t in list(disconnected_at.items())
        if now - t > DISCONNECT_GRACE_SECONDS
    ]
    for pid in expired:
        if pid in connected_clients:
            # Hráč se mezitím vrátil, jen zapomenutý záznam
            disconnected_at.pop(pid, None)
            continue
        pname = player_registry.get(pid, {}).get("name", "?")
        logger.info("Reconnect grace expired: player=%s (%s), removing from game", pid, pname)
        try:
            await _force_disconnect_player(pid, reason="timeout")
        except Exception:
            logger.exception("Error in grace-expiry disconnect for %s", pid)


async def monitor_heartbeats():
    """Periodically check for players who stopped sending pings and
    handle their disconnect.  Also removes players whose reconnect grace
    period expired.  This runs independently of the per-connection
    receive loop and does not rely on WebSocket close detection."""
    while True:
        # Po sekundě, aby odpočet na návrat odpojeného hráče seděl
        await asyncio.sleep(1)
        await _process_heartbeats(time.time())


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    lobby_task = asyncio.create_task(cleanup_empty_lobbies())
    cleanup_task = asyncio.create_task(periodic_cleanup())
    heartbeat_task = asyncio.create_task(monitor_heartbeats())
    logger.info("Server started (log_level=%s, token_expiry=%ds)", LOG_LEVEL, TOKEN_EXPIRY_SECONDS)
    if not ADMIN_PASSWORD:
        logger.warning("ADMIN_PASSWORD není nastavené - admin režim Super Power je vypnutý")
    if "*" in ALLOWED_ORIGINS:
        logger.warning("ALLOWED_ORIGINS=* - WebSocket přijímá připojení z libovolného webu")
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
    # Aplikace nepoužívá cookies ani credentials; kombinace "*" origin
    # + allow_credentials=True je nebezpečný vzor
    allow_credentials=False,
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
        logger.warning(
            "Rejected WS: disallowed origin (ip=%s, origin=%s, host=%s) - nastav ALLOWED_ORIGINS",
            client_ip, websocket.headers.get("origin"), websocket.headers.get("host"),
        )
        await websocket.close(code=WS_CLOSE_ORIGIN_REJECTED)
        return

    if ip_connections[client_ip] >= MAX_CONNECTIONS_PER_IP:
        logger.warning("Rejected WS: connection limit for %s", client_ip)
        await websocket.close(code=WS_CLOSE_TOO_MANY_CONNECTIONS)
        return

    ip_connections[client_ip] += 1
    logger.info("WS connected (ip=%s, active=%d)", client_ip, ip_connections[client_ip])
    player_id: Optional[str] = None

    try:
        while True:
            raw = await websocket.receive_text()

            if player_id:
                active_ws = connected_clients.get(player_id)
                if active_ws is not websocket:
                    # Spojení nahradilo novější (reconnect z jiného okna), nebo ho
                    # server už uklidil - zprávy z něj se nesmí zpracovat
                    logger.info("Ignoring message from superseded connection: player=%s", player_id)
                    try:
                        await websocket.close(
                            code=WS_CLOSE_REPLACED if active_ws is not None else WS_CLOSE_CONNECTION_LOST
                        )
                    except Exception:
                        pass
                    break
                now = time.time()
                player_last_activity[player_id] = now
                info = player_registry.get(player_id)
                if info:
                    info["last_seen"] = now

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
                if player_id:
                    await websocket.send_json({"type": "error", "message": "Již jste přihlášeni"})
                    continue

                name = str(data.get("name", "")).strip()
                password = str(data.get("password", "")).strip()
                is_super_power = False

                if not name:
                    await websocket.send_json({"type": "error", "message": "Jméno je povinné"})
                    continue
                if len(name) > MAX_PLAYER_NAME_LENGTH:
                    await websocket.send_json({"type": "error", "message": f"Jméno je příliš dlouhé (max {MAX_PLAYER_NAME_LENGTH} znaků)"})
                    continue
                if _has_forbidden_chars(name):
                    await websocket.send_json({"type": "error", "message": "Jméno obsahuje nepovolené znaky"})
                    continue

                if password:
                    if not ADMIN_PASSWORD:
                        logger.warning("Admin login attempt, but admin is disabled (ip=%s)", client_ip)
                        await websocket.send_json({"type": "error", "message": "Admin režim není na tomto serveru zapnutý"})
                        continue
                    lockout = admin_login_throttle.lockout_remaining(client_ip)
                    if lockout > 0:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Příliš mnoho neúspěšných pokusů, zkus to znovu za {math.ceil(lockout / 60)} min",
                        })
                        continue
                    if not secrets.compare_digest(password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8")):
                        admin_login_throttle.register_failure(client_ip)
                        logger.warning("Invalid admin password attempt (ip=%s)", client_ip)
                        await websocket.send_json({"type": "error", "message": "Nesprávné heslo"})
                        continue
                    admin_login_throttle.reset(client_ip)
                    is_super_power = True

                # Jméno drží jen aktivní hráči - opuštěnou registraci (bez spojení
                # a mimo místnost) může převzít nový hráč
                name_owner = next(
                    (pid for pid, i in player_registry.items() if i["name"].lower() == name.lower()),
                    None,
                )
                if name_owner:
                    if _is_stale_registration(name_owner, player_registry[name_owner]):
                        _drop_registration(name_owner)
                    else:
                        await websocket.send_json({"type": "error", "message": "Jméno je již obsazené"})
                        continue

                ip_registrations = sum(1 for i in player_registry.values() if i.get("ip") == client_ip)
                if (ip_registrations >= MAX_REGISTRATIONS_PER_IP
                        and not _evict_oldest_stale_registration(ip=client_ip)):
                    await websocket.send_json({"type": "error", "message": "Z této adresy je přihlášeno příliš mnoho hráčů"})
                    continue
                if (len(player_registry) >= MAX_REGISTERED_PLAYERS
                        and not _evict_oldest_stale_registration()):
                    await websocket.send_json({"type": "error", "message": "Server je plný, zkuste to později"})
                    continue

                now = time.time()
                player_id = str(uuid.uuid4())
                new_token = str(uuid.uuid4())
                player_registry[player_id] = {
                    "name": name,
                    "token": new_token,
                    "is_super_power": is_super_power,
                    "token_created_at": now,
                    "last_seen": now,
                    "lobby_id": None,
                    "ip": client_ip,
                }
                token_map[new_token] = player_id
                connected_clients[player_id] = websocket
                player_last_activity[player_id] = now
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
                    await websocket.send_json({"type": "error", "code": ERR_TOKEN_REQUIRED, "message": "Token je povinný"})
                    continue

                rec_pid = token_map.get(rec_token)
                if not rec_pid or rec_pid not in player_registry:
                    await websocket.send_json({"type": "error", "code": ERR_INVALID_TOKEN, "message": "Neplatný token"})
                    continue

                if player_id and player_id != rec_pid:
                    await websocket.send_json({"type": "error", "message": "Již jste přihlášeni"})
                    continue

                info = player_registry[rec_pid]
                if _is_token_expired(info):
                    await websocket.send_json({"type": "error", "code": ERR_TOKEN_EXPIRED, "message": "Token vypršel, přihlaš se znovu"})
                    continue

                old_ws = connected_clients.get(rec_pid)
                if data.get("resume") is True and old_ws is not None and old_ws is not websocket:
                    # Obnovení po restartu prohlížeče, ale hráč je aktivní v jiném
                    # okně - bez výslovného souhlasu ho nepřebírat
                    await websocket.send_json({
                        "type": "error",
                        "code": ERR_SESSION_ACTIVE,
                        "message": "Tvoje hra je otevřená v jiném okně",
                        "player_name": info["name"],
                    })
                    continue

                player_id = rec_pid
                connected_clients[player_id] = websocket
                if old_ws is not None and old_ws is not websocket:
                    # Hráče nesmí ovládat dvě spojení najednou - starší se zavře
                    # (klient podle kódu pozná, že se nemá znovu připojovat)
                    logger.info("Closing superseded connection of player %s", player_id)
                    try:
                        await old_ws.close(code=WS_CLOSE_REPLACED)
                    except Exception:
                        pass

                now = time.time()
                player_last_activity[player_id] = now
                disconnected_at.pop(player_id, None)
                info.pop("disconnected_at", None)
                info["last_seen"] = now
                info["ip"] = client_ip
                logger.info("Player reconnected: %s (id=%s)", info["name"], player_id)

                await websocket.send_json({
                    "type": "reconnect_ok",
                    "player_id": player_id,
                    "is_super_power": info.get("is_super_power", False),
                })

                lobby = _get_player_lobby(player_id)
                rec_player = lobby.session.get_player(player_id) if lobby else None
                if lobby and rec_player:
                    was_disconnected = not rec_player.connected
                    rec_player.connected = True
                    if was_disconnected and lobby.session.status != GameStatus.WAITING:
                        await broadcast_to_lobby(lobby, {
                            "type": "player_reconnected",
                            "player_id": player_id,
                            "player_name": rec_player.name,
                        })
                    await websocket.send_json({
                        "type": "lobby_joined",
                        "lobby_id": lobby.lobby_id,
                        "lobby_name": lobby.name,
                    })
                    if lobby.session.status == GameStatus.WAITING:
                        await send_room_state(lobby)
                    else:
                        # Běžící i dohraná hra - klient zobrazí herní obrazovku
                        # (u dohrané s tlačítky "Začít novou hru" / "Zpět")
                        await send_game_state(lobby)
                else:
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

                lobby_name = str(data.get("name", "")).strip()[:MAX_LOBBY_NAME_LENGTH].strip()
                if _has_forbidden_chars(lobby_name):
                    await websocket.send_json({"type": "error", "message": "Název místnosti obsahuje nepovolené znaky"})
                    continue
                if not lobby_name:
                    lobby_name = _default_lobby_name()

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
                if not isinstance(target_lid, str) or target_lid not in lobbies:
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
                    removed = _remove_player_from_lobby(player_id, lobby)
                    if info:
                        info["lobby_id"] = None

                    await websocket.send_json({"type": "lobby_left"})
                    await _notify_player_left(lobby, removed, "left")
                    await _after_player_left(lobby)
                    await broadcast_lobby_list()
                else:
                    await websocket.send_json({"type": "lobby_left"})

            # ==============================================================
            # LOGOUT (disconnect completely)
            # ==============================================================
            elif msg_type == "logout":
                if player_id:
                    lobby = _get_player_lobby(player_id)
                    _drop_registration(player_id)
                    connected_clients.pop(player_id, None)
                    player_last_activity.pop(player_id, None)
                    if lobby:
                        removed = _remove_player_from_lobby(player_id, lobby)
                        await _notify_player_left(lobby, removed, "left")
                        await _after_player_left(lobby)
                    await broadcast_lobby_list()

                await websocket.send_json({"type": "leave_ok"})
                player_id = None
                # Řádné zavření - klient pak nehlásí chybu připojení
                try:
                    await websocket.close(code=1000)
                except Exception:
                    pass
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

                if lobby.session.status != GameStatus.WAITING:
                    await websocket.send_json({"type": "error", "message": "Hra už probíhá"})
                    continue

                player.ready = bool(data.get("ready", False))
                _touch_lobby(lobby)
                await send_room_state(lobby)
                await _maybe_start_game(lobby)

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
                if not isinstance(card_id, str) or (target_pid is not None and not isinstance(target_pid, str)):
                    await websocket.send_json({"type": "error", "message": "Chybná data karty"})
                    continue

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
                    continue

                played_msg = {
                    "type": "card_played",
                    "player_id": player_id,
                    "player_name": player.name,
                    "card_type": result.get("card_type"),
                    "result": _public_play_result(result),
                    "can_nope": session.last_action_for_nope is not None,
                }
                favor_target = session.get_player(result["target_player_id"]) if result.get("target_player_id") else None
                if favor_target:
                    played_msg["target_player_name"] = favor_target.name
                await broadcast_to_lobby(lobby, played_msg)

                # Soukromé výsledky jen dotčeným hráčům
                if "see_future_cards" in result:
                    await send_to_player(player_id, {"type": "see_future", "cards": result["see_future_cards"]})
                if result.get("favor_card") and favor_target:
                    card_title = result["favor_card"]["title"]
                    await send_to_player(player_id, {
                        "type": "favor_card_received",
                        "from_player_name": favor_target.name,
                        "card_title": card_title,
                    })
                    await send_to_player(favor_target.player_id, {
                        "type": "favor_card_taken",
                        "from_player_name": player.name,
                        "card_title": card_title,
                    })

                if result.get("action_cancelled"):
                    # Nené vrací tah hráči, jehož akce byla zrušena
                    return_pid = result.get("return_turn_to")
                    rp = session.get_player(return_pid) if return_pid else None
                    if rp and rp.alive:
                        session.current_player_id = return_pid
                        if session.pending_turns.get(return_pid, 0) <= 0:
                            session.pending_turns[return_pid] = 1
                        logger.debug("NOPE: turn returned to %s", rp.name)
                elif result.get("end_turn"):
                    end_turn(session, force=result.get("force_end_turn", False))

                if await _announce_game_end_if_over(lobby):
                    await broadcast_lobby_list()
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
                draw_result = draw_card(session, player)

                if draw_result.get("empty"):
                    # Podle pravidel se balíček nikdy nevyčerpá; kdyby přesto,
                    # nesmí se to tvářit jako zneškodnění koťátka.
                    await websocket.send_json({"type": "error", "message": "Balíček je prázdný"})
                elif draw_result.get("exploded"):
                    await broadcast_to_lobby(lobby, {
                        "type": "player_died",
                        "player_id": player_id,
                        "player_name": player.name,
                    })
                    if await _announce_game_end_if_over(lobby):
                        await broadcast_lobby_list()
                    else:
                        end_turn(session)
                    await send_game_state(lobby)
                else:
                    if draw_result.get("defused"):
                        await broadcast_to_lobby(lobby, {
                            "type": "exploding_kitten_defused",
                            "player_id": player_id,
                            "player_name": player.name,
                        })
                    else:
                        await websocket.send_json({"type": "card_drawn", "card": draw_result["card"].to_dict()})
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

                if lobby.session.status != GameStatus.FINISHED:
                    await websocket.send_json({"type": "error", "message": "Novou hru lze začít až po skončení té současné"})
                    continue

                _touch_lobby(lobby)
                logger.info("Game restart in lobby %s by %s", lobby.lobby_id, player_id)

                lobby.session.status = GameStatus.WAITING
                for p in lobby.session.players:
                    p.ready = False
                    p.alive = True
                    p.hand = []
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
                target = lobby.session.get_player(target_pid) if isinstance(target_pid, str) else None
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

                await send_to_player(target_pid, {
                    "type": "you_were_removed",
                    "message": "Byli jste odebráni z místnosti administrátorem",
                })
                await broadcast_to_lobby(lobby, {
                    "type": "player_removed",
                    "player_id": target_pid,
                    "player_name": target.name,
                })
                await _after_player_left(lobby)
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

                # Vítěz jen pokud opravdu zbyl jediný živý hráč - jinak hra
                # končí bez vítěze (nevybírá se náhodně první v seznamu)
                alive = lobby.session.get_alive_players()
                winner = alive[0] if len(alive) == 1 else None
                lobby.session.status = GameStatus.FINISHED
                lobby.session.last_action_for_nope = None
                for p in lobby.session.players:
                    p.ready = False

                logger.info("Game in lobby %s ended by admin %s", lobby.lobby_id, player_id)
                await broadcast_to_lobby(lobby, {
                    "type": "game_end",
                    "winner_id": winner.player_id if winner else None,
                    "winner_name": winner.name if winner else None,
                    "ended_by_admin": True,
                })
                await send_game_state(lobby)
                await broadcast_lobby_list()

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
                if not isinstance(target_lid, str) or target_lid not in lobbies:
                    await websocket.send_json({"type": "error", "message": "Místnost neexistuje"})
                    continue

                lobby = lobbies[target_lid]
                for p in list(lobby.session.players):
                    disconnected_at.pop(p.player_id, None)
                    pinfo = player_registry.get(p.player_id)
                    if pinfo:
                        pinfo["lobby_id"] = None
                    await send_to_player(p.player_id, {
                        "type": "you_were_removed",
                        "message": "Místnost byla smazána administrátorem",
                    })

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
                logger.info("Finally cleanup: handling connection lost for player=%s", player_id)
                try:
                    await _handle_connection_lost(player_id)
                except Exception as cleanup_err:
                    logger.error("Error in _handle_connection_lost: %s", cleanup_err, exc_info=True)
            else:
                already_gone = current_ws is None
                logger.info(
                    "Finally cleanup: player=%s already handled (ws_gone=%s)",
                    player_id, already_gone,
                )
                # Aktivitu mažeme jen když hráč nemá jiné (novější) spojení
                if already_gone:
                    player_last_activity.pop(player_id, None)
