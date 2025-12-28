import json
import uuid
import time
import asyncio
from typing import Dict, Set, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app.models import GameSession, Player, GameStatus
from app.game_logic import initialize_game, draw_card, play_card, end_turn, check_game_end

app = FastAPI(title="Výbušná koťátka")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Globální herní session (v RAM)
game_session = GameSession()
connected_clients: Dict[str, WebSocket] = {}
player_tokens: Dict[str, str] = {}  # player_id -> token


async def broadcast_to_all(message: dict):
    """Pošle zprávu všem připojeným klientům"""
    disconnected = []
    for player_id, ws in connected_clients.items():
        try:
            await ws.send_json(message)
        except:
            disconnected.append(player_id)
    
    for player_id in disconnected:
        connected_clients.pop(player_id, None)


async def send_lobby_state(target_player_id: Optional[str] = None):
    """Pošle aktuální stav lobby
    Pokud je hra ve stavu PLAYING nebo FINISHED, pošle zprávu pouze hráčům, kteří nejsou ve hře (nejsou alive),
    nebo pouze konkrétnímu hráči, pokud je zadán target_player_id.
    Jinak pošle všem."""
    # Hra může začít pouze pokud je ve stavu WAITING a všichni jsou připraveni
    can_start = (
        game_session.status == GameStatus.WAITING and
        len(game_session.players) >= 2 and
        len(game_session.players) <= 5 and
        all(p.ready for p in game_session.players) and
        len(game_session.players) == len([p for p in game_session.players if p.ready])
    )
    
    message = {
        "type": "lobby_state",
        "status": game_session.status.value,
        "players": [p.to_dict(hide_hand=True) for p in game_session.players],
        "can_start": can_start
    }
    
    # Pokud je hra ve stavu PLAYING nebo FINISHED, pošleme pouze hráčům, kteří nejsou ve hře
    if game_session.status == GameStatus.PLAYING or game_session.status == GameStatus.FINISHED:
        if target_player_id:
            # Pošleme pouze konkrétnímu hráči
            if target_player_id in connected_clients:
                try:
                    await connected_clients[target_player_id].send_json(message)
                except:
                    pass
        else:
            # Pošleme pouze hráčům, kteří nejsou ve hře (nejsou alive)
            for player_id, ws in connected_clients.items():
                player = game_session.get_player(player_id)
                if player and not player.alive:
                    try:
                        await ws.send_json(message)
                    except:
                        pass
    else:
        # Pokud hra neprobíhá, pošleme všem
        await broadcast_to_all(message)


async def send_game_state():
    """Pošle aktuální herní stav všem hráčům, kteří skutečně hrají (mají karty v ruce)"""
    alive_players = game_session.get_alive_players()
    
    # Pošleme každému hráči jeho vlastní stav s kartami
    # Ale pouze hráčům, kteří skutečně hrají (mají karty v ruce) NEBO jsou mrtví (aby viděli, že jsou mrtví)
    for player in game_session.players:
        # Hráč hraje pouze pokud má karty v ruce NEBO je mrtvý (aby viděl svůj stav)
        if (not player.hand or len(player.hand) == 0) and player.alive:
            continue  # Přeskočíme hráče, kteří nemají karty a jsou živí (noví hráči v lobby)
        
        if player.player_id in connected_clients:
            ws = connected_clients[player.player_id]
            try:
                # Vytvoříme stav s vlastními kartami viditelnými
                game_state = {
                    "type": "game_state",
                    "status": game_session.status.value,
                    "current_player_id": game_session.current_player_id,
                    "pending_turns": game_session.pending_turns.copy(),
                    "draw_pile_size": len(game_session.draw_pile),
                    "discard_pile_size": len(game_session.discard_pile),
                    "reverse_direction": game_session.reverse_direction,
                    "can_nope": game_session.last_action_for_nope is not None,  # Informace, jestli lze použít NOPE
                    "players": []
                }
                
                # Pro ostatní hráče skryjeme karty
                # DŮLEŽITÉ: Zahrneme hráče, kteří skutečně hrají (mají karty v ruce) NEBO jsou mrtví
                for p in game_session.players:
                    # Přeskočíme hráče, kteří nemají karty a jsou živí (noví hráči v lobby)
                    if (not p.hand or len(p.hand) == 0) and p.alive:
                        continue
                    
                    if p.player_id == player.player_id:
                        player_dict = p.to_dict(hide_hand=False)
                        # Debug: zkontrolujeme, že ruka obsahuje správný počet karet
                        print(f"DEBUG send_game_state: Hráč {p.name} ({p.player_id}) má {len(p.hand)} karet v ruce, alive={p.alive}, serializováno {len(player_dict.get('hand', []))} karet")
                        game_state["players"].append(player_dict)
                    else:
                        game_state["players"].append(p.to_dict(hide_hand=True))
                
                await ws.send_json(game_state)
            except:
                pass


