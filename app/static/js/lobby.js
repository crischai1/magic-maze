const root = document.querySelector(".lobby");
const code = root.dataset.code;
const username = root.dataset.username;
const playerId = root.dataset.playerId;

const socket = io("/game", { transports: ["websocket", "polling"] });

const playerListEl = document.getElementById("player-list");
const startBtn = document.getElementById("start-btn");
const statusEl = document.getElementById("lobby-status");
const scenarioSelect = document.getElementById("scenario-select");
const scenarioDescEl = document.getElementById("scenario-desc");

const scenarioDescMap = {};
document.querySelectorAll(".scenario-data div").forEach((d) => {
    scenarioDescMap[d.dataset.id] = d.dataset.desc;
});

function updateScenarioDesc() {
    scenarioDescEl.textContent = scenarioDescMap[scenarioSelect.value] || "";
}
scenarioSelect.addEventListener("change", () => {
    updateScenarioDesc();
    socket.emit("lobby:select_scenario", { code, scenario_id: parseInt(scenarioSelect.value, 10) });
});
updateScenarioDesc();

startBtn.addEventListener("click", () => {
    socket.emit("lobby:start", { code });
});

socket.on("connect", () => {
    socket.emit("lobby:join", { code, username });
});

socket.on("lobby:state", (state) => {
    playerListEl.innerHTML = "";
    let isHost = false;
    state.players.forEach((p) => {
        const li = document.createElement("li");
        if (!p.connected) li.classList.add("offline");
        const name = document.createElement("span");
        name.textContent = p.username + (p.player_id === playerId ? " (you)" : "");
        li.appendChild(name);
        if (p.is_host) {
            const badge = document.createElement("span");
            badge.className = "badge";
            badge.textContent = "HOST";
            li.appendChild(badge);
            if (p.player_id === playerId) isHost = true;
        }
        playerListEl.appendChild(li);
    });
    scenarioSelect.value = String(state.scenario_id);
    updateScenarioDesc();
    scenarioSelect.disabled = !isHost;
    startBtn.disabled = !isHost;
    startBtn.textContent = isHost
        ? `Start (${state.players.length} player${state.players.length === 1 ? "" : "s"})`
        : "Waiting for host…";
});

socket.on("lobby:error", (e) => {
    statusEl.textContent = e.message;
});

socket.on("lobby:redirect_to_game", (d) => {
    window.location.href = `/game/${d.code}`;
});
