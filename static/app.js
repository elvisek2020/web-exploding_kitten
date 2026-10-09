let ws = null;
let playerId = null;
let token = null;
let currentGameState = null;
let currentLobbyId = null;
let currentLobbyName = null;
let pingInterval = null;
// Obnovení session uložené v prohlížeči (po jeho zavření/pádu) - server
// v tomto režimu nepřebírá hráče, který je aktivní v jiném okně
let resumeMode = false;
// Místnost, ve které byl hráč před výpadkem spojení (pro hlášku, že vypadl)
let lobbyBeforeReconnect = null;
// Místnost, jejíž průběh hry je zobrazený (při návratu do stejné se nemaže)
let lastLobbyId = null;

// Chybové kódy serveru, po kterých je uložená session k ničemu
const TOKEN_ERROR_CODES = ['token_required', 'invalid_token', 'token_expired'];
// Close kódy serveru (viz main.py)
const WS_CLOSE_REPLACED = 4001;
const WS_CLOSE_ORIGIN_REJECTED = 4003;
const WS_CLOSE_TOO_MANY_CONNECTIONS = 4029;

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
// Session storage
// sessionStorage = identita tohoto okna (přežije reload stránky),
// localStorage   = poslední hráč v tomto prohlížeči (přežije zavření
//                  nebo pád prohlížeče, pak se hra nabídne k obnovení)
// =========================================================================
function storageGet(storage, key) {
    try { return storage.getItem(key); } catch (e) { return null; }
}

function storageSet(storage, key, value) {
    try { storage.setItem(key, value); } catch (e) { /* ignore */ }
}

function storageRemove(storage, key) {
    try { storage.removeItem(key); } catch (e) { /* ignore */ }
}

function saveSession(newPlayerId, newToken) {
    playerId = newPlayerId;
    token = newToken;
    for (const storage of [sessionStorage, localStorage]) {
        storageSet(storage, 'player_id', newPlayerId);
        storageSet(storage, 'token', newToken);
    }
}

function clearSession() {
    // Uloženou session prohlížeče mažeme jen pokud patří tomuto oknu
    if (token && storageGet(localStorage, 'token') === token) {
        storageRemove(localStorage, 'token');
        storageRemove(localStorage, 'player_id');
    }
    storageRemove(sessionStorage, 'token');
    storageRemove(sessionStorage, 'player_id');
    storageRemove(sessionStorage, 'is_super_power');
    token = null;
    playerId = null;
    resumeMode = false;
    currentLobbyId = null;
    currentLobbyName = null;
    currentGameState = null;
    lobbyBeforeReconnect = null;
}

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
    token = storageGet(sessionStorage, 'token');
    playerId = storageGet(sessionStorage, 'player_id');
    if (!token) {
        token = storageGet(localStorage, 'token');
        playerId = storageGet(localStorage, 'player_id');
        resumeMode = !!token;
    }

    const savedName = storageGet(localStorage, 'player_name');
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

            storageSet(localStorage, 'player_name', name);
            window.pendingJoinName = name;

            const pwdInput = document.getElementById('player-password');
            if (pwdInput && pwdInput.value.trim()) {
                window.pendingJoinPassword = pwdInput.value.trim();
            }

            // Uživatel se chce přihlásit znovu – zahodit starou session (např. po restartu serveru)
            clearSession();
            closeSocket();
            connectWebSocket();
        });
    }

    if (token && playerId) connectWebSocket();
    initModals();
    initButtons();
    setInterval(updateReconnectCountdowns, 1000);
});

document.getElementById('player-name')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') document.getElementById('join-btn')?.click();
});