@app.get("/")
async def get_index():
    """Vrátí hlavní HTML stránku"""
    try:
        return FileResponse("static/index.html")
    except:
        return HTMLResponse("<h1>Chyba: Soubor index.html nenalezen</h1>")

@app.get("/super_power")
async def get_super_power():
    """Vrátí super power HTML stránku"""
    try:
        return FileResponse("static/super_power.html")
    except:
        return HTMLResponse("<h1>Chyba: Soubor super_power.html nenalezen</h1>")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"DEBUG: WebSocket připojen z {websocket.client}")
    player_id = None
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            print(f"DEBUG: Přijata zpráva typu: {msg_type}, data: {data}")
            
            if msg_type == "join":
                name = data.get("name", "").strip()
                password = data.get("password", "").strip()
                is_super_power = False
                
                print(f"DEBUG: Zpracovávám join zprávu, jméno: '{name}', password: {'***' if password else 'není'}")
                print(f"DEBUG: Aktuální status hry: {game_session.status}")
                print(f"DEBUG: Počet hráčů v lobby: {len(game_session.players)}")
                
                if not name:
                    print(f"DEBUG: Jméno je prázdné, odmítám join")
                    await websocket.send_json({"type": "error", "message": "Jméno je povinné"})
                    continue
                
                # Kontrola hesla pro super_power režim
                if password:
                    if password != "TajneHeslo":
                        print(f"DEBUG: Nesprávné heslo")
                        await websocket.send_json({"type": "error", "message": "Nesprávné heslo"})
                        continue
                    is_super_power = True
                
                if len(game_session.players) >= 5:
                    print(f"DEBUG: Lobby je plné, odmítám join")
                    await websocket.send_json({"type": "error", "message": "Lobby je plné (max 5 hráčů)"})
                    continue
                
                # Zkontrolujeme, jestli už není hráč s tímto jménem
                existing_names = [p.name.lower() for p in game_session.players]
                if name.lower() in existing_names:
                    print(f"DEBUG: Jméno '{name}' je již obsazené (existující: {existing_names}), odmítám join")
                    await websocket.send_json({"type": "error", "message": "Jméno je již obsazené"})
                    continue
                
                # Vytvoříme nového hráče
                player_id = str(uuid.uuid4())
                token = str(uuid.uuid4())
                player = Player(player_id=player_id, name=name, token=token, is_super_power=is_super_power)
                
                # Pokud hra probíhá nebo skončila, nový hráč není součástí hry
                if game_session.status == GameStatus.PLAYING or game_session.status == GameStatus.FINISHED:
                    player.alive = False  # Nový hráč není ve hře
                
                game_session.players.append(player)
                connected_clients[player_id] = websocket
                player_tokens[player_id] = token
                
                print(f"DEBUG: Vytvořen nový hráč: {name} (ID: {player_id})")
                print(f"DEBUG: Posílám join_ok zprávu")
                
                await websocket.send_json({
                    "type": "join_ok",
                    "player_id": player_id,
                    "token": token,
                    "is_super_power": is_super_power
                })
                
                print(f"DEBUG: Volám send_lobby_state() pro nového hráče {player_id}")
                # Pošleme lobby_state pouze nově připojenému hráči
                await send_lobby_state(target_player_id=player_id)
                print(f"DEBUG: Join dokončen úspěšně")
            
            elif msg_type == "reconnect":
                token = data.get("token")
                if not token:
                    await websocket.send_json({"type": "error", "message": "Token je povinný"})
                    continue
                
                # Najdeme hráče podle tokenu
                player = None
                for p in game_session.players:
                    if p.token == token:
                        player = p
                        player_id = p.player_id
                        break
                
                if not player:
                    await websocket.send_json({"type": "error", "message": "Neplatný token"})
                    continue
                
                connected_clients[player_id] = websocket
                await websocket.send_json({
                    "type": "reconnect_ok",
                    "player_id": player_id
                })
                
                # Pokud hra probíhá, zkontrolujeme, zda hráč skutečně hraje (má karty v ruce)
                if game_session.status == GameStatus.PLAYING:
                    # Hráč hraje pouze pokud má karty v ruce
                    if player.hand and len(player.hand) > 0:
                        await send_game_state()
                    else:
                        # Hráč nemá karty - je to nový hráč, který se připojil během hry
                        await send_lobby_state(target_player_id=player_id)
                else:
                    await send_lobby_state()
            
            elif msg_type == "set_ready":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue
                
                player = game_session.get_player(player_id)
                if not player:
                    await websocket.send_json({"type": "error", "message": "Hráč nenalezen"})
                    continue
                
                ready = data.get("ready", False)
                player.ready = ready
                
                await send_lobby_state()
                
                # Zkontrolujeme, jestli můžeme začít hru
                if (
                    game_session.status == GameStatus.WAITING and
                    len(game_session.players) >= 2 and
                    len(game_session.players) <= 5 and
                    all(p.ready for p in game_session.players)
                ):
                    initialize_game(game_session)
                    await send_game_state()
            
            elif msg_type == "play_card":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue
                
                if game_session.status != GameStatus.PLAYING:
                    await websocket.send_json({"type": "error", "message": "Hra neprobíhá"})
                    continue
                
                player = game_session.get_player(player_id)
                if not player or not player.alive:
                    await websocket.send_json({"type": "error", "message": "Hráč není aktivní"})
                    continue
                
                card_id = data.get("card_id")
                target_player_id = data.get("target_player_id")
                
                # Zkontrolujeme, jestli hráč hraje NOPE kartu
                # NOPE může být zahraná i když hráč není na tahu, ale pouze pokud existuje akce k zrušení
                card_in_hand = None
                for card in player.hand:
                    if card.id == card_id:
                        card_in_hand = card
                        break
                
                if not card_in_hand:
                    await websocket.send_json({"type": "error", "message": "Karta není v ruce"})
                    continue
                
                # Pokud hráč není na tahu, povolíme pouze NOPE kartu (a pouze pokud existuje akce k zrušení)
                if game_session.current_player_id != player_id:
                    if card_in_hand.type.value != "NOPE":
                        await websocket.send_json({"type": "error", "message": "Není váš tah"})
                        continue
                    # Pro NOPE zkontrolujeme, jestli existuje akce k zrušení
                    if not game_session.last_action_for_nope:
                        await websocket.send_json({"type": "error", "message": "Není žádná akce k zrušení"})
                        continue
                
                result = play_card(game_session, player, card_id, target_player_id)
                
                if "error" in result:
                    await websocket.send_json({"type": "error", "message": result["error"]})
                else:
                    # Pošleme výsledek všem (nejdřív zpráva o zahrané kartě)
                    await broadcast_to_all({
                        "type": "card_played",
                        "player_id": player_id,
                        "player_name": player.name,
                        "card_type": result.get("card_type"),
                        "result": result,
                        "can_nope": game_session.last_action_for_nope is not None  # Informace, jestli lze použít NOPE
                    })
                    
                    # Pokud je to FAVOR a máme favor_card, pošleme speciální zprávu cílovému hráči (po zprávě o zahrané kartě)
                    if result.get("card_type") == "FAVOR" and result.get("favor_card"):
                        target_player_id = result.get("target_player_id")
                        if target_player_id and target_player_id in connected_clients:
                            # Malé zpoždění, aby se zpráva zobrazila po zprávě o zahrané kartě
                            await asyncio.sleep(0.1)
                            await connected_clients[target_player_id].send_json({
                                "type": "favor_card_taken",
                                "from_player_name": player.name,
                                "card_title": result["favor_card"]["title"]
                            })
                        
                        # Zkontrolujeme, jestli cílový hráč zemřel (ztratil všechny karty)
                        target_player = game_session.get_player(target_player_id)
                        if target_player and not target_player.alive:
                            # Hráč zemřel - pošleme zprávu všem
                            await broadcast_to_all({
                                "type": "player_died",
                                "player_id": target_player_id,
                                "player_name": target_player.name
                            })
                            
                            # Zkontrolujeme konec hry
                            winner = check_game_end(game_session)
                            if winner:
                                await broadcast_to_all({
                                    "type": "game_end",
                                    "winner_id": winner.player_id,
                                    "winner_name": winner.name
                                })
                                game_session.status = GameStatus.FINISHED
                                for p in game_session.players:
                                    p.ready = False
                    
                    # Pokud je to NOPE a akce byla zrušena, vrátíme tah na hráče, který kartu zahrál
                    if result.get("action_cancelled") and result.get("return_turn_to"):
                        return_player_id = result.get("return_turn_to")
                        return_player = game_session.get_player(return_player_id)
                        if return_player and return_player.alive:
                            # Vrátíme tah na hráče, který kartu zahrál
                            game_session.current_player_id = return_player_id
                            # Nastavíme pending_turns na 1, pokud ještě nemá
                            if return_player_id not in game_session.pending_turns:
                                game_session.pending_turns[return_player_id] = 1
                            print(f"DEBUG NOPE: Vrácen tah hráči {return_player.name}")
                    
                    # Pokud karta ukončila tah, přejdeme na dalšího hráče
                    elif result.get("end_turn"):
                        # Pokud je force_end_turn (např. ATTACK), ukončíme tah bez ohledu na pending_turns
                        force_end = result.get("force_end_turn", False)
                        end_turn(game_session, force=force_end)
                    
                    # Zkontrolujeme konec hry
                    winner = check_game_end(game_session)
                    if winner:
                        await broadcast_to_all({
                            "type": "game_end",
                            "winner_id": winner.player_id,
                            "winner_name": winner.name
                        })
                        game_session.status = GameStatus.FINISHED
                        # Reset ready stavu
                        for p in game_session.players:
                            p.ready = False
                        await send_game_state()
                    else:
                        await send_game_state()
            
            elif msg_type == "draw_card":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue
                
                if game_session.status != GameStatus.PLAYING:
                    await websocket.send_json({"type": "error", "message": "Hra neprobíhá"})
                    continue
                
                if game_session.current_player_id != player_id:
                    await websocket.send_json({"type": "error", "message": "Není váš tah"})
                    continue
                
                player = game_session.get_player(player_id)
                if not player or not player.alive:
                    await websocket.send_json({"type": "error", "message": "Hráč není aktivní"})
                    continue
                
                card = draw_card(game_session, player)
                
                if card and card.type.value == "EXPLODING_KITTEN":
                    # Hráč dostal výbušné koťátko a nemá Zneškodni - umřel
                    # Pošleme jen zprávu o smrti (ne duplicitní zprávu o líznutí)
                    await broadcast_to_all({
                        "type": "player_died",
                        "player_id": player_id,
                        "player_name": player.name
                    })
                    
                    # Zkontrolujeme konec hry (po smrti hráče)
                    winner = check_game_end(game_session)
                    if winner:
                        await broadcast_to_all({
                            "type": "game_end",
                            "winner_id": winner.player_id,
                            "winner_name": winner.name
                        })
                        game_session.status = GameStatus.FINISHED
                        for p in game_session.players:
                            p.ready = False
                        await send_game_state()
                    else:
                        # Pokud hra pokračuje, přejdeme na dalšího hráče
                        end_turn(game_session)
                        # Zkontrolujeme znovu konec hry (po přepnutí hráče)
                        winner = check_game_end(game_session)
                        if winner:
                            await broadcast_to_all({
                                "type": "game_end",
                                "winner_id": winner.player_id,
                                "winner_name": winner.name
                            })
                            game_session.status = GameStatus.FINISHED
                            for p in game_session.players:
                                p.ready = False
                        await send_game_state()
                else:
                    # Normální karta nebo přežil EK s DEFUSE
                    if card:
                        await websocket.send_json({
                            "type": "card_drawn",
                            "card": card.to_dict()
                        })
                    else:
                        # Přežil výbušné koťátko - zobrazíme všem (jedna zpráva pro všechny)
                        await broadcast_to_all({
                            "type": "exploding_kitten_defused",
                            "player_id": player_id,
                            "player_name": player.name
                        })
                    
                    end_turn(game_session)
                    await send_game_state()
            
            elif msg_type == "end_turn":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue
                
                if game_session.status != GameStatus.PLAYING:
                    await websocket.send_json({"type": "error", "message": "Hra neprobíhá"})
                    continue
                
                if game_session.current_player_id != player_id:
                    await websocket.send_json({"type": "error", "message": "Není váš tah"})
                    continue
                
                end_turn(game_session)
                await send_game_state()
            
            elif msg_type == "restart_game":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue
                
                print(f"DEBUG: Restart hry požadován hráčem {player_id}, aktuální status: {game_session.status}")
                
                # Povolíme restart vždy (i když hra neskončila nebo je ve stavu WAITING)
                # Reset hry - resetujeme všechny stavy
                game_session.status = GameStatus.WAITING
                # Všichni hráči musí být ready=false pro novou hru
                for p in game_session.players:
                    p.ready = False
                    p.alive = True
                
                # Vymažeme všechny hry související stavy
                game_session.draw_pile = []
                game_session.discard_pile = []
                game_session.pending_turns = {}
                game_session.last_action_for_nope = None
                game_session.peeked_cards = []
                game_session.current_player_id = None
                
                # Pošleme lobby_state (protože status je WAITING)
                await send_lobby_state()
                print(f"DEBUG: Restart hry dokončen, nový status: {game_session.status}")
            
            elif msg_type == "leave_lobby":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue
                
                # Odstraníme hráče z lobby
                game_session.players = [p for p in game_session.players if p.player_id != player_id]
                connected_clients.pop(player_id, None)
                player_tokens.pop(player_id, None)
                
                await websocket.send_json({"type": "leave_ok"})
                await send_lobby_state()
                break  # Ukončíme WebSocket spojení
            
            elif msg_type == "remove_player":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue
                
                player = game_session.get_player(player_id)
                if not player or not player.is_super_power:
                    await websocket.send_json({"type": "error", "message": "Nemáte oprávnění"})
                    continue
                
                target_player_id = data.get("target_player_id")
                if not target_player_id:
                    await websocket.send_json({"type": "error", "message": "Cílový hráč není zadán"})
                    continue
                
                target_player = game_session.get_player(target_player_id)
                if not target_player:
                    await websocket.send_json({"type": "error", "message": "Hráč nenalezen"})
                    continue
                
                # Super_power uživatelé nemohou být odstraněni
                if target_player.is_super_power:
                    await websocket.send_json({"type": "error", "message": "Super_power uživatelé nemohou být odstraněni"})
                    continue
                
                # Odstraníme hráče z lobby
                game_session.players = [p for p in game_session.players if p.player_id != target_player_id]
                player_tokens.pop(target_player_id, None)
                
                # Pokud hráč měl aktivní WebSocket, pošleme mu zprávu a zavřeme ho
                if target_player_id in connected_clients:
                    try:
                        await connected_clients[target_player_id].send_json({
                            "type": "you_were_removed",
                            "message": "Byli jste odebráni z lobby administrátorem"
                        })
                        await connected_clients[target_player_id].close()
                    except:
                        pass
                connected_clients.pop(target_player_id, None)
                
                await broadcast_to_all({
                    "type": "player_removed",
                    "player_id": target_player_id,
                    "player_name": target_player.name
                })
                
                await send_lobby_state()
            
            elif msg_type == "view_deck":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue
                
                player = game_session.get_player(player_id)
                if not player or not player.is_super_power:
                    await websocket.send_json({"type": "error", "message": "Nemáte oprávnění"})
                    continue
                
                if game_session.status != GameStatus.PLAYING:
                    await websocket.send_json({"type": "error", "message": "Hra neprobíhá"})
                    continue
                
                # Pošleme všechny karty z dobíracího balíčku
                deck_cards = [card.to_dict() for card in game_session.draw_pile]
                await websocket.send_json({
                    "type": "deck_view",
                    "cards": deck_cards,
                    "count": len(deck_cards)
                })
            
            elif msg_type == "end_game":
                if not player_id:
                    await websocket.send_json({"type": "error", "message": "Nejste přihlášeni"})
                    continue
                
                player = game_session.get_player(player_id)
                if not player or not player.is_super_power:
                    await websocket.send_json({"type": "error", "message": "Nemáte oprávnění"})
                    continue
                
                if game_session.status != GameStatus.PLAYING:
                    await websocket.send_json({"type": "error", "message": "Hra neprobíhá"})
                    continue
                
                # Ukončíme hru - najdeme vítěze (prvního živého hráče)
                alive_players = game_session.get_alive_players()
                winner = alive_players[0] if alive_players else None
                
                game_session.status = GameStatus.FINISHED
                for p in game_session.players:
                    p.ready = False
                
                if winner:
                    await broadcast_to_all({
                        "type": "game_end",
                        "winner_id": winner.player_id,
                        "winner_name": winner.name,
                        "ended_by_admin": True
                    })
                else:
                    await broadcast_to_all({
                        "type": "game_end",
                        "winner_id": None,
                        "winner_name": None,
                        "ended_by_admin": True
                    })
                
                await send_game_state()
            
            else:
                await websocket.send_json({"type": "error", "message": f"Neznámý typ zprávy: {msg_type}"})
    
    except WebSocketDisconnect:
        print(f"DEBUG: WebSocket disconnect pro hráče {player_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if player_id:
            connected_clients.pop(player_id, None)
            # Pokud hráč není připojený (WebSocket se zavřel), odstraníme ho z lobby
            # Ale pouze pokud hra neprobíhá (aby se neodstranil hráč během hry)
            if game_session.status == GameStatus.WAITING:
                # Zkontrolujeme, jestli hráč má aktivní WebSocket připojení
                if player_id not in connected_clients:
                    print(f"DEBUG: Odstraňuji hráče {player_id} z lobby (WebSocket zavřen, hra neprobíhá)")
                    game_session.players = [p for p in game_session.players if p.player_id != player_id]
                    player_tokens.pop(player_id, None)
                    # Pošleme aktualizovaný stav lobby
                    asyncio.create_task(send_lobby_state())
            # Pokud hra probíhá, hráče neodstraňujeme (může se znovu připojit pomocí reconnect)


# Auto-reset lobby po 60 sekundách, pokud je prázdná
async def auto_reset_lobby():
    """Automaticky resetuje lobby, pokud je prázdná 60 sekund"""
    while True:
        await asyncio.sleep(10)  # Kontrolujeme každých 10 sekund
        if (
            game_session.status == GameStatus.WAITING and
            len(game_session.players) == 0 and
            time.time() - game_session.last_reset_time > 60
        ):
            game_session.last_reset_time = time.time()
            game_session.players = []
            game_session.draw_pile = []
            game_session.discard_pile = []
            game_session.current_player_id = None
            game_session.pending_turns = {}
            game_session.last_action_for_nope = None


@app.on_event("startup")
async def startup_event():
    """Spustí background task pro auto-reset"""
    asyncio.create_task(auto_reset_lobby())

