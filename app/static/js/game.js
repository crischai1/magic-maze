// Main game client: SVG renderer, input handler, network, chat, timer.
// Hero colors per rulebook: Y=Yellow Barbarian, P=Purple Mage, G=Green Elf, O=Orange Dwarf.

const wrap = document.querySelector(".game-wrap");
const code = wrap.dataset.code;
const username = wrap.dataset.username;
const playerId = wrap.dataset.playerId;

const socket = io("/game", { transports: ["websocket", "polling"] });

const CELL_SIZE = 40;
const SVG_NS = "http://www.w3.org/2000/svg";

// ---------------- State ----------------
let state = null;
let selectedPawnColor = null;
let lastServerRemainingMs = 0;
let lastServerTimestamp = Date.now();
let timerPaused = false;
let chatUnlockedUntil = null;
let cachedReachable = null;  // {moves: {N: [[r,c],...], ...}, vortex: [[r,c]...]}

const tileLayer = document.getElementById("tile-layer");
const pawnLayer = document.getElementById("pawn-layer");
const overlayLayer = document.getElementById("overlay-layer");
const svg = document.getElementById("board-svg");
const timerDisplay = document.getElementById("timer-display");
const timerFill = document.getElementById("timer-fill");
const actionCardEl = document.getElementById("action-card");
const playersListEl = document.getElementById("players-list");
const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatCard = document.querySelector(".chat-card");
const phaseBanner = document.getElementById("phase-banner");
const resultOverlay = document.getElementById("result-overlay");
const btnReturnLobby = document.getElementById("btn-return-lobby");
const deckCounter = document.getElementById("deck-counter");

// ---------------- Helpers ----------------
function el(tag, attrs = {}, children = []) {
    const e = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (v != null) e.setAttribute(k, String(v));
    }
    children.forEach((c) => e.appendChild(c));
    return e;
}

function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
}

const DIR_VEC = { 0: [-1, 0], 1: [0, 1], 2: [1, 0], 3: [0, -1] };
const DIR_NAMES = ["N", "E", "S", "W"];
const DIR_KEYS = { w: 0, d: 1, s: 2, a: 3 };

function rotateLocal(lr, lc, rot) {
    rot = ((rot % 4) + 4) % 4;
    if (rot === 0) return [lr, lc];
    if (rot === 1) return [lc, 3 - lr];
    if (rot === 2) return [3 - lr, 3 - lc];
    return [3 - lc, lr];
}

function resolveCell(placedTile, tileDef, lr, lc) {
    const [gr, gc] = rotateLocal(lr, lc, placedTile.rotation);
    const globalR = placedTile.origin[0] + gr;
    const globalC = placedTile.origin[1] + gc;
    const def = tileDef.cells[lr][lc];
    const dirNumByName = { N: 0, E: 1, S: 2, W: 3 };
    const walls = (def.walls || []).map((w) => (dirNumByName[w] + placedTile.rotation) % 4);
    return { globalR, globalC, def, walls };
}

// ---------------- Board rendering ----------------

function viewBoxToFit() {
    if (!state) return;
    const cells = [];
    for (const placed of state.board.tiles) {
        for (let r = 0; r < 4; r++) {
            for (let c = 0; c < 4; c++) {
                cells.push([placed.origin[0] + r, placed.origin[1] + c]);
            }
        }
    }
    if (!cells.length) return;
    let minR = Infinity, maxR = -Infinity, minC = Infinity, maxC = -Infinity;
    for (const [r, c] of cells) {
        if (r < minR) minR = r;
        if (r > maxR) maxR = r;
        if (c < minC) minC = c;
        if (c > maxC) maxC = c;
    }
    const pad = CELL_SIZE * 0.8;
    const x = minC * CELL_SIZE - pad;
    const y = minR * CELL_SIZE - pad;
    const w = (maxC - minC + 1) * CELL_SIZE + pad * 2;
    const h = (maxR - minR + 1) * CELL_SIZE + pad * 2;
    svg.setAttribute("viewBox", `${x} ${y} ${w} ${h}`);
}