// =========================================================================
// WebSocket
// =========================================================================
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
    ws = socket;

    ws.onopen = () => {
        if (pingInterval) clearInterval(pingInterval);
        pingInterval = setInterval(() => {
            if (ws?.readyState === WebSocket.OPEN) {
                try { ws.send(JSON.stringify({ type: 'ping' })); } catch (e) { /* ignore */ }
            }
        }, 15000);

        if (token) {
            sendReconnect();
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
        if (ws !== socket) return;
        if (pingInterval) { clearInterval(pingInterval); pingInterval = null; }
        ws = null;
        if (event.code === WS_CLOSE_ORIGIN_REJECTED || event.code === WS_CLOSE_TOO_MANY_CONNECTIONS) {
            showError(event.code === WS_CLOSE_TOO_MANY_CONNECTIONS ? 'Příliš mnoho připojení' : 'Připojení odmítnuto');
            return;
        }
        if (event.code === WS_CLOSE_REPLACED) {
            // Hráče převzalo jiné okno - nepřipojovat se zpět, jinak by se okna
            // navzájem donekonečna odpojovala
            showError('Hra je teď otevřená v jiném okně. Pro návrat sem obnov stránku.', 0);
            return;
        }
        if (token) setTimeout(() => { if (token && !ws) connectWebSocket(); }, 1000);
    };
}

function sendReconnect() {
    if (ws?.readyState !== WebSocket.OPEN || !token) return;
    const msg = { type: 'reconnect', token };
    if (resumeMode) msg.resume = true;
    ws.send(JSON.stringify(msg));
}

function closeSocket() {
    if (pingInterval) { clearInterval(pingInterval); pingInterval = null; }
    if (ws) {
        // Úmyslné zavření - bez handlerů, ať se nehlásí "Chyba připojení"
        // a nespouští automatické znovupřipojení
        ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
        try { ws.close(); } catch (e) { /* ignore */ }
        ws = null;
    }
}

function wsSend(message) {
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message));
}

