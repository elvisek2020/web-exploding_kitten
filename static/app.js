let ws = null;
let playerId = null;
let token = null;
let currentGameState = null;

// Cache pro audio objekty
const audioCache = {};
// Flag pro odemknutí zvuků (některé prohlížeče blokují autoplay)
let audioUnlocked = false;

// Odemkneme zvuky při první interakci uživatele
document.addEventListener('click', () => {
    if (!audioUnlocked) {
        audioUnlocked = true;
        // Vytvoříme a přehrajeme tichý zvuk pro odemknutí
        const unlockAudio = new Audio('data:audio/wav;base64,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');
        unlockAudio.volume = 0.01;
        unlockAudio.play().catch(() => {});
    }
}, { once: true });

// Načtení tokenu ze sessionStorage při načtení stránky
// Přidáme event listener pro refresh na nadpis
window.addEventListener('DOMContentLoaded', () => {
    const mainTitle = document.getElementById('main-title');
    if (mainTitle) {
        mainTitle.addEventListener('click', () => {
            window.location.reload();
        });
    }
});

window.addEventListener('load', () => {
    console.log('DEBUG: window.load event spuštěn');
    token = sessionStorage.getItem('token');
    playerId = sessionStorage.getItem('player_id');
    
    // Předvyplníme jméno hráče, pokud existuje v sessionStorage
    const savedPlayerName = sessionStorage.getItem('player_name');
    const nameInput = document.getElementById('player-name');
    if (savedPlayerName && nameInput) {
        nameInput.value = savedPlayerName;
    }
    
    // Načteme verzi buildu z JSON souboru
    const versionInfo = document.getElementById('version-info');
    if (versionInfo) {
        fetch('/static/version.json')
            .then(response => response.json())
            .then(data => {
                versionInfo.textContent = data.version || 'v.unknown';
            })
            .catch(error => {
                console.error('Chyba při načítání verze:', error);
                versionInfo.textContent = 'v.unknown';
            });
    }
    
    // Přidáme event listener pro tlačítko Přihlásit
    const joinBtn = document.getElementById('join-btn');
    console.log('DEBUG: joinBtn nalezen:', joinBtn);
    if (joinBtn) {
        console.log('DEBUG: Přidávám event listener na join-btn');
        joinBtn.addEventListener('click', async () => {
            console.log('DEBUG: Kliknuto na Přihlásit');
            const nameInput = document.getElementById('player-name');
            if (!nameInput) {
                console.error('DEBUG: nameInput není nalezen');
                return;
            }
            
            const name = nameInput.value.trim();
            console.log('DEBUG: Jméno:', name);
            
            if (!name) {
                showError('Zadej jméno');
                return;
            }
            
            // Uložíme jméno do sessionStorage pro příští hraní
            sessionStorage.setItem('player_name', name);
            
            // Funkce pro odeslání join zprávy
            const sendJoin = () => {
                if (ws && ws.readyState === WebSocket.OPEN && token) {
                    // Pouze pokud máme token, můžeme použít existující WebSocket
                    console.log('DEBUG: Posílám join zprávu s jménem:', name);
                    const joinMessage = { type: 'join', name: name };
                    console.log('DEBUG: Odesílám join zprávu:', JSON.stringify(joinMessage));
                    try {
                        ws.send(JSON.stringify(joinMessage));
                        console.log('DEBUG: Join zpráva úspěšně odeslána');
                        return true;
                    } catch (error) {
                        console.error('DEBUG: Chyba při odesílání join zprávy:', error);
                        return false;
                    }
                }
                console.log('DEBUG: WebSocket není otevřený nebo nemáme token, stav:', ws ? ws.readyState : 'null', 'token:', token ? 'existuje' : 'neexistuje');
                return false;
            };
            
            // Pokud nemáme token, vždy vytvoříme nový WebSocket (i když je starý otevřený)
            if (!token && ws) {
                console.log('DEBUG: Nemáme token, zavírám existující WebSocket');
                ws.onclose = null; // Odstraníme event listener, aby se nezkoušel reconnect
                ws.close();
                ws = null;
            }
            
            // Pokud je WebSocket otevřený a máme token, pošleme zprávu přímo
            if (sendJoin()) {
                console.log('DEBUG: Join zpráva odeslána přímo');
                return;
            }
            
            // Pokud není otevřený, otevřeme ho a pošleme zprávu až když se otevře
            console.log('DEBUG: WebSocket není otevřený, připojuji se...');
            console.log('DEBUG: WebSocket stav:', ws ? ws.readyState : 'null');
            
            // Uložíme jméno do dočasné proměnné pro pozdější použití
            window.pendingJoinName = name;
            console.log('DEBUG: Uloženo pendingJoinName:', window.pendingJoinName);
            
            // Zavřeme existující WebSocket, pokud existuje a není otevřený
            if (ws && ws.readyState !== WebSocket.OPEN) {
                console.log('DEBUG: Zavírám existující WebSocket');
                ws.onclose = null; // Odstraníme event listener, aby se nezkoušel reconnect
                ws.close();
                ws = null;
            }
            
            // Vytvoříme nový WebSocket
            console.log('DEBUG: Vytvářím nový WebSocket');
            connectWebSocket();
            
            // Počkáme, až se WebSocket otevře (max 5 sekund)
            let attempts = 0;
            const maxAttempts = 50; // 50 * 100ms = 5 sekund
            const checkInterval = setInterval(() => {
                attempts++;
                if (sendJoin()) {
                    console.log('DEBUG: Join zpráva odeslána po připojení');
                    clearInterval(checkInterval);
                    delete window.pendingJoinName;
                } else if (ws && (ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING)) {
                    console.log('DEBUG: WebSocket se uzavřel během čekání');
                    clearInterval(checkInterval);
                    showError('Připojení se nezdařilo. Zkus to znovu.');
                } else if (attempts >= maxAttempts) {
                    console.error('DEBUG: Timeout při čekání na WebSocket');
                    clearInterval(checkInterval);
                    showError('Timeout při připojování. Zkus to znovu.');
                }
            }, 100);
        });
    } else {
        console.error('DEBUG: join-btn není nalezen při načtení stránky');
    }
    
    if (token && playerId) {
        // Pokud je uživatel super_power, uložíme heslo do sessionStorage pro reconnect
        const isSuperPower = sessionStorage.getItem('is_super_power') === 'true';
        if (isSuperPower && !sessionStorage.getItem('super_power_password')) {
            // Pokud nemáme heslo uložené, zkusíme ho získat z inputu (pokud je na super_power stránce)
            const passwordInput = document.getElementById('player-password');
            if (passwordInput && passwordInput.value.trim()) {
                sessionStorage.setItem('super_power_password', passwordInput.value.trim());
            }
        }
        connectWebSocket();
    }
    
    // Inicializujeme event listenery pro tlačítka
    initRestartButton();
    
    console.log('DEBUG: window.load event dokončen');
});