function renderBoard() {
    if (!state) return;
    clear(tileLayer);
    clear(overlayLayer);
    const exploredAnchors = new Set();
    for (const t of state.board.tiles) {
        for (const p of (t.explored_anchors || [])) {
            exploredAnchors.add(`${p[0]},${p[1]}`);
        }
    }
    const usedTimers = new Set((state.used_sand_timers || []).map(p => `${p[0]},${p[1]}`));
    const usedBalls = new Set((state.used_crystal_balls || []).map(p => `${p[0]},${p[1]}`));
    for (const placed of state.board.tiles) {
        const tileDef = state.board.tile_defs[placed.tile_id];
        if (!tileDef) continue;
        // No tile-border rect — the per-cell wall lines form the visible
        // perimeter and leave a genuine gap at door cells.
        const DIR_NAME_BY_NUM = ["N", "E", "S", "W"];
        const DIR_NUM_BY_NAME = { N: 0, E: 1, S: 2, W: 3 };
        for (let lr = 0; lr < 4; lr++) {
            for (let lc = 0; lc < 4; lc++) {
                const { globalR, globalC, def, walls } = resolveCell(placed, tileDef, lr, lc);
                const x = globalC * CELL_SIZE;
                const y = globalR * CELL_SIZE;
                const isStart = (def.features || []).includes("start");
                tileLayer.appendChild(el("rect", {
                    x, y, width: CELL_SIZE, height: CELL_SIZE,
                    class: "cell-bg" + (isStart ? " cell-start" : ""),
                }));
                for (const d of walls) {
                    const [x1, y1, x2, y2] = wallLine(x, y, d);
                    tileLayer.appendChild(el("line", { x1, y1, x2, y2, class: "cell-wall" }));
                }
                // Compute the global direction this explore door faces (for door orientation).
                let exploreEdgeGlobal = null;
                if (def.explore_edge != null) {
                    const localNum = DIR_NUM_BY_NAME[def.explore_edge];
                    exploreEdgeGlobal = DIR_NAME_BY_NUM[(localNum + placed.rotation) % 4];
                }
                renderFeatures(x, y, def, exploredAnchors.has(`${globalR},${globalC}`), exploreEdgeGlobal);
                const cellKey = `${globalR},${globalC}`;
                if (usedTimers.has(cellKey) || usedBalls.has(cellKey)) {
                    tileLayer.appendChild(el("rect", {
                        x: x + 4, y: y + 4,
                        width: CELL_SIZE - 8, height: CELL_SIZE - 8,
                        class: "out-of-order",
                    }));
                }
            }
        }
    }
    renderEscalators();
    if (state.pending_exploration) {
        const [r, c] = state.pending_exploration.anchor_pos;
        overlayLayer.appendChild(el("rect", {
            x: c * CELL_SIZE, y: r * CELL_SIZE,
            width: CELL_SIZE, height: CELL_SIZE,
            class: "move-hint",
        }));
    }
    viewBoxToFit();
}

function wallLine(x, y, d) {
    const s = CELL_SIZE;
    if (d === 0) return [x, y, x + s, y];
    if (d === 1) return [x + s, y, x + s, y + s];
    if (d === 2) return [x, y + s, x + s, y + s];
    return [x, y, x, y + s];
}

function renderFeatures(x, y, def, isExplored, exploreEdgeGlobal) {
    const cx = x + CELL_SIZE / 2;
    const cy = y + CELL_SIZE / 2;
    for (const feat of def.features || []) {
        if (feat === "start") continue;
        // If this is an explore door cell and it's already been used, omit it entirely.
        if (isExplored && feat.startsWith("explore_")) continue;
        const glyph = featureGlyph(feat);
        if (!glyph) continue;
        let suffix = featureClassSuffix(feat);
        // In scenarios with colored_exits=false, all exits use a neutral class.
        if (feat.startsWith("exit_") && state.scenario && !state.scenario.colored_exits) {
            suffix = "exit";
        }
        const klass = "feature-" + suffix;
        let transform;
        if (feat.startsWith("explore_") && exploreEdgeGlobal) {
            // Door sits on the wall midpoint of the cell's outer edge, with the
            // arrow pointing outward. Canonical glyph faces N (+Y outward), so
            // we rotate to match the cell's outer direction.
            const anchors = {
                N: { ax: cx, ay: y,                  rot: 180 },
                S: { ax: cx, ay: y + CELL_SIZE,      rot: 0   },
                E: { ax: x + CELL_SIZE, ay: cy,      rot: 270 },
                W: { ax: x, ay: cy,                  rot: 90  },
            };
            const a = anchors[exploreEdgeGlobal];
            transform = `translate(${a.ax},${a.ay}) rotate(${a.rot})`;
        } else {
            transform = `translate(${cx},${cy})`;
        }
        const g = el("g", { transform, class: klass });
        g.appendChild(el("use", { href: glyph }));
        tileLayer.appendChild(g);
    }
    // Escalators are drawn as a single diagonal connector between the two
    // endpoints — see renderEscalators(). Skip per-cell rendering here.
}

