let ws = null;
let playerId = null;
let token = null;
let currentGameState = null;
let currentLobbyId = null;
let currentLobbyName = null;
let pingInterval = null;

const audioCache = {};
let audioUnlocked = false;

document.addEventListener('click', () => {
    if (!audioUnlocked) {
        audioUnlocked = true;
        const unlockAudio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBTQ=');
        unlockAudio.volume = 0.01;
        unlockAudio.play().catch(() => {});
    }
}, { once: true });

// =========================================================================
// Init
// =========================================================================
window.addEventListener('DOMContentLoaded', () => {
    const mainTitle = document.getElementById('main-title');
    if (mainTitle) {
        mainTitle.addEventListener('click', () => window.location.reload());
    }
});

window.addEventListener('load', () => {
    token = sessionStorage.getItem('token');
    playerId = sessionStorage.getItem('player_id');

    const savedName = sessionStorage.getItem('player_name');
    const nameInput = document.getElementById('player-name');
    if (savedName && nameInput) nameInput.value = savedName;

    const versionInfo = document.getElementById('version-info');
    if (versionInfo) {
        fetch('/static/version.json')
            .then(r => r.json())
            .then(d => { versionInfo.textContent = d.version || 'v.unknown'; })
            .catch(() => { versionInfo.textContent = 'v.unknown'; });
    }

    const joinBtn = document.getElementById('join-btn');
    if (joinBtn) {
        joinBtn.addEventListener('click', () => {
            const ni = document.getElementById('player-name');
            if (!ni) return;
            const name = ni.value.trim();
            if (!name) { showError('Zadej jméno'); return; }

            sessionStorage.setItem('player_name', name);
            window.pendingJoinName = name;

            const pwdInput = document.getElementById('player-password');
            if (pwdInput && pwdInput.value.trim()) {
                window.pendingJoinPassword = pwdInput.value.trim();
            }

            // Uživatel se chce přihlásit znovu – zahodit starou session (např. po restartu serveru)
            clearSession();
            if (ws) {
                ws.onclose = null;
                ws.close();
                ws = null;
            }
            connectWebSocket();
        });
    }

    if (token && playerId) connectWebSocket();
    initButtons();
});

document.getElementById('player-name')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') document.getElementById('join-btn')?.click();
});

// =========================================================================
// WebSocket
// =========================================================================
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = () => {
        if (pingInterval) clearInterval(pingInterval);
        pingInterval = setInterval(() => {
            if (ws?.readyState === WebSocket.OPEN) {
                try { ws.send(JSON.stringify({ type: 'ping' })); } catch (e) { /* ignore */ }
            }
        }, 15000);

        if (token) {
            ws.send(JSON.stringify({ type: 'reconnect', token }));
        } else if (window.pendingJoinName) {
            const msg = { type: 'join', name: window.pendingJoinName };
            if (window.pendingJoinPassword) msg.password = window.pendingJoinPassword;
            ws.send(JSON.stringify(msg));
            delete window.pendingJoinName;
            delete window.pendingJoinPassword;
        }
    };

    ws.onmessage = (event) => {
        try { handleMessage(JSON.parse(event.data)); } catch (e) { console.error('Parse error:', e); }
    };

    ws.onerror = () => showError('Chyba připojení');

    ws.onclose = (event) => {
        if (pingInterval) { clearInterval(pingInterval); pingInterval = null; }
        if (event.code === 4003 || event.code === 4029) {
            showError(event.code === 4029 ? 'Příliš mnoho připojení' : 'Připojení odmítnuto');
            return;
        }
        if (token) setTimeout(() => { if (token) connectWebSocket(); }, 1000);
    };
}