// Také zkusíme DOMContentLoaded pro případ, že load event neproběhne
document.addEventListener('DOMContentLoaded', () => {
    console.log('DEBUG: DOMContentLoaded event spuštěn');
    const joinBtn = document.getElementById('join-btn');
    console.log('DEBUG: joinBtn v DOMContentLoaded:', joinBtn);
});

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('DEBUG: WebSocket připojen, readyState:', ws.readyState);
        console.log('DEBUG: token:', token ? 'existuje' : 'neexistuje');
        console.log('DEBUG: pendingJoinName:', window.pendingJoinName || 'neexistuje');
        
        if (token) {
            // Reconnect
            console.log('DEBUG: Reconnect s tokenem');
            ws.send(JSON.stringify({ type: 'reconnect', token: token }));
        } else if (window.pendingJoinName) {
            // Pokud máme pending join jméno, pošleme join zprávu
            const name = window.pendingJoinName;
            const password = window.pendingJoinPassword || null;
            console.log('DEBUG: WebSocket otevřen, posílám join zprávu s jménem:', name, 'heslo:', password ? '***' : 'není');
            const joinMessage = password ? { type: 'join', name: name, password: password } : { type: 'join', name: name };
            console.log('DEBUG: Odesílám join zprávu:', JSON.stringify(password ? { type: 'join', name: name, password: '***' } : joinMessage));
            try {
                ws.send(JSON.stringify(joinMessage));
                console.log('DEBUG: Join zpráva úspěšně odeslána');
            } catch (error) {
                console.error('DEBUG: Chyba při odesílání join zprávy:', error);
            }
            delete window.pendingJoinName;
            if (window.pendingJoinPassword) {
                delete window.pendingJoinPassword;
            }
        } else {
            // Zkusíme zjistit jméno z inputu, pokud je na login screenu
            const nameInput = document.getElementById('player-name');
            const passwordInput = document.getElementById('player-password');
            if (nameInput && nameInput.value.trim()) {
                const name = nameInput.value.trim();
                // Zkusíme heslo z inputu, nebo z sessionStorage (pro super_power reconnect)
                let password = passwordInput && passwordInput.value.trim() ? passwordInput.value.trim() : null;
                if (!password) {
                    const storedPassword = sessionStorage.getItem('super_power_password');
                    if (storedPassword) {
                        password = storedPassword;
                    }
                }
                console.log('DEBUG: WebSocket otevřen, našel jsem jméno v inputu:', name, 'heslo:', password ? '***' : 'není');
                const joinMessage = password ? { type: 'join', name: name, password: password } : { type: 'join', name: name };
                console.log('DEBUG: Odesílám join zprávu z inputu:', JSON.stringify(password ? { type: 'join', name: name, password: '***' } : joinMessage));
                try {
                    ws.send(JSON.stringify(joinMessage));
                    console.log('DEBUG: Join zpráva úspěšně odeslána z inputu');
                } catch (error) {
                    console.error('DEBUG: Chyba při odesílání join zprávy z inputu:', error);
                }
            } else {
                // Zkusíme reconnect s heslem z sessionStorage, pokud je uživatel super_power
                const isSuperPower = sessionStorage.getItem('is_super_power') === 'true';
                const storedPassword = sessionStorage.getItem('super_power_password');
                const storedName = sessionStorage.getItem('player_name');
                if (isSuperPower && storedPassword && storedName && !token) {
                    console.log('DEBUG: Super_power reconnect - posílám join s heslem z sessionStorage');
                    const joinMessage = { type: 'join', name: storedName, password: storedPassword };
                    try {
                        ws.send(JSON.stringify(joinMessage));
                        console.log('DEBUG: Join zpráva úspěšně odeslána z sessionStorage');
                    } catch (error) {
                        console.error('DEBUG: Chyba při odesílání join zprávy z sessionStorage:', error);
                    }
                } else {
                    console.log('DEBUG: WebSocket otevřen, ale žádné pendingJoinName, token ani jméno v inputu');
                }
            }
        }
    };
    
    ws.onmessage = (event) => {
        console.log('DEBUG: Přijata zpráva ze serveru:', event.data);
        try {
            const message = JSON.parse(event.data);
            console.log('DEBUG: Parsovaná zpráva:', message);
            handleMessage(message);
        } catch (error) {
            console.error('DEBUG: Chyba při parsování zprávy:', error, 'Raw data:', event.data);
        }
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        showError('Chyba připojení');
    };
    
    ws.onclose = (event) => {
        console.log('DEBUG: WebSocket odpojen, code:', event.code, 'reason:', event.reason, 'wasClean:', event.wasClean);
        // Reconnect pouze pokud máme token (jsme přihlášeni)
        // Pokud nemáme token, necháme to být (uživatel se může znovu pokusit přihlásit)
        if (token) {
            console.log('DEBUG: Reconnect s tokenem za 1 sekundu');
            setTimeout(() => {
                if (token) {
                    connectWebSocket();
                }
            }, 1000);
        } else {
            console.log('DEBUG: Nemám token, neprovádím reconnect');
            // Pokud nemáme token a máme pendingJoinName, zkusíme znovu připojit
            if (window.pendingJoinName) {
                console.log('DEBUG: Mám pendingJoinName, zkusím znovu připojit za 1 sekundu');
                setTimeout(() => {
                    if (window.pendingJoinName && !token) {
                        console.log('DEBUG: Znovu připojuji WebSocket s pendingJoinName');
                        connectWebSocket();
                    }
                }, 1000);
            }
        }
    };
}