function renderEscalators() {
    // Original-game style: a single diagonal connector spanning the two
    // endpoint cells, drawn over the cells with endpoint markers. The
    // escalator_to field on a cell points to its partner cell in local
    // (pre-rotation) tile coords, so we rotate before placing globally.
    if (!state) return;
    const drawn = new Set();
    for (const placed of state.board.tiles) {
        const tileDef = state.board.tile_defs[placed.tile_id];
        if (!tileDef) continue;
        for (let lr = 0; lr < 4; lr++) {
            for (let lc = 0; lc < 4; lc++) {
                const cellDef = tileDef.cells[lr][lc];
                if (!cellDef.escalator_to) continue;
                const [lr2, lc2] = cellDef.escalator_to;
                const a = `${lr},${lc}`;
                const b = `${lr2},${lc2}`;
                const lo = a < b ? a : b;
                const hi = a < b ? b : a;
                const key = `${placed.tile_id}@${placed.origin[0]},${placed.origin[1]}:${lo}->${hi}`;
                if (drawn.has(key)) continue;
                drawn.add(key);
                const [gr1, gc1] = rotateLocal(lr, lc, placed.rotation);
                const [gr2, gc2] = rotateLocal(lr2, lc2, placed.rotation);
                const x1 = (placed.origin[1] + gc1) * CELL_SIZE + CELL_SIZE / 2;
                const y1 = (placed.origin[0] + gr1) * CELL_SIZE + CELL_SIZE / 2;
                const x2 = (placed.origin[1] + gc2) * CELL_SIZE + CELL_SIZE / 2;
                const y2 = (placed.origin[0] + gr2) * CELL_SIZE + CELL_SIZE / 2;
                const g = el("g", { class: "feature-escalator" });
                g.appendChild(el("line", {
                    x1, y1, x2, y2,
                    class: "escalator-line",
                }));
                g.appendChild(el("circle", { cx: x1, cy: y1, r: 6, class: "escalator-end" }));
                g.appendChild(el("circle", { cx: x2, cy: y2, r: 6, class: "escalator-end" }));
                // Midpoint icon — a small step glyph clarifies it's an escalator.
                const mx = (x1 + x2) / 2;
                const my = (y1 + y2) / 2;
                const mid = el("g", { transform: `translate(${mx},${my}) scale(0.6)` });
                mid.appendChild(el("use", { href: "#glyph-escalator" }));
                g.appendChild(mid);
                tileLayer.appendChild(g);
            }
        }
    }
}

function featureGlyph(feat) {
    if (feat.startsWith("item_")) return "#glyph-item";
    if (feat.startsWith("exit_")) return "#glyph-exit";
    if (feat.startsWith("vortex_")) return "#glyph-vortex";
    if (feat.startsWith("explore_")) return "#glyph-explore-door";
    if (feat === "sand_timer") return "#glyph-sand-timer";
    if (feat === "crystal_ball") return "#glyph-crystal";
    if (feat === "camera") return "#glyph-camera";
    if (feat === "dwarf_passage") return "#glyph-dwarf-passage";
    return null;
}