// =========================================================================
// Message handler
// =========================================================================
function handleMessage(message) {
    if (message.type === 'pong') return;
    switch (message.type) {
        case 'join_ok':
            saveSession(message.player_id, message.token);
            if (message.is_super_power) {
                storageSet(sessionStorage, 'is_super_power', 'true');
            } else {
                storageRemove(sessionStorage, 'is_super_power');
            }
            showScreen('lobby-browser-screen');
            break;

        case 'reconnect_ok':
            // Session teď patří tomuto oknu
            saveSession(message.player_id, token);
            resumeMode = false;
            if (message.is_super_power) {
                storageSet(sessionStorage, 'is_super_power', 'true');
            } else {
                storageRemove(sessionStorage, 'is_super_power');
            }
            // Server pošle lobby_joined, nebo seznam místností (pokud už v žádné není)
            lobbyBeforeReconnect = currentLobbyId;
            currentLobbyId = null;
            break;

        case 'lobby_list':
            updateLobbyBrowser(message.lobbies || []);
            if (!currentLobbyId) {
                showScreen('lobby-browser-screen');
                if (lobbyBeforeReconnect) {
                    showError('Spojení bylo přerušené příliš dlouho, z místnosti jsi vypadl');
                    lobbyBeforeReconnect = null;
                }
            }
            break;

        case 'lobby_joined': {
            lobbyBeforeReconnect = null;
            currentLobbyId = message.lobby_id;
            currentLobbyName = message.lobby_name;
            const roomTitle = document.getElementById('room-title');
            if (roomTitle) roomTitle.textContent = message.lobby_name;
            showScreen('lobby-screen');
            if (message.lobby_id !== lastLobbyId) {
                const msgs = document.getElementById('game-messages');
                if (msgs) msgs.innerHTML = '';
            }
            lastLobbyId = message.lobby_id;
            break;
        }

        case 'lobby_left':
            currentLobbyId = null;
            currentLobbyName = null;
            lastLobbyId = null;
            showScreen('lobby-browser-screen');
            break;

        case 'error':
            if (message.code === 'session_active') {
                offerSessionTakeover(message.player_name);
                break;
            }
            showError(message.message || 'Nastala chyba');
            if (TOKEN_ERROR_CODES.includes(message.code)) {
                // Neplatná session (např. po restartu serveru) - zpět na přihlášení
                clearSession();
                closeSocket();
                showScreen('login-screen');
            }
            break;

        case 'lobby_state':
            syncReconnectDeadlines(message.players || []);
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
            syncReconnectDeadlines(message.players || []);
            showScreen('game-screen');
            updateGame(message);
            if (wasLobby && message.status === 'playing') playSound('game_start');
            break;
        }

        case 'card_played': {
            const mine = message.player_id === playerId;
            const kind = mine ? 'mine' : 'other';
            const played = { card: message.card_type };
            const target = message.target_player_name ? [' od ', { player: message.target_player_name }] : [];
            if (mine) logEvent(kind, CARD_ICONS[message.card_type], 'Hraješ ', played, ...target);
            else logEvent(kind, CARD_ICONS[message.card_type], { player: message.player_name }, ' hraje ', played, ...target);
            if (message.result?.action_cancelled) {
                logEvent('warn', '🚫', { card: message.result.original_card_type }, ' zrušeno kartou ', { card: 'NOPE' });
            }
            if (message.result?.action_restored) {
                logEvent('warn', '↩️', { card: message.result.original_card_type }, ' znovu platí');
            }
            if (currentGameState) {
                currentGameState.can_nope = message.can_nope || false;
                const mp = currentGameState.players?.find(p => p.player_id === playerId);
                if (mp) updateMyHand(mp.hand || [], currentGameState.current_player_id === playerId, currentGameState.can_nope);
            }
            break;
        }

        case 'see_future':
            showSeeFutureModal(message.cards || []);
            break;

        case 'favor_card_received':
            logEvent('private', '🤲', 'Od ', { player: message.from_player_name }, ' máš ', { cardTitle: message.card_title });
            break;

        case 'favor_card_taken':
            logEvent('danger', '😿', { player: message.from_player_name }, ' ti vzal ', { cardTitle: message.card_title });
            break;

        case 'player_died':
            if (message.player_id === playerId) logEvent('danger', '💥', 'Vybuchl jsi – konec hry pro tebe');
            else logEvent('danger', '💥', { player: message.player_name }, ' vybuchl!');
            playSound('exploding_kitten');
            if (message.player_id === playerId) showExplosionEffect();
            break;

        case 'player_disconnected':
            logEvent('warn', '📡', { player: message.player_name }, ` se odpojil, čekáme ${message.grace_seconds} s`);
            break;

        case 'player_reconnected':
            logEvent('good', '🔌', { player: message.player_name }, ' je zpět ve hře');
            break;

        case 'player_left': {
            const reasons = {
                left: ['🚪', ' opustil hru'],
                timeout: ['⌛', ' se nevrátil včas a vypadl'],
                disconnected: ['📴', ' se odpojil a vypadl'],
            };
            const [icon, text] = reasons[message.reason] || reasons.left;
            logEvent('warn', icon, { player: message.player_name }, text);
            break;
        }

        case 'game_end':
            if (message.winner_name) {
                if (message.winner_id === playerId) logEvent('good', '🏆', 'Vyhrál jsi hru!');
                else logEvent('good', '🏆', { player: message.winner_name }, ' vyhrál hru!');
            } else {
                logEvent('warn', '🏁', 'Hru ukončil administrátor, bez vítěze');
            }
            playSound('game_end');
            break;

        case 'leave_ok':
            clearSession();
            closeSocket();
            showScreen('login-screen');
            break;

        case 'you_were_removed':
            currentLobbyId = null;
            currentLobbyName = null;
            lastLobbyId = null;
            closeAllModals();
            showScreen('lobby-browser-screen');
            showError(message.message || 'Byli jste odebráni');
            break;

        case 'player_removed':
            logEvent('warn', '🚫', { player: message.player_name }, ' byl odebrán adminem');
            break;

        case 'deck_view':
            if (typeof showDeckModal === 'function') {
                showDeckModal(message.cards || []);
            }
            break;

        case 'card_drawn':
            logEvent('private', '🃏', 'Lízl jsi ', { card: message.card.type, title: message.card.title });
            break;

        case 'exploding_kitten_defused':
            if (message.player_id === playerId) {
                logEvent('good', '🛡️', 'Zneškodnil jsi ', { card: 'EXPLODING_KITTEN' });
                playSound('defused');
            } else {
                logEvent('good', '🛡️', { player: message.player_name }, ' zneškodnil ', { card: 'EXPLODING_KITTEN' });
            }
            break;
    }
}