// =========================================================================
// Message handler
// =========================================================================
function handleMessage(message) {
    if (message.type === 'pong') return;
    switch (message.type) {
        case 'join_ok':
            playerId = message.player_id;
            token = message.token;
            sessionStorage.setItem('player_id', playerId);
            sessionStorage.setItem('token', token);
            if (message.is_super_power) {
                sessionStorage.setItem('is_super_power', 'true');
            } else {
                sessionStorage.removeItem('is_super_power');
            }
            showScreen('lobby-browser-screen');
            break;

        case 'reconnect_ok':
            playerId = message.player_id;
            if (message.is_super_power) {
                sessionStorage.setItem('is_super_power', 'true');
            }
            break;

        case 'lobby_list':
            updateLobbyBrowser(message.lobbies || []);
            if (!currentLobbyId) showScreen('lobby-browser-screen');
            break;

        case 'lobby_joined':
            currentLobbyId = message.lobby_id;
            currentLobbyName = message.lobby_name;
            const roomTitle = document.getElementById('room-title');
            if (roomTitle) roomTitle.textContent = message.lobby_name;
            showScreen('lobby-screen');
            const msgs = document.getElementById('game-messages');
            if (msgs) msgs.innerHTML = '';
            break;

        case 'lobby_left':
            currentLobbyId = null;
            currentLobbyName = null;
            showScreen('lobby-browser-screen');
            break;

        case 'error':
            showError(message.message || 'Nastala chyba');
            if (token && isTokenError(message.message)) {
                clearSession();
                if (ws) ws.onclose = null;
                showScreen('login-screen');
            }
            break;

        case 'lobby_state':
            updateLobby(message);
            {
                const cur = document.querySelector('.screen:not(.hidden)');
                const onGame = cur && cur.id === 'game-screen';
                const active = message.status === 'playing' || message.status === 'finished';
                if (active && onGame) break;
                showScreen('lobby-screen');
            }
            break;

        case 'game_state': {
            const wasLobby = document.querySelector('.screen:not(.hidden)')?.id === 'lobby-screen';
            currentGameState = message;
            showScreen('game-screen');
            updateGame(message);
            if (wasLobby && message.status === 'playing') playSound('game_start');
            if (message.status !== 'finished') {
                const rb = document.getElementById('restart-game-btn');
                if (rb) rb.classList.add('hidden');
                const lb = document.getElementById('leave-room-btn');
                if (lb) lb.classList.add('hidden');
            }
            break;
        }

        case 'card_played':
            addMessage(`${message.player_name} zahrál kartu ${getCardTypeName(message.card_type)}`, 'success');
            if (message.result?.see_future_cards && message.player_id === playerId) {
                showSeeFutureModal(message.result.see_future_cards);
            }
            if (message.result?.favor_card && message.player_id === playerId) {
                addMessage(`✅ Dostal jsi kartu: ${message.result.favor_card.title}`, 'success');
            }
            if (message.result?.action_restored) {
                addMessage(`↩️ Akce ${getCardTypeName(message.result.original_card_type || '')} byla obnovena!`, 'success');
            }
            if (currentGameState) {
                currentGameState.can_nope = message.can_nope || false;
                const mp = currentGameState.players?.find(p => p.player_id === playerId);
                if (mp) updateMyHand(mp.hand || [], currentGameState.current_player_id === playerId, currentGameState.can_nope);
            }
            break;

        case 'player_died':
            addMessage(`💀 ${message.player_name} zemřel!`, 'died');
            playSound('exploding_kitten');
            if (message.player_id === playerId) showExplosionEffect();
            break;

        case 'game_end':
            addMessage(`🎉 ${message.winner_name} vyhrál hru!`, 'success');
            playSound('game_end');
            {
                const rb = document.getElementById('restart-game-btn');
                if (rb) rb.classList.remove('hidden');
                const lb = document.getElementById('leave-room-btn');
                if (lb) lb.classList.remove('hidden');
            }
            break;

        case 'leave_ok':
            clearSession();
            if (ws) { ws.onclose = null; ws.close(); ws = null; }
            showScreen('login-screen');
            break;

        case 'you_were_removed':
            currentLobbyId = null;
            currentLobbyName = null;
            showScreen('lobby-browser-screen');
            showError(message.message || 'Byli jste odebráni');
            break;

        case 'player_removed':
            addMessage(`Hráč ${message.player_name} byl odebrán`, 'error');
            break;

        case 'deck_view':
            if (typeof showDeckModal === 'function') {
                showDeckModal(message.cards || []);
            }
            break;

        case 'card_drawn':
            addMessage('Lízl jsi kartu: ' + message.card.title, 'success');
            break;

        case 'exploding_kitten_defused':
            if (message.player_id === playerId) {
                addMessage('🛡️ Přežil jsi Výbušné koťátko pomocí Zneškodni!', 'defused');
                playSound('defused');
            } else {
                addMessage(`🛡️ ${message.player_name} přežil Výbušné koťátko pomocí Zneškodni!`, 'defused');
            }
            break;

        case 'favor_card_taken':
            addMessage(`❌ Ztratil jsi kartu: ${message.card_title}`, 'error');
            break;
    }
}