function featureClassSuffix(feat) {
    if (feat.startsWith("item_")) return "item-" + feat.slice(-1).toUpperCase();
    if (feat.startsWith("exit_")) return "exit-" + feat.slice(-1).toUpperCase();
    if (feat.startsWith("vortex_")) return "vortex-" + feat.slice(-1).toUpperCase();
    if (feat.startsWith("explore_")) return "explore-" + feat.slice(-1).toUpperCase();
    if (feat === "sand_timer") return "sand-timer";
    if (feat === "crystal_ball") return "crystal-ball";
    if (feat === "camera") return "camera";
    if (feat === "dwarf_passage") return "dwarf-passage";
    return "";
}

// ---------------- Pawns ----------------

function renderPawns() {
    if (!state) return;
    clear(pawnLayer);
    for (const [color, p] of Object.entries(state.pawns)) {
        if (p.exited) continue;
        const [r, c] = p.pos;
        const cx = c * CELL_SIZE + CELL_SIZE / 2;
        const cy = r * CELL_SIZE + CELL_SIZE / 2;
        const g = el("g", {
            class: `pawn pawn-${color}${p.has_item ? " has-item" : ""}${selectedPawnColor === color ? " selected" : ""}`,
            transform: `translate(${cx},${cy})`,
            "data-color": color,
        });
        g.appendChild(el("circle", { r: CELL_SIZE * 0.32 }));
        const label = el("text", {
            x: 0, y: 5, "text-anchor": "middle", "font-size": 14,
            fill: "#0a1422", "font-weight": 700,
        });
        label.textContent = color;
        g.appendChild(label);
        g.addEventListener("click", (e) => {
            e.stopPropagation();
            selectPawn(color);
        });
        pawnLayer.appendChild(g);
    }
    renderMoveHints();
}

function renderMoveHints() {
    // When we have fresh reachable data, own the full overlay: clear it, re-add
    // the exploration anchor (if pending), then paint exactly one blue hint per
    // direction (at the slide endpoint) plus all vortex hints.
    if (!selectedPawnColor || !cachedReachable) return;
    if (!state.pawns[selectedPawnColor] || state.pawns[selectedPawnColor].exited) return;

    clear(overlayLayer);

    // Re-add pending-exploration anchor highlight if the server says one is active.
    if (state.pending_exploration) {
        const [er, ec] = state.pending_exploration.anchor_pos;
        overlayLayer.appendChild(el("rect", {
            x: ec * CELL_SIZE, y: er * CELL_SIZE,
            width: CELL_SIZE, height: CELL_SIZE, class: "move-hint",
        }));
    }

    const moves = cachedReachable.moves || {};
    // One hint per direction: the immediately adjacent open cell (one square away).
    // Clicking moves exactly ONE square in that direction; click again to keep moving.
    for (const dir of DIR_NAMES) {
        const dirMoves = moves[dir] || [];
        if (!dirMoves.length) continue;
        const [r, c] = dirMoves[0];                              // adjacent cell — visual indicator AND destination
        const x = c * CELL_SIZE;
        const y = r * CELL_SIZE;
        const hint = el("rect", {
            x, y, width: CELL_SIZE, height: CELL_SIZE, class: "move-hint",
            "data-r": r, "data-c": c, "data-dir": dir,
        });
        hint.addEventListener("click", (e) => {
            e.stopPropagation();
            emitMove(dir, [r, c]);
        });
        overlayLayer.appendChild(hint);
    }

    // Vortex teleport targets (purple, separate class).
    for (const [r, c] of cachedReachable.vortex || []) {
        const x = c * CELL_SIZE;
        const y = r * CELL_SIZE;
        const hint = el("rect", {
            x, y, width: CELL_SIZE, height: CELL_SIZE, class: "vortex-hint",
            "data-r": r, "data-c": c,
        });
        hint.addEventListener("click", (e) => {
            e.stopPropagation();
            emitMove("VORTEX", [r, c]);
        });
        overlayLayer.appendChild(hint);
    }
}

function selectPawn(color) {
    selectedPawnColor = color;
    cachedReachable = null;
    renderPawns();
    socket.emit("game:reachable", { code, pawn_color: color });
}