async function offerSessionTakeover(playerName) {
    const takeOver = await showConfirm({
        title: 'Rozehraná hra',
        message: `Jako hráč „${playerName || '?'}“ jsi přihlášený v jiném okně nebo záložce. Chceš hru převzít sem? Druhé okno se odpojí.`,
        okText: 'Převzít sem',
        cancelText: 'Nový hráč',
    });
    if (takeOver === null) return;
    if (takeOver) {
        resumeMode = false;
        sendReconnect();
    } else {
        // Session patří jinému oknu - nechat ji mu a přihlásit se jako nový hráč
        token = null;
        playerId = null;
        resumeMode = false;
        closeSocket();
        showScreen('login-screen');
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

let toastTimer = null;

// Zobrazí hlášku v liště nahoře (viditelná na všech obrazovkách).
// duration 0 = zůstane zobrazená, dokud ji nenahradí jiná
function showError(message, duration = 5000) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    if (duration > 0) {
        toastTimer = setTimeout(() => toast.classList.remove('show'), duration);
    }
}

// =========================================================================
// Modals
// Otevřený modál blokuje zbytek stránky (inert), Esc a klik mimo okno
// fungují jako "Zrušit", fokus zůstává uvnitř okna.
// =========================================================================
const modalStack = [];

function openModal(modal, { onCancel = null, focus = null } = {}) {
    if (!modal) return;
    modal._onCancel = onCancel;
    modal._returnFocus = document.activeElement;
    if (!modalStack.includes(modal)) modalStack.push(modal);
    modal.classList.add('show');
    updateModalInert();
    const target = focus || modal.querySelector('button:not([disabled])');
    if (target) setTimeout(() => target.focus(), 0);
}

function closeModal(modal) {
    if (!modal) return;
    modal.classList.remove('show');
    const idx = modalStack.indexOf(modal);
    if (idx !== -1) modalStack.splice(idx, 1);
    updateModalInert();
    const back = modal._returnFocus;
    modal._returnFocus = null;
    if (back && typeof back.focus === 'function' && document.contains(back)) back.focus();
}

function cancelModal(modal) {
    if (modal?._onCancel) modal._onCancel();
    else closeModal(modal);
}

function closeAllModals() {
    [...modalStack].reverse().forEach(m => cancelModal(m));
}

function updateModalInert() {
    const container = document.querySelector('.container');
    if (container) container.inert = modalStack.length > 0;
    document.querySelectorAll('.modal').forEach(m => {
        // Aktivní je jen nejvrchnější modál
        m.inert = modalStack.length > 0 && m !== modalStack[modalStack.length - 1];
    });
}

function initModals() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.addEventListener('click', (e) => {
            if (e.target === modal) cancelModal(modal);
        });
    });

    document.addEventListener('keydown', (e) => {
        const top = modalStack[modalStack.length - 1];
        if (!top) return;
        if (e.key === 'Escape') {
            e.preventDefault();
            cancelModal(top);
        } else if (e.key === 'Tab') {
            const focusable = [...top.querySelectorAll('button:not([disabled]), [href], input, [tabindex]:not([tabindex="-1"])')]
                .filter(el => el.offsetParent !== null);
            if (focusable.length === 0) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
            else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
            else if (!top.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
        }
    });
}