function handleMessage(message) {
    console.log('Received:', message);
    
    switch (message.type) {
        case 'join_ok':
            console.log('DEBUG: Přijato join_ok, player_id:', message.player_id);
            playerId = message.player_id;
            token = message.token;
            sessionStorage.setItem('player_id', playerId);
            sessionStorage.setItem('token', token);
            // Uložíme is_super_power do sessionStorage, pokud je nastaveno
            if (message.is_super_power) {
                sessionStorage.setItem('is_super_power', 'true');
            } else {
                sessionStorage.removeItem('is_super_power');
            }
            console.log('DEBUG: Přepínám na lobby-screen');
            showScreen('lobby-screen');
            break;
        
        case 'error':
            console.error('DEBUG: Chyba ze serveru:', message.message);
            showError(message.message || 'Nastala chyba');
            // Pokud je chyba při přihlášení, zůstaneme na login screenu
            break;
        
        case 'reconnect_ok':
            playerId = message.player_id;
            showScreen('lobby-screen');
            break;
        
        case 'lobby_state':
            updateLobby(message);
            // Přepneme na lobby screen pouze pokud hra neprobíhá nebo pokud už jsme v lobby
            // Pokud hráč hraje (je na game-screen), nepřepínejme ho do lobby
            const currentScreen = document.querySelector('.screen:not(.hidden)');
            const isOnGameScreen = currentScreen && currentScreen.id === 'game-screen';
            const isGameActive = message.status === 'playing' || message.status === 'finished';
            
            // Pokud hra probíhá a hráč je ve hře, nepřepínejme ho
            if (isGameActive && isOnGameScreen) {
                // Hráč hraje, necháme ho ve hře
                break;
            }
            
            // Jinak přepneme na lobby screen
            showScreen('lobby-screen');
            // Vymažeme chat při nové hře
            const messagesDiv = document.getElementById('game-messages');
            if (messagesDiv) {
                messagesDiv.innerHTML = '';
            }
            break;
        
        case 'game_state':
            // Zkontrolujeme, jestli se právě přepínáme z lobby na hru (začátek hry)
            const currentScreenForGame = document.querySelector('.screen:not(.hidden)');
            const wasInLobby = currentScreenForGame && currentScreenForGame.id === 'lobby-screen';
            
            currentGameState = message;
            showScreen('game-screen');
            updateGame(message);
            
            // Pokud jsme byli v lobby a teď jsme ve hře, přehrajeme zvuk zahájení hry
            if (wasInLobby && message.status === 'playing') {
                playSound('game_start');
            }
            
            // Zajistíme, že tlačítko restart je skryté pokud hra nekončila
            if (message.status !== 'finished') {
                const restartBtn2 = document.getElementById('restart-game-btn');
                if (restartBtn2) {
                    restartBtn2.classList.add('hidden');
                }
            }
            break;
        
        case 'card_played':
            addMessage(`${message.player_name} zahrál kartu ${getCardTypeName(message.card_type)}`, 'success');
            // Pokud je to SEE_FUTURE a máme karty, zobrazíme modal
            if (message.result && message.result.see_future_cards && message.player_id === playerId) {
                console.log('DEBUG card_played: Přijato see_future_cards:', message.result.see_future_cards.length, 'karet');
                console.log('DEBUG card_played: Karty:', message.result.see_future_cards.map(c => c.title || c.id));
                showSeeFutureModal(message.result.see_future_cards);
            }
            // Pokud je to FAVOR a hráč, který kartu zahrál, jsme my, zobrazíme jakou kartu jsme dostali
            if (message.result && message.result.favor_card && message.player_id === playerId) {
                const favorCard = message.result.favor_card;
                addMessage(`✅ Dostal jsi kartu: ${favorCard.title}`, 'success');
                console.log('FAVOR karta zahrána, favor_card:', favorCard);
            }
            // Aktualizujeme ruku, aby se NOPE karty staly aktivní, pokud lze použít NOPE
            if (currentGameState) {
                currentGameState.can_nope = message.can_nope || false;
                const myPlayer = currentGameState.players.find(p => p.player_id === playerId);
                if (myPlayer) {
                    updateMyHand(myPlayer.hand || [], currentGameState.current_player_id === playerId, currentGameState.can_nope || false);
                }
            }
            break;
        
        case 'exploding_kitten_drawn':
            // Tato zpráva se posílá pouze když hráč přežije výbušné koťátko pomocí Zneškodni
            // (viz exploding_kitten_defused)
            addMessage(`💣 ${message.player_name} si lízl Výbušné koťátko!`, 'error');
            playSound('exploding_kitten');
            break;
        
        case 'player_died':
            addMessage(`💀 ${message.player_name} zemřel!`, 'died');
            // Přehrát zvuk exploze (když hráč skutečně umře)
            playSound('exploding_kitten');
            // Zobrazit celoobrazovkový efekt exploze, pokud zemřel aktuální hráč
            if (message.player_id === playerId) {
                showExplosionEffect();
            }
            break;
        
        case 'game_end':
            addMessage(`🎉 ${message.winner_name} vyhrál hru!`, 'success');
            // Přehrát zvuk konce hry
            playSound('game_end');
            // Zobrazíme tlačítko pro restart
            const restartBtn3 = document.getElementById('restart-game-btn');
            if (restartBtn3) {
                restartBtn3.classList.remove('hidden');
            }
            // Necháme hráče ve hře, aby mohli restartovat
            break;
        
        case 'leave_ok':
            // Hráč opustil lobby
            // Nejdřív smažeme token a playerId, aby se nereconnectovalo
            sessionStorage.removeItem('token');
            sessionStorage.removeItem('player_id');
            playerId = null;
            token = null;
            
            // Zavřeme WebSocket explicitně a zrušíme reconnect
            if (ws) {
                ws.onclose = null; // Zrušíme event listener, aby se nereconnectovalo
                ws.close();
                ws = null;
            }
            
            showScreen('login-screen');
            break;
        
        case 'you_were_removed':
            // Hráč byl odebrán z lobby administrátorem
            sessionStorage.removeItem('token');
            sessionStorage.removeItem('player_id');
            playerId = null;
            token = null;
            
            // Zavřeme WebSocket explicitně
            if (ws) {
                ws.onclose = null;
                ws.close();
                ws = null;
            }
            
            showScreen('login-screen');
            showError(message.message || 'Byli jste odebráni z lobby administrátorem');
            break;
        
        case 'deck_view':
            // Zobrazení balíčku v super power módu
            if (typeof showDeckModal === 'function') {
                showDeckModal(message.cards || []);
            } else {
                // Fallback - použijeme stejnou logiku jako v super_power.html
                const modal = document.getElementById('view-deck-modal');
                const cardsDiv = document.getElementById('deck-cards');
                if (modal && cardsDiv) {
                    cardsDiv.innerHTML = '';
                    if (message.cards && message.cards.length > 0) {
                        message.cards.forEach(card => {
                            const cardDiv = document.createElement('div');
                            cardDiv.className = 'card';
                            if (card.asset_path) {
                                cardDiv.style.backgroundImage = `url('${card.asset_path}')`;
                                cardDiv.style.backgroundSize = 'cover';
                                cardDiv.style.backgroundPosition = 'center';
                                cardDiv.classList.add('has-image');
                            }
                            cardDiv.innerHTML = `
                                <div class="card-title">${escapeHtml(card.title)}</div>
                            `;
                            cardsDiv.appendChild(cardDiv);
                        });
                    } else {
                        cardsDiv.innerHTML = '<p>Balíček je prázdný</p>';
                    }
                    modal.classList.add('show');
                }
            }
            break;
        
        case 'card_drawn':
            addMessage('Lízl jsi kartu: ' + message.card.title, 'success');
            break;
        
        case 'exploding_kitten_defused':
            // Zobrazíme zprávu - pokud je to hráč sám, použijeme "Přežil jsi", jinak "Přežil X"
            if (message.player_id === playerId) {
                addMessage('🛡️ Přežil jsi Výbušné koťátko pomocí Zneškodni!', 'defused');
                // Přehrát zvuk přežití výbuchu
                playSound('defused');
            } else {
                addMessage(`🛡️ ${message.player_name} přežil Výbušné koťátko pomocí Zneškodni!`, 'defused');
            }
            break;
        
        case 'favor_card_taken':
            addMessage(`❌ Ztratil jsi kartu: ${message.card_title}`, 'error');
            break;
        
        case 'error':
            showError(message.message);
            break;
    }
}