// ---------------- Network actions ----------------
function emitMove(direction, target) {
    if (!selectedPawnColor) return;
    socket.emit("game:move", { code, pawn_color: selectedPawnColor, direction, target });
}
function emitExplore() {
    if (!selectedPawnColor) return;
    socket.emit("game:explore", { code, pawn_color: selectedPawnColor });
}
function emitExploreCommit() {
    socket.emit("game:explore_commit", { code });
}

// ---------------- Sidebar / players / actions ----------------

function renderPlayers() {
    if (!state) return;
    clear(playersListEl);
    let mine = null;
    for (const p of state.players) {
        const li = document.createElement("li");
        const name = document.createElement("span");
        name.textContent = p.username + (p.player_id === playerId ? " (you)" : "");
        if (!p.connected) name.style.opacity = 0.5;
        li.appendChild(name);
        if (p.is_host) {
            const b = document.createElement("span");
            b.className = "badge";
            b.textContent = "HOST";
            li.appendChild(b);
        }
        playersListEl.appendChild(li);
        if (p.player_id === playerId) mine = p;
    }
    renderActionCard(mine);
}

function renderActionCard(me) {
    clear(actionCardEl);
    const allActions = [
        { id: "MOVE_N", label: "↑ North", key: "W" },
        { id: "MOVE_E", label: "→ East", key: "D" },
        { id: "MOVE_S", label: "↓ South", key: "S" },
        { id: "MOVE_W", label: "← West", key: "A" },
        { id: "ESCALATOR", label: "↕ Escalator", key: "E" },
        { id: "VORTEX", label: "↺ Vortex", key: "V" },
        { id: "EXPLORE", label: "? Explore", key: "X" },
    ];
    const granted = new Set(me ? me.actions : []);
    for (const a of allActions) {
        const div = document.createElement("div");
        div.className = "action-slot" + (granted.has(a.id) ? " granted" : "");
        const lbl = document.createElement("span");
        lbl.textContent = a.label;
        div.appendChild(lbl);
        const k = document.createElement("kbd");
        k.textContent = a.key;
        div.appendChild(k);
        actionCardEl.appendChild(div);
    }
}

function setPhaseBanner() {
    if (!state) return;
    const p = state.phase;
    if (p === "exploring") phaseBanner.textContent = "Phase 1 — All 4 heroes onto their Item squares simultaneously";
    else if (p === "escaping") phaseBanner.textContent = "Phase 2 — Items stolen! Reach the exits before time runs out";
    else if (p === "waiting") phaseBanner.textContent = "Waiting…";
    else phaseBanner.textContent = "";
}

function renderDeckCounter() {
    if (!state || !deckCounter) return;
    const remaining = state.deck_remaining ?? 0;
    const total = state.scenario?.deck_total ?? 0;
    const placed = Math.max(0, total - remaining);
    deckCounter.textContent = total ? `${remaining} / ${total}` : `${remaining}`;
    deckCounter.title = total
        ? `${placed} of ${total} tiles explored, ${remaining} left in the deck`
        : `${remaining} tiles left in the deck`;
}

// ---------------- Timer ----------------

function startTimerInterpolation() {
    function tick() {
        if (state && state.phase === "finished") {
            renderTimer(state.timer?.remaining_ms ?? 0);
        } else if (!timerPaused) {
            const elapsed = Date.now() - lastServerTimestamp;
            const ms = Math.max(0, lastServerRemainingMs - elapsed);
            renderTimer(ms);
        } else {
            renderTimer(lastServerRemainingMs);
        }
        if (chatUnlockedUntil) {
            const ms = chatUnlockedUntil - Date.now();
            if (ms <= 0) lockChat();
        }
        requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
}

function renderTimer(ms) {
    const total = state?.scenario?.starting_timer_ms ?? 180000;
    const s = Math.max(0, Math.floor(ms / 1000));
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    timerDisplay.textContent = `${mins}:${String(secs).padStart(2, "0")}`;
    timerDisplay.classList.toggle("low", ms < 30000);
    const pct = Math.max(0, Math.min(100, (ms / total) * 100));
    timerFill.style.width = `${pct}%`;
}

// ---------------- Chat ----------------

function unlockChat(until) {
    chatUnlockedUntil = until;
    chatCard.classList.add("unlocked");
    chatInput.disabled = false;
    chatInput.placeholder = "Talk now — locks again on the next action…";
    chatInput.focus();
}

function lockChat() {
    chatUnlockedUntil = null;
    chatCard.classList.remove("unlocked");
    chatInput.disabled = true;
    chatInput.placeholder = "Silent. Chat unlocks when a hero flips the sand timer.";
    chatInput.value = "";
}

chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    socket.emit("game:chat", { code, text });
    chatInput.value = "";
});