// Potvrzovací dialog místo nativního confirm(). Vrací Promise<boolean>,
// případně null, pokud dialog nahradil novější dotaz (volající pak nic nedělá).
function showConfirm({ title = 'Potvrzení', message = '', okText = 'Ano', cancelText = 'Zrušit', danger = false } = {}) {
    return new Promise(resolve => {
        const modal = document.getElementById('confirm-modal');
        const okBtn = document.getElementById('confirm-ok-btn');
        const cancelBtn = document.getElementById('confirm-cancel-btn');
        if (!modal || !okBtn || !cancelBtn) { resolve(false); return; }

        // Předchozí nevyřízený dotaz nahradí nový
        if (modal._resolve) modal._resolve(null);

        document.getElementById('confirm-title').textContent = title;
        document.getElementById('confirm-message').textContent = message;
        okBtn.textContent = okText;
        cancelBtn.textContent = cancelText;
        okBtn.className = danger ? 'btn-danger' : 'btn-primary';

        const finish = (result) => {
            if (modal._resolve !== finish) return;
            modal._resolve = null;
            okBtn.onclick = null;
            cancelBtn.onclick = null;
            closeModal(modal);
            resolve(result);
        };
        modal._resolve = finish;
        okBtn.onclick = () => finish(true);
        cancelBtn.onclick = () => finish(false);
        openModal(modal, { onCancel: () => finish(false), focus: danger ? cancelBtn : okBtn });
    });
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
        const isSuperPower = storageGet(sessionStorage, 'is_super_power') === 'true';
        let btnText = 'Připojit';
        if (!isWaiting) btnText = lobby.status === 'finished' ? 'Hra skončila' : 'Probíhá hra';
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
            joinBtn.addEventListener('click', () => wsSend({ type: 'join_lobby', lobby_id: lobby.lobby_id }));
        }

        const delBtn = div.querySelector('.btn-delete-lobby');
        if (delBtn) {
            delBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const ok = await showConfirm({
                    title: 'Smazat místnost',
                    message: `Opravdu smazat místnost „${lobby.name}“? Hráči v ní budou odpojeni.`,
                    okText: 'Smazat',
                    danger: true,
                });
                if (ok) wsSend({ type: 'delete_lobby', lobby_id: lobby.lobby_id });
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
        div.dataset.playerId = player.player_id;
        let statusHtml;
        if (player.connected === false) {
            statusHtml = `Odpojen (${reconnectCountdownHtml(player.player_id)} s)`;
        } else if (isGameActive) {
            if (player.alive === false) statusHtml = 'Vypadl';
            else statusHtml = state.status === 'playing' ? 'Ve hře' : 'Přežil';
        } else {
            statusHtml = player.ready ? '✓ Připraven' : 'Čeká...';
        }
        div.innerHTML = `
            <div class="player-item-left">
                <span class="player-name">${escapeHtml(player.name)}</span>
            </div>
            <span class="ready-status">${statusHtml}</span>
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
// Odpočet návratu odpojeného hráče
// =========================================================================
const reconnectDeadlines = {};

function syncReconnectDeadlines(players) {
    const now = Date.now();
    players.forEach(p => {
        if (typeof p.reconnect_seconds_left === 'number') {
            reconnectDeadlines[p.player_id] = now + p.reconnect_seconds_left * 1000;
        } else {
            delete reconnectDeadlines[p.player_id];
        }
    });
}

function reconnectSecondsLeft(pid) {
    const deadline = reconnectDeadlines[pid];
    if (!deadline) return null;
    return Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
}

function reconnectCountdownHtml(pid) {
    const secs = reconnectSecondsLeft(pid);
    return `<span class="reconnect-countdown" data-player-id="${escapeHtml(pid)}">${secs ?? '?'}</span>`;
}

function updateReconnectCountdowns() {
    document.querySelectorAll('.reconnect-countdown').forEach(el => {
        const secs = reconnectSecondsLeft(el.dataset.playerId);
        if (secs !== null) el.textContent = secs;
    });
}

// =========================================================================
// Game
// =========================================================================
function updateGame(state) {
    const finished = state.status === 'finished';
    const me = state.players.find(p => p.player_id === playerId);

    document.getElementById('restart-game-btn')?.classList.toggle('hidden', !finished);
    document.getElementById('leave-room-btn')?.classList.toggle('hidden', !finished);
    document.getElementById('leave-game-btn')?.classList.toggle('hidden', finished);
    const drawBtn = document.getElementById('draw-card-btn');
    if (drawBtn) {
        drawBtn.style.display = finished ? 'none' : '';
        drawBtn.disabled = state.current_player_id !== playerId || !me?.alive;
    }

    const deckSizeDiv = document.getElementById('deck-size');
    if (deckSizeDiv && state.draw_pile_size !== undefined) {
        const n = state.draw_pile_size;
        deckSizeDiv.innerHTML = `<span class="deck-count">${n}</span><span class="deck-label">${formatCards(n)}</span>`;
    }

    const direction = document.getElementById('direction-indicator');
    if (direction) {
        direction.innerHTML = `<span class="direction-label">Směr</span><span class="direction-value">${state.reverse_direction ? '⬅️ Dozadu' : '➡️ Dopředu'}</span>`;
    }

    updatePlayers(state.players, state.current_player_id, state.pending_turns || {});

    if (me) {
        if (!me.hand) me.hand = [];
        updateMyHand(me.hand, state.current_player_id === playerId, state.can_nope || false);
    }
}

function formatCards(n) {
    if (n === 1) return 'karta';
    if (n >= 2 && n <= 4) return 'karty';
    return 'karet';
}

function formatTurns(n) {
    if (n === 1) return '1 tah';
    if (n >= 2 && n <= 4) return `${n} tahy`;
    return `${n} tahů`;
}

function updatePlayers(players, currentPlayerId, pendingTurns) {
    const container = document.getElementById('players-container');
    if (!container) return;
    container.innerHTML = '';

    players.forEach(player => {
        const div = document.createElement('div');
        div.className = `player-card ${player.player_id === currentPlayerId ? 'current' : ''} ${!player.alive ? 'dead' : ''}`;
        div.dataset.playerId = player.player_id;
        const turns = pendingTurns[player.player_id] || 0;
        const disconnected = player.alive && player.connected === false;
        div.innerHTML = `
            <div class="player-name">${escapeHtml(player.name)}</div>
            ${turns > 0 ? `<div class="player-turns">${formatTurns(turns)}</div>` : ''}
            <div class="hand-size">Karet: ${player.hand_size}</div>
            ${!player.alive ? '<div class="player-dead">Mrtvý</div>' : ''}
            ${disconnected ? `<div class="player-disconnected">Odpojen · vypadne za ${reconnectCountdownHtml(player.player_id)} s</div>` : ''}
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
        wsSend({ type: 'play_card', card_id: card.id });
    }
}