function showScreen(screenId) {
    document.querySelectorAll('.screen').forEach(screen => {
        screen.classList.add('hidden');
    });
    document.getElementById(screenId).classList.remove('hidden');
}

function showError(message) {
    const errorDiv = document.getElementById('login-error');
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.classList.add('show');
        setTimeout(() => {
            errorDiv.classList.remove('show');
        }, 5000);
    }
}

function playSound(soundName) {
    /**
     * Přehrává zvukový soubor
     * @param {string} soundName - Název zvuku bez přípony (např. 'exploding_kitten' nebo 'game_end')
     */
    if (!audioUnlocked) {
        console.log(`Zvuky jsou zamčené - čekám na interakci uživatele pro ${soundName}`);
        return;
    }
    
    try {
        // Zkusíme MP3, pokud neexistuje, použijeme WAV
        const mp3Path = `/static/sounds/${soundName}.mp3`;
        const wavPath = `/static/sounds/${soundName}.wav`;
        
        // Vytvoříme nový audio objekt pro každé přehrání
        const audio = new Audio();
        audio.volume = 0.7; // Nastavíme hlasitost
        
        // Zkusíme načíst MP3
        audio.src = mp3Path;
        
        // Fallback na WAV pokud MP3 selže
        audio.addEventListener('error', function onError() {
            if (audio.src !== wavPath) {
                console.log(`MP3 selhalo, zkouším WAV pro ${soundName}`);
                audio.src = wavPath;
                audio.load();
            } else {
                console.warn(`Nepodařilo se načíst zvuk ${soundName} (ani MP3 ani WAV)`);
            }
        }, { once: true });
        
        // Zkusíme přehrát
        const playPromise = audio.play();
        
        if (playPromise !== undefined) {
            playPromise
                .then(() => {
                    console.log(`Zvuk ${soundName} se přehrává`);
                })
                .catch(err => {
                    // Některé prohlížeče blokují autoplay bez interakce uživatele
                    console.warn(`Nepodařilo se přehrát zvuk ${soundName}:`, err.message || err);
                });
        }
        
    } catch (err) {
        console.error(`Chyba při přehrávání zvuku ${soundName}:`, err);
    }
}