socket.on("game:chat_message", (m) => {
    const li = document.createElement("li");
    const a = document.createElement("span");
    a.className = "author";
    a.textContent = m.username + ":";
    li.appendChild(a);
    li.appendChild(document.createTextNode(" " + m.text));
    chatLog.appendChild(li);
    chatLog.scrollTop = chatLog.scrollHeight;
});

socket.on("game:result", (r) => {
    const card = resultOverlay.querySelector(".overlay-card");
    const title = document.getElementById("result-title");
    const reason = document.getElementById("result-reason");
    card.classList.remove("win", "loss");
    if (r.outcome === "win") {
        title.textContent = "Victory!";
        card.classList.add("win");
    } else {
        title.textContent = "Defeated";
        card.classList.add("loss");
    }
    reason.textContent = r.reason || "";
    resultOverlay.classList.remove("hidden");
});

btnReturnLobby.addEventListener("click", () => {
    socket.emit("game:return_to_lobby", { code });
});

socket.on("lobby:redirect_to_lobby", (d) => {
    window.location.href = "/lobby/" + (d.code || code);
});

// ---------------- Snapshot + delta ----------------

socket.on("connect", () => {
    socket.emit("lobby:join", { code, username });
});

socket.on("game:snapshot", (s) => {
    state = s;
    lastServerRemainingMs = s.timer.remaining_ms;
    lastServerTimestamp = Date.now();
    timerPaused = s.timer.paused;
    if (s.chat_unlocked && s.chat_unlocked_until) unlockChat(s.chat_unlocked_until);
    else lockChat();
    cachedReachable = null;
    renderBoard();
    renderPawns();
    renderPlayers();
    setPhaseBanner();
    renderDeckCounter();
});

socket.on("game:delta", (d) => {
    if (!state) {
        socket.emit("game:request_resync", { code });
        return;
    }
    for (const op of d.ops) applyOp(op);
    state.version = d.version;
    cachedReachable = null;
    renderBoard();
    renderPawns();
    renderPlayers();
    setPhaseBanner();
    renderDeckCounter();
    if (selectedPawnColor) {
        socket.emit("game:reachable", { code, pawn_color: selectedPawnColor });
    }
});

socket.on("game:reachable_result", (r) => {
    if (r.pawn_color !== selectedPawnColor) return;
    cachedReachable = r;
    renderMoveHints();  // owns the full overlay refresh
});

socket.on("game:tick", (t) => {
    lastServerRemainingMs = t.remaining_ms;
    lastServerTimestamp = Date.now();
    timerPaused = !!t.paused;
    if (t.chat_unlocked && t.chat_unlocked_until && !chatUnlockedUntil) {
        unlockChat(t.chat_unlocked_until);
    } else if (!t.chat_unlocked && chatUnlockedUntil) {
        lockChat();
    }
});

socket.on("game:error", (e) => {
    flash(e.message);
});

function markCellExplored(pos) {
    if (!pos || !state) return;
    for (const t of state.board.tiles) {
        const [tr, tc] = t.origin;
        const [ar, ac] = pos;
        if (ar >= tr && ar < tr + 4 && ac >= tc && ac < tc + 4) {
            if (!t.explored_anchors) t.explored_anchors = [];
            t.explored_anchors.push([ar, ac]);
            return;
        }
    }
}