function showFavorModal() {
    const modal = document.getElementById('favor-modal');
    const list = document.getElementById('favor-players-list');
    if (!modal || !list || !currentGameState) return;

    list.innerHTML = '';
    let selectable = 0;
    currentGameState.players.forEach(p => {
        if (p.player_id === playerId || !p.alive) return;
        const empty = (p.hand_size || 0) === 0;
        const div = document.createElement('button');
        div.type = 'button';
        div.className = 'favor-player-item';
        div.disabled = empty;
        div.innerHTML = `<span class="favor-player-name">${escapeHtml(p.name)}</span><span class="favor-player-hand">(${empty ? 'nemá karty' : `${p.hand_size} karet`})</span>`;
        if (!empty) {
            selectable++;
            div.addEventListener('click', () => {
                if (pendingFavorCard) {
                    wsSend({ type: 'play_card', card_id: pendingFavorCard.id, target_player_id: p.player_id });
                }
                pendingFavorCard = null;
                closeModal(modal);
            });
        }
        list.appendChild(div);
    });
    if (selectable === 0) {
        list.insertAdjacentHTML('beforeend', '<p>Žádný hráč nemá kartu, kterou by šlo vzít</p>');
    }
    openModal(modal, {
        onCancel: () => { pendingFavorCard = null; closeModal(modal); },
    });
}