function addMessage(text, type = '') {
    const messagesDiv = document.getElementById('game-messages');
    if (!messagesDiv) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    
    // Přidáme čas
    const now = new Date();
    const timeStr = now.toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    
    // Datum a text na jeden řádek
    messageDiv.innerHTML = `
        <span class="message-time">${timeStr}</span>
        <span class="message-text">${escapeHtml(text)}</span>
    `;
    
    // Přidáme na začátek kontejneru (nejnovější zpráva bude první v DOMu a zobrazí se nahoře)
    if (messagesDiv.firstChild) {
        messagesDiv.insertBefore(messageDiv, messagesDiv.firstChild);
    } else {
        messagesDiv.appendChild(messageDiv);
    }
    
    // Scroll na začátek (kde jsou nejnovější zprávy)
    // S flex-direction: column je scrollTop=0 na začátku (nejnovější zprávy)
    messagesDiv.scrollTop = 0;
}

// Login - event listener se přidá po načtení stránky

document.getElementById('player-name')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        document.getElementById('join-btn').click();
    }
});

// Ready button
let isReady = false;
document.getElementById('ready-btn')?.addEventListener('click', () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    
    isReady = !isReady;
    ws.send(JSON.stringify({ type: 'set_ready', ready: isReady }));
    document.getElementById('ready-btn').textContent = isReady ? 'Zrušit' : 'Připraven';
});