// =========================================================================
// Screens
// =========================================================================
function showScreen(screenId) {
    document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
    const el = document.getElementById(screenId);
    if (el) el.classList.remove('hidden');
}

function clearSession() {
    sessionStorage.removeItem('token');
    sessionStorage.removeItem('player_id');
    sessionStorage.removeItem('is_super_power');
    token = null;
    playerId = null;
    currentLobbyId = null;
    currentLobbyName = null;
    currentGameState = null;
}

function isTokenError(message) {
    const m = (message || '').toLowerCase();
    return m.includes('token') || m.includes('neplatný') || m.includes('vypršel');
}

function showError(message) {
    const errorDiv = document.getElementById('login-error');
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.classList.add('show');
        setTimeout(() => errorDiv.classList.remove('show'), 5000);
    }
}

// =========================================================================
// Lobby Browser
// =========================================================================
function updateLobbyBrowser(lobbies) {
    const list = document.getElementById('lobbies-list');
    if (!list) return;
    list.innerHTML = '';

    if (lobbies.length === 0) {
        list.innerHTML = '<div class="no-lobbies">Žádné místnosti. Vytvoř novou!</div>';
        return;
    }

    lobbies.forEach(lobby => {
        const statusMap = { waiting: 'Čeká na hráče', playing: 'Probíhá hra', finished: 'Hra skončila' };
        const statusText = statusMap[lobby.status] || lobby.status;
        const isWaiting = lobby.status === 'waiting';
        const canJoin = isWaiting && lobby.player_count < lobby.max_players;
        const isSuperPower = sessionStorage.getItem('is_super_power') === 'true';
        let btnText = 'Připojit';
        if (!isWaiting) btnText = 'Probíhá hra';
        else if (lobby.player_count >= lobby.max_players) btnText = 'Plná';

        const div = document.createElement('div');
        div.className = 'lobby-item';
        div.innerHTML = `
            <div class="lobby-info">
                <div class="lobby-name-text">${escapeHtml(lobby.name)}</div>
                <div class="lobby-details">${lobby.player_count}/${lobby.max_players} hráčů &bull; ${statusText}</div>
            </div>
            <div class="lobby-actions">
                ${isSuperPower ? `<button class="btn-delete-lobby" title="Smazat místnost">✕</button>` : ''}
                <button class="btn-primary lobby-join-btn" ${!canJoin ? 'disabled' : ''}>${btnText}</button>
            </div>
        `;

        const joinBtn = div.querySelector('.lobby-join-btn');
        if (canJoin && joinBtn) {
            joinBtn.addEventListener('click', () => {
                if (ws?.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'join_lobby', lobby_id: lobby.lobby_id }));
                }
            });
        }

        const delBtn = div.querySelector('.btn-delete-lobby');
        if (delBtn) {
            delBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (confirm(`Smazat místnost "${lobby.name}"?`)) {
                    ws?.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ type: 'delete_lobby', lobby_id: lobby.lobby_id }));
                }
            });
        }

        list.appendChild(div);
    });
}

// =========================================================================
// Room Lobby
// =========================================================================
let isReady = false;

function updateLobby(state) {
    const playersList = document.getElementById('players-list');
    if (!playersList) return;

    const isGameActive = state.status === 'playing' || state.status === 'finished';
    playersList.innerHTML = '';

    state.players.forEach(player => {
        const div = document.createElement('div');
        div.className = `player-item ${player.ready ? 'ready' : ''}`;
        let statusText = 'Čeká...';
        if (isGameActive) {
            const hasCards = (player.hand_size || 0) > 0;
            statusText = hasCards ? (player.alive !== false ? 'Ve hře' : 'Vypadl') : 'V lobby';
        } else {
            statusText = player.ready ? '✓ Připraven' : 'Čeká...';
        }
        div.innerHTML = `
            <div class="player-item-left">
                <span class="player-name">${escapeHtml(player.name)}</span>
            </div>
            <span class="ready-status">${statusText}</span>
        `;
        playersList.appendChild(div);
    });

    const myPlayer = state.players.find(p => p.player_id === playerId);
    const readyBtn = document.getElementById('ready-btn');
    if (isGameActive) {
        if (readyBtn) readyBtn.style.display = 'none';
    } else {
        if (readyBtn) {
            readyBtn.style.display = '';
            if (myPlayer) {
                isReady = myPlayer.ready || false;
                readyBtn.textContent = isReady ? 'Zrušit' : 'Připraven';
            }
        }
    }

    const statusDiv = document.getElementById('lobby-status');
    if (statusDiv) {
        if (isGameActive) {
            statusDiv.textContent = state.status === 'playing' ? 'Probíhá hra' : 'Hra skončila';
            statusDiv.style.color = state.status === 'playing' ? '#ff9800' : '#dc3545';
        } else if (state.can_start) {
            statusDiv.textContent = 'Všichni jsou připraveni! Hra začne automaticky...';
            statusDiv.style.color = '#28a745';
        } else {
            statusDiv.textContent = `Čekáme na hráče... (${state.players.length}/5)`;
            statusDiv.style.color = '#667eea';
        }
    }
}