function applyOp(op) {
    switch (op.op) {
        case "move_pawn":
            state.pawns[op.color].pos = op.to_pos;
            break;
        case "flip_pawn":
            state.pawns[op.color].has_item = op.has_item;
            break;
        case "pawn_exit":
            state.pawns[op.color].exited = true;
            break;
        case "phase_change":
            state.phase = op.new_phase;
            break;
        case "place_tile": {
            state.board.tiles.push({
                tile_id: op.tile_id,
                origin: op.origin,
                rotation: op.rotation,
                explored_anchors: [],
            });
            // Server attaches the cell definitions for the newly placed tile
            // so the client can render it without a resync.
            if (op.tile_def) {
                state.board.tile_defs[op.tile_def.id] = op.tile_def;
            }
            // Mark BOTH primary doors as spent: the source door (on a previous
            // tile) and the entrance door on the newly placed tile.
            markCellExplored(op.explored_anchor);
            markCellExplored(op.entrance_anchor);
            // Also mark any extra doors that _seal_doors_facing_placed_tiles()
            // sealed server-side (explore arrows pointing into already-occupied
            // cells on the newly placed tile or on adjacent existing tiles).
            for (const p of (op.sealed_anchors || [])) {
                markCellExplored(p);
            }
            state.deck_remaining = Math.max(0, state.deck_remaining - 1);
            break;
        }
        case "timer_flip": {
            // Compute the "live" remaining (interpolated), flip it, and reset the anchor.
            const live = timerPaused ? lastServerRemainingMs : Math.max(0, lastServerRemainingMs - (Date.now() - lastServerTimestamp));
            const total = state.scenario.starting_timer_ms;
            lastServerRemainingMs = Math.max(0, total - live);
            lastServerTimestamp = Date.now();
            break;
        }
        case "use_sand_timer":
            state.used_sand_timers = state.used_sand_timers || [];
            state.used_sand_timers.push(op.pos);
            break;
        case "use_crystal_ball":
            state.used_crystal_balls = state.used_crystal_balls || [];
            state.used_crystal_balls.push(op.pos);
            break;
        case "open_chat":
            unlockChat(Date.now() + op.expires_at_ms);
            break;
        case "close_chat":
            lockChat();
            break;
        case "require_exploration":
            state.pending_exploration = { player_id: op.player_id, anchor_pos: op.anchor_pos, remaining: op.extra_tiles };
            break;
        case "exploration_done":
            state.pending_exploration = null;
            // When no new tile was placed (adjacent slot already occupied), the
            // server still sealed the source and adjacent door anchors.  Apply
            // them here so the arrows disappear on the client too.
            for (const p of (op.sealed_anchors || [])) {
                markCellExplored(p);
            }
            break;
        case "end_game":
            state.phase = "finished";
            state.outcome = op.outcome;
            state.outcome_reason = op.reason;
            break;
    }
}

// ---------------- Input ----------------

document.addEventListener("keydown", (e) => {
    if (document.activeElement && document.activeElement.tagName === "INPUT") return;
    const k = e.key.toLowerCase();
    if (k in DIR_KEYS) {
        // WASD = one square at a time. Click a highlighted square to slide farther.
        const dir = DIR_NAMES[DIR_KEYS[k]];
        if (cachedReachable && cachedReachable.moves && cachedReachable.moves[dir] && cachedReachable.moves[dir].length) {
            const first = cachedReachable.moves[dir][0];
            emitMove(dir, first);
        } else {
            emitMove(dir, null);
        }
        e.preventDefault();
    } else if (k === "e") emitMove("ESCALATOR", null);
    else if (k === "x") {
        if (state && state.pending_exploration && state.pending_exploration.player_id === playerId) {
            emitExploreCommit();
        } else {
            emitExplore();
        }
    }
    else if (k === "1") selectPawn("Y");
    else if (k === "2") selectPawn("P");
    else if (k === "3") selectPawn("G");
    else if (k === "4") selectPawn("O");
});

let flashTimer = null;
function flash(msg) {
    phaseBanner.textContent = msg;
    if (flashTimer) clearTimeout(flashTimer);
    flashTimer = setTimeout(() => setPhaseBanner(), 2200);
}

setInterval(() => {
    if (state && state.pending_exploration && state.pending_exploration.player_id === playerId) {
        phaseBanner.textContent = `Exploration ready — press X to place tile (${state.pending_exploration.remaining || 1} left)`;
    }
}, 500);

startTimerInterpolation();