function updateLobby(state) {
    const playersList = document.getElementById('players-list');
    if (!playersList) return;
    
    const isGameActive = state.status === 'playing' || state.status === 'finished';
    
    playersList.innerHTML = '';
    state.players.forEach(player => {
        const div = document.createElement('div');
        div.className = `player-item ${player.ready ? 'ready' : ''}`;
        // Během hry zobrazujeme jiný status
        let statusText = 'Čeká...';
        if (isGameActive) {
            // Hráč hraje pouze pokud má karty v ruce (hand_size > 0)
            // hand_size je vždy posílán v lobby_state (i když hide_hand=True)
            const handSize = player.hand_size || 0;
            const hasCards = handSize > 0;
            
            if (hasCards) {
                // Hráč má karty - hraje
                statusText = player.alive !== false ? 'Ve hře' : 'Vypadl';
            } else {
                // Nový hráč, který se připojil během hry (nemá karty)
                statusText = 'V lobby';
            }
        } else {
            // Hra neprobíhá - zobrazujeme ready status
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
    
    // Aktualizujeme tlačítko "Připraven" podle stavu aktuálního hráče
    const myPlayer = state.players.find(p => p.player_id === playerId);
    const readyBtn = document.getElementById('ready-btn');
    
    if (isGameActive) {
        // Během hry skryjeme nebo zakážeme ready button
        if (readyBtn) {
            readyBtn.style.display = 'none';
        }
    } else {
        // Když hra neprobíhá, zobrazíme ready button
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
            if (state.status === 'playing') {
                statusDiv.textContent = 'Probíhá hra';
                statusDiv.style.color = '#ff9800';
            } else if (state.status === 'finished') {
                statusDiv.textContent = 'Hra skončila';
                statusDiv.style.color = '#dc3545';
            }
        } else if (state.can_start) {
            statusDiv.textContent = 'Všichni jsou připraveni! Hra začne automaticky...';
            statusDiv.style.color = '#28a745';
        } else {
            statusDiv.textContent = `Čekáme na hráče... (${state.players.length}/5)`;
            statusDiv.style.color = '#667eea';
        }
    }
}

function updateGame(state) {
    // Zobrazíme/skryjeme tlačítko pro restart - POUZE když je hra dokončena
    const restartBtn = document.getElementById('restart-game-btn');
    if (restartBtn) {
        if (state.status === 'finished') {
            restartBtn.classList.remove('hidden');
            // Skryjeme tlačítko líznutí během dokončené hry
            const drawBtn = document.getElementById('draw-card-btn');
            if (drawBtn) drawBtn.style.display = 'none';
        } else {
            restartBtn.classList.add('hidden');
            // Zobrazíme tlačítko líznutí během hry
            const drawBtn = document.getElementById('draw-card-btn');
            if (drawBtn) drawBtn.style.display = '';
        }
    }
    
    // Zajistíme, že chat zůstane scrollovaný na začátku (nejnovější zprávy nahoře)
    const messagesDiv = document.getElementById('game-messages');
    if (messagesDiv) {
        // S flex-direction: column je scrollTop=0 na začátku (nejnovější zprávy)
        messagesDiv.scrollTop = 0;
    }
    
    // Update deck size
    const deckSizeDiv = document.getElementById('deck-size');
    if (deckSizeDiv && state.draw_pile_size !== undefined) {
        deckSizeDiv.textContent = `${state.draw_pile_size} karet`;
    }
    
    // Přidáme indikátor směru do boxíku s dobíracím balíčkem
    const deckInfoBox = document.querySelector('.deck-info-box');
    if (deckInfoBox) {
        // Odstraníme starý indikátor, pokud existuje
        const oldIndicator = deckInfoBox.querySelector('.direction-indicator');
        if (oldIndicator) {
            oldIndicator.remove();
        }
        
        // Přidáme nový indikátor směru
        const directionIndicator = document.createElement('div');
        directionIndicator.className = 'direction-indicator';
        directionIndicator.style.cssText = 'margin-top: 8px; padding: 6px; background: rgba(102, 126, 234, 0.1); border-radius: 6px; text-align: center; font-weight: bold; color: #667eea; font-size: 14px;';
        directionIndicator.innerHTML = `Směr: ${state.reverse_direction ? '⬅️ Dozadu' : '➡️ Dopředu'}`;
        deckInfoBox.appendChild(directionIndicator);
    }
    
    // Update players
    updatePlayers(state.players, state.current_player_id, state.pending_turns || {}, state.reverse_direction || false);
    
    // Update my hand
    const myPlayer = state.players.find(p => p.player_id === playerId);
    if (myPlayer) {
        // Zajistíme, že hand je pole
        if (!myPlayer.hand) {
            myPlayer.hand = [];
        }
        
        console.log('updateGame - ruka z game_state:', myPlayer.hand.length, 'karet');
        console.log('Karty v ruce z game_state:', myPlayer.hand.map(c => c.title || c.id || 'bez názvu'));
        
        // Aktualizujeme ruku - použijeme hand z game_state, který by měl být aktualizovaný
        // Server už přidal kartu do ruky před posláním game_state, takže by měla být v hand
        console.log('Aktualizace ruky, počet karet:', myPlayer.hand.length);
        updateMyHand(myPlayer.hand, state.current_player_id === playerId, state.can_nope || false);
    }
    
    // Update buttons
    const isMyTurn = state.current_player_id === playerId;
    const drawBtn = document.getElementById('draw-card-btn');
    
    if (drawBtn) {
        drawBtn.disabled = !isMyTurn;
    }
    
    // Skryjeme tlačítko restart, pokud hra nekončila
    // (to už dělá updateGame výše, takže to zde nepotřebujeme)
}

function updatePlayers(players, currentPlayerId, pendingTurns = {}, reverseDirection = false) {
    const container = document.getElementById('players-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    players.forEach(player => {
        const div = document.createElement('div');
        div.className = `player-card ${player.player_id === currentPlayerId ? 'current' : ''} ${!player.alive ? 'dead' : ''}`;
        
        // Zobrazíme počet tahů, pokud má hráč pending_turns
        const turns = pendingTurns[player.player_id] || 0;
        const turnsDisplay = turns > 0 ? `${turns} tah${turns > 1 ? 'y' : turns === 1 ? '' : 'ů'}` : '';
        
        div.innerHTML = `
            <div class="player-name">${escapeHtml(player.name)}</div>
            ${turnsDisplay ? `<div class="player-turns" style="font-size: 0.85em; color: #667eea; margin-top: 4px;">${turnsDisplay}</div>` : ''}
            <div class="hand-size">Karet: ${player.hand_size}</div>
            ${!player.alive ? '<div style="color: red; margin-top: 5px;">Mrtvý</div>' : ''}
        `;
        container.appendChild(div);
    });
}

function updateMyHand(hand, isMyTurn, canNope = false) {
    const handDiv = document.getElementById('my-hand');
    if (!handDiv) return;
    
    // DŮLEŽITÉ: Výbušné koťátko se NESMÍ zobrazit v ruce - filtrujeme ho
    const filteredHand = hand.filter(card => card.type !== 'EXPLODING_KITTEN');
    
    console.log('updateMyHand - počet karet:', filteredHand.length, '(původně:', hand.length, ')');
    console.log('updateMyHand - karty:', filteredHand.map(c => c.title || c.id));
    console.log('updateMyHand - isMyTurn:', isMyTurn, 'canNope:', canNope);
    
    // Seřadíme karty podle typu, aby stejné typy byly spolu
    const sortedHand = [...filteredHand].sort((a, b) => {
        // Pořadí typů karet pro řazení
        const typeOrder = {
            'DEFUSE': 0,
            'EXPLODING_KITTEN': 1,
            'SKIP': 2,
            'ATTACK': 3,
            'SHUFFLE': 4,
            'SEE_FUTURE': 5,
            'FAVOR': 6,
            'NOPE': 7,
            'REVERSE': 8
        };
        
        const orderA = typeOrder[a.type] !== undefined ? typeOrder[a.type] : 999;
        const orderB = typeOrder[b.type] !== undefined ? typeOrder[b.type] : 999;
        
        if (orderA !== orderB) {
            return orderA - orderB;
        }
        
        // Pokud jsou stejného typu, řadíme podle názvu
        return (a.title || '').localeCompare(b.title || '');
    });
    
    handDiv.innerHTML = '';
    sortedHand.forEach(card => {
        const cardDiv = document.createElement('div');
        // Přidáme třídu podle typu karty pro barvení
        const cardTypeClass = `card-type-${card.type.toLowerCase()}`;
        // NOPE karta je aktivní, pokud je náš tah NEBO pokud lze použít NOPE
        const isCardActive = isMyTurn || (card.type === 'NOPE' && canNope);
        cardDiv.className = `card ${cardTypeClass} ${!isCardActive ? 'disabled' : ''}`;
        cardDiv.dataset.cardId = card.id;
        cardDiv.dataset.cardType = card.type;
        
        // Pokud má karta obrázek, použijeme ho jako pozadí celé karty
        if (card.asset_path) {
            cardDiv.style.backgroundImage = `url(${card.asset_path})`;
            cardDiv.style.backgroundSize = 'cover';
            cardDiv.style.backgroundPosition = 'center';
            cardDiv.style.backgroundRepeat = 'no-repeat';
            cardDiv.classList.add('has-image');
        }
        
        cardDiv.innerHTML = `
            <div class="card-title">${escapeHtml(card.title)}</div>
            <div class="card-description">${escapeHtml(card.description)}</div>
        `;
        
        if (isCardActive) {
            // Desktop - hover zobrazí popis
            cardDiv.addEventListener('mouseenter', () => {
                const desc = cardDiv.querySelector('.card-description');
                if (desc) {
                    desc.style.display = 'block';
                    setTimeout(() => desc.style.opacity = '1', 10);
                }
            });
            cardDiv.addEventListener('mouseleave', () => {
                const desc = cardDiv.querySelector('.card-description');
                if (desc) {
                    desc.style.opacity = '0';
                    setTimeout(() => desc.style.display = 'none', 300);
                }
            });
            
            // Mobilní - dlouhý tap zobrazí/skryje popis
            let touchStartTime = 0;
            let longPressTimeout = null;
            
            cardDiv.addEventListener('touchstart', (e) => {
                touchStartTime = Date.now();
                longPressTimeout = setTimeout(() => {
                    cardDiv.classList.toggle('show-description');
                    e.preventDefault();
                }, 500);
            });
            
            cardDiv.addEventListener('touchend', (e) => {
                const touchDuration = Date.now() - touchStartTime;
                clearTimeout(longPressTimeout);
                
                // Pokud to byl krátký tap (< 500ms), zahrajeme kartu
                if (touchDuration < 500 && !cardDiv.classList.contains('show-description')) {
                    playCard(card);
                }
            });
            
            cardDiv.addEventListener('touchcancel', () => {
                clearTimeout(longPressTimeout);
            });
            
            // Desktop - kliknutí na kartu (ne na popis)
            cardDiv.addEventListener('click', (e) => {
                // Pokud klikneme na popis, nehrajeme kartu
                if (e.target.classList.contains('card-description')) {
                    return;
                }
                // Na desktopu hrajeme kartu při kliknutí
                if (!('ontouchstart' in window)) {
                    playCard(card);
                }
            });
        }
        
        handDiv.appendChild(cardDiv);
    });
}

let pendingFavorCard = null;

function playCard(card) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    
    // Speciální karty vyžadují cílového hráče
    if (card.type === 'FAVOR') {
        pendingFavorCard = card;
        showFavorModal();
    } else {
        ws.send(JSON.stringify({
            type: 'play_card',
            card_id: card.id
        }));
    }
}