// =========================================================================
// Game
// =========================================================================
function updateGame(state) {
    const restartBtn = document.getElementById('restart-game-btn');
    const leaveRoomBtn = document.getElementById('leave-room-btn');
    if (restartBtn) {
        if (state.status === 'finished') {
            restartBtn.classList.remove('hidden');
            if (leaveRoomBtn) leaveRoomBtn.classList.remove('hidden');
            const drawBtn = document.getElementById('draw-card-btn');
            if (drawBtn) drawBtn.style.display = 'none';
        } else {
            restartBtn.classList.add('hidden');
            if (leaveRoomBtn) leaveRoomBtn.classList.add('hidden');
            const drawBtn = document.getElementById('draw-card-btn');
            if (drawBtn) drawBtn.style.display = '';
        }
    }

    const deckSizeDiv = document.getElementById('deck-size');
    if (deckSizeDiv && state.draw_pile_size !== undefined) {
        deckSizeDiv.textContent = `${state.draw_pile_size} karet`;
    }

    const deckInfoBox = document.querySelector('.deck-info-box');
    if (deckInfoBox) {
        const old = deckInfoBox.querySelector('.direction-indicator');
        if (old) old.remove();
        const di = document.createElement('div');
        di.className = 'direction-indicator';
        di.style.cssText = 'margin-top: 8px; padding: 6px; background: rgba(102,126,234,0.1); border-radius: 6px; text-align: center; font-weight: bold; color: #667eea; font-size: 14px;';
        di.innerHTML = `Směr: ${state.reverse_direction ? '⬅️ Dozadu' : '➡️ Dopředu'}`;
        deckInfoBox.appendChild(di);
    }

    updatePlayers(state.players, state.current_player_id, state.pending_turns || {});

    const myPlayer = state.players.find(p => p.player_id === playerId);
    if (myPlayer) {
        if (!myPlayer.hand) myPlayer.hand = [];
        updateMyHand(myPlayer.hand, state.current_player_id === playerId, state.can_nope || false);
    }

    const drawBtn = document.getElementById('draw-card-btn');
    if (drawBtn) drawBtn.disabled = state.current_player_id !== playerId;
}

function updatePlayers(players, currentPlayerId, pendingTurns) {
    const container = document.getElementById('players-container');
    if (!container) return;
    container.innerHTML = '';

    players.forEach(player => {
        const div = document.createElement('div');
        div.className = `player-card ${player.player_id === currentPlayerId ? 'current' : ''} ${!player.alive ? 'dead' : ''}`;
        const turns = pendingTurns[player.player_id] || 0;
        const turnsDisplay = turns > 0 ? `${turns} tah${turns > 1 ? 'y' : turns === 1 ? '' : 'ů'}` : '';
        div.innerHTML = `
            <div class="player-name">${escapeHtml(player.name)}</div>
            ${turnsDisplay ? `<div class="player-turns" style="font-size:0.85em;color:#667eea;margin-top:4px;">${turnsDisplay}</div>` : ''}
            <div class="hand-size">Karet: ${player.hand_size}</div>
            ${!player.alive ? '<div style="color:red;margin-top:5px;">Mrtvý</div>' : ''}
            ${player.alive && player.connected === false ? '<div style="color:#ff9800;margin-top:5px;">Odpojen</div>' : ''}
        `;
        container.appendChild(div);
    });
}