// =========================================================================
// Modals
// =========================================================================
function showSeeFutureModal(cards) {
    const modal = document.getElementById('see-future-modal');
    const cardsDiv = document.getElementById('modal-cards');
    if (!modal || !cardsDiv) return;
    cardsDiv.innerHTML = '';
    if (cards.length === 0) cardsDiv.innerHTML = '<p>Žádné karty</p>';

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
    openModal(modal);
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
        wsSend({ type: 'set_ready', ready: isReady });
        const rb = document.getElementById('ready-btn');
        if (rb) rb.textContent = isReady ? 'Zrušit' : 'Připraven';
    });

    document.getElementById('draw-card-btn')?.addEventListener('click', () => wsSend({ type: 'draw_card' }));

    document.getElementById('restart-game-btn')?.addEventListener('click', () => wsSend({ type: 'restart_game' }));

    document.getElementById('leave-btn')?.addEventListener('click', () => wsSend({ type: 'leave_room' }));

    document.getElementById('leave-room-btn')?.addEventListener('click', () => wsSend({ type: 'leave_room' }));

    document.getElementById('leave-game-btn')?.addEventListener('click', async () => {
        const me = currentGameState?.players?.find(p => p.player_id === playerId);
        if (me?.alive) {
            const ok = await showConfirm({
                title: 'Opustit hru',
                message: 'Opravdu chceš opustit rozehranou hru?\nVypadneš z ní a zpátky se už nevrátíš.',
                okText: 'Opustit hru',
                danger: true,
            });
            if (!ok) return;
        }
        wsSend({ type: 'leave_room' });
    });

    document.getElementById('logout-btn')?.addEventListener('click', () => {
        if (ws?.readyState === WebSocket.OPEN) {
            wsSend({ type: 'logout' });
        } else {
            clearSession();
            closeSocket();
            showScreen('login-screen');
        }
    });

    document.getElementById('create-lobby-btn')?.addEventListener('click', () => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const nameInput = document.getElementById('new-lobby-name');
        const name = nameInput ? nameInput.value.trim() : '';
        wsSend({ type: 'create_lobby', name });
        if (nameInput) nameInput.value = '';
    });

    document.getElementById('new-lobby-name')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') document.getElementById('create-lobby-btn')?.click();
    });

    document.getElementById('cancel-favor-btn')?.addEventListener('click', () => {
        cancelModal(document.getElementById('favor-modal'));
    });

    document.getElementById('close-modal-btn')?.addEventListener('click', () => {
        closeModal(document.getElementById('see-future-modal'));
    });
}

// =========================================================================
// Utilities
// =========================================================================
const MAX_CHAT_MESSAGES = 4;

const CARD_ICONS = {
    EXPLODING_KITTEN: '💣', DEFUSE: '🛡️', SKIP: '⏭️', ATTACK: '⚔️', SHUFFLE: '🔀',
    SEE_FUTURE: '🔮', FAVOR: '🤲', NOPE: '✋', REVERSE: '🔄',
};

// Zápis do Průběhu hry.
// kind: mine (můj veřejný tah), other (tah soupeře), private (vidím jen já),
//       good, danger, warn (důležité události)
// parts: text, {player: jméno}, {card: TYP} nebo {cardTitle: název}
function logEvent(kind, icon, ...parts) {
    const div = document.getElementById('game-messages');
    if (!div) return;

    let plain = '';
    const html = parts.map(part => {
        if (typeof part === 'string') {
            plain += part;
            return escapeHtml(part);
        }
        if (part.player !== undefined) {
            plain += part.player;
            return `<strong class="log-player">${escapeHtml(part.player)}</strong>`;
        }
        const title = part.title || part.cardTitle || getCardTypeName(part.card || '');
        plain += title;
        const cardType = part.card || cardTypeByTitle(part.cardTitle);
        const type = cardType ? ` card-chip-${String(cardType).toLowerCase()}` : '';
        return `<span class="card-chip${type}">${escapeHtml(title)}</span>`;
    }).join('');

    const m = document.createElement('div');
    m.className = `message log-${kind}`;
    m.title = plain;
    const t = new Date().toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' });
    m.innerHTML = `
        <span class="message-icon">${icon || '•'}</span>
        <span class="message-text">${html}${kind === 'private' ? '<span class="log-private-badge" title="Tuhle zprávu vidíš jen ty">jen ty</span>' : ''}</span>
        <span class="message-time">${t}</span>`;
    div.insertBefore(m, div.firstChild);
    while (div.children.length > MAX_CHAT_MESSAGES) {
        div.removeChild(div.lastChild);
    }
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

function cardTypeByTitle(title) {
    return Object.keys(CARD_ICONS).find(type => getCardTypeName(type) === title) || null;
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