function showFavorModal() {
    const modal = document.getElementById('favor-modal');
    const playersList = document.getElementById('favor-players-list');
    if (!modal || !playersList || !currentGameState) return;
    
    playersList.innerHTML = '';
    
    // Zobrazíme všechny živé hráče kromě sebe
    currentGameState.players.forEach(player => {
        if (player.player_id !== playerId && player.alive) {
            const div = document.createElement('div');
            div.className = 'favor-player-item';
            div.innerHTML = `
                <span class="favor-player-name">${escapeHtml(player.name)}</span>
                <span class="favor-player-hand">(${player.hand_size} karet)</span>
            `;
            div.addEventListener('click', () => {
                if (pendingFavorCard && ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({
                        type: 'play_card',
                        card_id: pendingFavorCard.id,
                        target_player_id: player.player_id
                    }));
                    pendingFavorCard = null;
                    modal.classList.remove('show');
                }
            });
            playersList.appendChild(div);
        }
    });
    
    if (playersList.children.length === 0) {
        playersList.innerHTML = '<p>Žádný dostupný cíl</p>';
    }
    
    modal.classList.add('show');
}

// Cancel favor button
document.getElementById('cancel-favor-btn')?.addEventListener('click', () => {
    const modal = document.getElementById('favor-modal');
    if (modal) {
        modal.classList.remove('show');
        pendingFavorCard = null;
    }
});