// =========================================================================
// Hand
// =========================================================================
function updateMyHand(hand, isMyTurn, canNope) {
    const handDiv = document.getElementById('my-hand');
    if (!handDiv) return;

    const filtered = hand.filter(c => c.type !== 'EXPLODING_KITTEN');
    const typeOrder = { DEFUSE: 0, SKIP: 2, ATTACK: 3, SHUFFLE: 4, SEE_FUTURE: 5, FAVOR: 6, NOPE: 7, REVERSE: 8 };
    const sorted = [...filtered].sort((a, b) => {
        const diff = (typeOrder[a.type] ?? 999) - (typeOrder[b.type] ?? 999);
        return diff !== 0 ? diff : (a.title || '').localeCompare(b.title || '');
    });

    handDiv.innerHTML = '';
    sorted.forEach(card => {
        const isActive = isMyTurn || (card.type === 'NOPE' && canNope);
        const cardDiv = document.createElement('div');
        cardDiv.className = `card card-type-${card.type.toLowerCase()} ${!isActive ? 'disabled' : ''}`;
        cardDiv.dataset.cardId = card.id;
        cardDiv.dataset.cardType = card.type;

        if (card.asset_path) {
            cardDiv.style.backgroundImage = `url(${card.asset_path})`;
            cardDiv.style.backgroundSize = 'cover';
            cardDiv.style.backgroundPosition = 'center';
            cardDiv.classList.add('has-image');
        }

        cardDiv.innerHTML = `
            <div class="card-title">${escapeHtml(card.title)}</div>
            <div class="card-description">${escapeHtml(card.description)}</div>
        `;

        if (isActive) {
            cardDiv.addEventListener('mouseenter', () => {
                const d = cardDiv.querySelector('.card-description');
                if (d) { d.style.display = 'block'; setTimeout(() => d.style.opacity = '1', 10); }
            });
            cardDiv.addEventListener('mouseleave', () => {
                const d = cardDiv.querySelector('.card-description');
                if (d) { d.style.opacity = '0'; setTimeout(() => d.style.display = 'none', 300); }
            });

            let touchStart = 0, lpTimeout = null;
            cardDiv.addEventListener('touchstart', (e) => {
                touchStart = Date.now();
                lpTimeout = setTimeout(() => { cardDiv.classList.toggle('show-description'); e.preventDefault(); }, 500);
            });
            cardDiv.addEventListener('touchend', () => {
                clearTimeout(lpTimeout);
                if (Date.now() - touchStart < 500 && !cardDiv.classList.contains('show-description')) playCard(card);
            });
            cardDiv.addEventListener('touchcancel', () => clearTimeout(lpTimeout));

            cardDiv.addEventListener('click', (e) => {
                if (e.target.classList.contains('card-description')) return;
                if (!('ontouchstart' in window)) playCard(card);
            });
        }

        handDiv.appendChild(cardDiv);
    });
}

let pendingFavorCard = null;

function playCard(card) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (card.type === 'FAVOR') {
        pendingFavorCard = card;
        showFavorModal();
    } else {
        ws.send(JSON.stringify({ type: 'play_card', card_id: card.id }));
    }
}

function showFavorModal() {
    const modal = document.getElementById('favor-modal');
    const list = document.getElementById('favor-players-list');
    if (!modal || !list || !currentGameState) return;

    list.innerHTML = '';
    currentGameState.players.forEach(p => {
        if (p.player_id !== playerId && p.alive) {
            const div = document.createElement('div');
            div.className = 'favor-player-item';
            div.innerHTML = `<span class="favor-player-name">${escapeHtml(p.name)}</span><span class="favor-player-hand">(${p.hand_size} karet)</span>`;
            div.addEventListener('click', () => {
                if (pendingFavorCard && ws?.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'play_card', card_id: pendingFavorCard.id, target_player_id: p.player_id }));
                    pendingFavorCard = null;
                    modal.classList.remove('show');
                }
            });
            list.appendChild(div);
        }
    });
    if (list.children.length === 0) list.innerHTML = '<p>Žádný dostupný cíl</p>';
    modal.classList.add('show');
}