// Draw card button
document.getElementById('draw-card-btn')?.addEventListener('click', () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'draw_card' }));
});

// Restart game button - přidáme event listener po načtení stránky
function initRestartButton() {
    const restartBtn = document.getElementById('restart-game-btn');
    if (restartBtn) {
        restartBtn.addEventListener('click', () => {
            console.log('DEBUG: Kliknuto na Začít novou hru');
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                console.error('DEBUG: WebSocket není otevřený');
                return;
            }
            console.log('DEBUG: Posílám restart_game zprávu');
            ws.send(JSON.stringify({ type: 'restart_game' }));
        });
    } else {
        console.error('DEBUG: restart-game-btn není nalezen');
    }
}

// Leave lobby button
document.getElementById('leave-btn')?.addEventListener('click', () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'leave_lobby' }));
});

function getCardTypeName(type) {
    const names = {
        'EXPLODING_KITTEN': 'Výbušné koťátko',
        'DEFUSE': 'Zneškodni',
        'SKIP': 'Přeskoč',
        'ATTACK': 'Zaútoč',
        'SHUFFLE': 'Zamíchej',
        'SEE_FUTURE': 'Pohledni do budoucnosti',
        'FAVOR': 'Tohle si vezmu',
        'NOPE': 'Nené',
        'REVERSE': 'Změna směru'
    };
    return names[type] || type;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showSeeFutureModal(cards) {
    const modal = document.getElementById('see-future-modal');
    const cardsDiv = document.getElementById('modal-cards');
    if (!modal || !cardsDiv) return;
    
    console.log('DEBUG showSeeFutureModal: Zobrazujeme', cards.length, 'karet:', cards.map(c => c.title || c.id));
    
    cardsDiv.innerHTML = '';
    
    // Zajistíme, že se zobrazí všechny karty (minimálně 3, pokud jsou dostupné)
    if (cards.length === 0) {
        cardsDiv.innerHTML = '<p>Žádné karty k zobrazení</p>';
        return;
    }
    
    cards.forEach(card => {
        const cardDiv = document.createElement('div');
        // Přidáme třídu podle typu karty pro barvení
        const cardTypeClass = `card-type-${card.type.toLowerCase()}`;
        cardDiv.className = `card ${cardTypeClass}`;
        
        // Pokud má karta obrázek, použijeme ho jako pozadí celé karty
        if (card.asset_path) {
            cardDiv.style.backgroundImage = `url(${card.asset_path})`;
            cardDiv.style.backgroundSize = 'cover';
            cardDiv.style.backgroundPosition = 'center';
            cardDiv.style.backgroundRepeat = 'no-repeat';
            cardDiv.classList.add('has-image');
        }
        
        cardDiv.innerHTML = `
            <div class="card-title">${escapeHtml(card.title)}</div>
            <div class="card-description">${escapeHtml(card.description)}</div>
        `;
        
        // Desktop - hover zobrazí popis
        cardDiv.addEventListener('mouseenter', () => {
            const desc = cardDiv.querySelector('.card-description');
            if (desc) {
                desc.style.display = 'block';
                setTimeout(() => desc.style.opacity = '1', 10);
            }
        });
        cardDiv.addEventListener('mouseleave', () => {
            const desc = cardDiv.querySelector('.card-description');
            if (desc) {
                desc.style.opacity = '0';
                setTimeout(() => desc.style.display = 'none', 300);
            }
        });
        
        // Mobilní - dlouhý tap zobrazí/skryje popis
        let touchStartTime = 0;
        let longPressTimeout = null;
        
        cardDiv.addEventListener('touchstart', (e) => {
            touchStartTime = Date.now();
            longPressTimeout = setTimeout(() => {
                cardDiv.classList.toggle('show-description');
                e.preventDefault();
            }, 500);
        });
        
        cardDiv.addEventListener('touchend', (e) => {
            const touchDuration = Date.now() - touchStartTime;
            clearTimeout(longPressTimeout);
            
            // Pokud to byl krátký tap (méně než 500ms), necháme to projít
            if (touchDuration < 500) {
                // Krátký tap - nic neděláme
            }
        });
        
        cardDiv.addEventListener('touchmove', () => {
            clearTimeout(longPressTimeout);
        });
        
        cardsDiv.appendChild(cardDiv);
    });
    
    modal.classList.add('show');
}

// Funkce pro zobrazení efektu exploze
function showExplosionEffect() {
    const overlay = document.getElementById('explosion-overlay');
    if (!overlay) return;
    
    // Přidáme shake efekt na body
    document.body.classList.add('shake');
    
    // Zobrazíme overlay
    overlay.classList.add('active');
    
    // Po 1.5 sekundách odstraníme efekt
    setTimeout(() => {
        overlay.classList.remove('active');
        document.body.classList.remove('shake');
    }, 1500);
}

// Close modal button
document.getElementById('close-modal-btn')?.addEventListener('click', () => {
    const modal = document.getElementById('see-future-modal');
    if (modal) {
        modal.classList.remove('show');
    }
});