// =========================================================================
// Modals
// =========================================================================
function showSeeFutureModal(cards) {
    const modal = document.getElementById('see-future-modal');
    const cardsDiv = document.getElementById('modal-cards');
    if (!modal || !cardsDiv) return;
    cardsDiv.innerHTML = '';
    if (cards.length === 0) { cardsDiv.innerHTML = '<p>Žádné karty</p>'; return; }

    cards.forEach(card => {
        const d = document.createElement('div');
        d.className = `card card-type-${card.type.toLowerCase()}`;
        if (card.asset_path) {
            d.style.backgroundImage = `url(${card.asset_path})`;
            d.style.backgroundSize = 'cover';
            d.style.backgroundPosition = 'center';
            d.classList.add('has-image');
        }
        d.innerHTML = `<div class="card-title">${escapeHtml(card.title)}</div><div class="card-description">${escapeHtml(card.description)}</div>`;
        cardsDiv.appendChild(d);
    });
    modal.classList.add('show');
}

function showExplosionEffect() {
    const overlay = document.getElementById('explosion-overlay');
    if (!overlay) return;
    document.body.classList.add('shake');
    overlay.classList.add('active');
    setTimeout(() => { overlay.classList.remove('active'); document.body.classList.remove('shake'); }, 1500);
}

// =========================================================================
// Buttons init
// =========================================================================
function initButtons() {
    document.getElementById('ready-btn')?.addEventListener('click', () => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        isReady = !isReady;
        ws.send(JSON.stringify({ type: 'set_ready', ready: isReady }));
        const rb = document.getElementById('ready-btn');
        if (rb) rb.textContent = isReady ? 'Zrušit' : 'Připraven';
    });

    document.getElementById('draw-card-btn')?.addEventListener('click', () => {
        if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'draw_card' }));
    });

    document.getElementById('restart-game-btn')?.addEventListener('click', () => {
        if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'restart_game' }));
    });

    document.getElementById('leave-btn')?.addEventListener('click', () => {
        if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'leave_room' }));
    });

    document.getElementById('leave-room-btn')?.addEventListener('click', () => {
        if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'leave_room' }));
    });

    document.getElementById('logout-btn')?.addEventListener('click', () => {
        if (ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'logout' }));
        } else {
            clearSession();
            showScreen('login-screen');
        }
    });

    document.getElementById('create-lobby-btn')?.addEventListener('click', () => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const nameInput = document.getElementById('new-lobby-name');
        const name = nameInput ? nameInput.value.trim() : '';
        ws.send(JSON.stringify({ type: 'create_lobby', name }));
        if (nameInput) nameInput.value = '';
    });

    document.getElementById('new-lobby-name')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') document.getElementById('create-lobby-btn')?.click();
    });

    document.getElementById('cancel-favor-btn')?.addEventListener('click', () => {
        const m = document.getElementById('favor-modal');
        if (m) { m.classList.remove('show'); pendingFavorCard = null; }
    });

    document.getElementById('close-modal-btn')?.addEventListener('click', () => {
        const m = document.getElementById('see-future-modal');
        if (m) m.classList.remove('show');
    });
}

// =========================================================================
// Utilities
// =========================================================================
function addMessage(text, type = '') {
    const div = document.getElementById('game-messages');
    if (!div) return;
    const m = document.createElement('div');
    m.className = `message ${type}`;
    const t = new Date().toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    m.innerHTML = `<span class="message-time">${t}</span><span class="message-text">${escapeHtml(text)}</span>`;
    div.firstChild ? div.insertBefore(m, div.firstChild) : div.appendChild(m);
    div.scrollTop = 0;
}

function playSound(soundName) {
    if (!audioUnlocked) return;
    try {
        const audio = new Audio();
        audio.volume = 0.7;
        audio.src = `/static/sounds/${soundName}.mp3`;
        audio.addEventListener('error', function () {
            if (!audio.src.endsWith('.wav')) { audio.src = `/static/sounds/${soundName}.wav`; audio.load(); }
        }, { once: true });
        audio.play().catch(() => {});
    } catch (e) { /* ignore */ }
}

function getCardTypeName(type) {
    const names = {
        EXPLODING_KITTEN: 'Výbušné koťátko', DEFUSE: 'Zneškodni', SKIP: 'Přeskoč',
        ATTACK: 'Zaútoč', SHUFFLE: 'Zamíchej', SEE_FUTURE: 'Pohledni do budoucnosti',
        FAVOR: 'Tohle si vezmu', NOPE: 'Nené', REVERSE: 'Změna směru'
    };
    return names[type] || type;
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}
