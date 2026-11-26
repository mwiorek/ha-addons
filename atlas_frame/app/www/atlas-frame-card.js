// Atlas Frame maps card: which maps are in the rotation, as a matrix of places (rows) by versions (columns).
// Reads sensor.atlas_frame (attributes maps_matrix and maps), writes input_text.atlas_frame_maps as rows such as
// "W1:BL R7:BPT". The add-on copies this file to /config/www; add /local/atlas-frame-card.js as a dashboard
// resource (JavaScript module), then a card:
//   type: custom:atlas-frame-card
//   entity: sensor.atlas_frame          # optional
//   only_installed: false               # optional: start with places that have nothing installed hidden
const VERSION = "0.5.8";
const SHORT = { B: "Map", P: "Pop.", T: "Temp.", L: "Live", S: "Snow", G: "Econ.", C: "GDP/p.", U: "Land", Z: "Clock" };

class AtlasFrameCard extends HTMLElement {
  setConfig(config) {
    this._config = { entity: "sensor.atlas_frame", only_installed: false, ...config };
    this._only = !!this._config.only_installed;
    this._pending = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    const st = hass.states[this._config.entity];
    const key = st ? st.last_updated + JSON.stringify(st.attributes.maps || []) : "none";
    const helper = st && st.attributes.maps_matrix && hass.states[st.attributes.maps_matrix.helper];
    const full = key + (helper ? helper.state : "");
    if (full === this._key) return;          // redraw only when the sensor or helper changes
    this._key = full;
    this._render();
  }

  getCardSize() { return 9; }
  static getStubConfig() { return { entity: "sensor.atlas_frame" }; }

  _chosen(st) {
    const now = new Set(st.attributes.maps || []);
    if (this._pending) {
      const same = this._pending.size === now.size && [...this._pending].every((m) => now.has(m));
      if (same || Date.now() - this._pendingAt > 15000) this._pending = null;
      else return new Set(this._pending);
    }
    return now;
  }

  _render() {
    const root = this.shadowRoot;
    const st = this._hass && this._hass.states[this._config.entity];
    if (!st || !st.attributes.maps_matrix) {
      root.innerHTML = `${STYLE}<ha-card header="Atlas Frame maps"><div class="note">
        ${st ? "This Atlas Frame add-on is too old for the card: update it to " + VERSION + " or later."
             : `<b>${this._config.entity}</b> not found: start the Atlas Frame add-on.`}</div></ha-card>`;
      return;
    }
    const mx = st.attributes.maps_matrix;
    const chosen = this._chosen(st);
    const versions = Object.keys(mx.versions);
    const rows = mx.places.filter((p) => !this._only ||
      Object.values(p.cells).some((c) => c.status !== "not installed"));
    const inMatrix = new Set(mx.places.flatMap((p) => Object.values(p.cells).map((c) => c.map)));
    const cells = mx.places.flatMap((p) => Object.values(p.cells));
    const picked = cells.filter((c) => chosen.has(c.map));
    const waiting = picked.filter((c) => c.status === "not installed").length;
    const extra = [...chosen].filter((m) => !inMatrix.has(m));
    const helper = this._hass.states[mx.helper];

    const head = versions.map((v) =>
      `<th><button class="col" data-col="${v}" title="${mx.versions[v]}: all on or off">${SHORT[v] || v}</button></th>`).join("");
    const body = rows.map((p) => {
      const tds = versions.map((v) => {
        const c = p.cells[v];
        if (!c) return `<td class="none"></td>`;
        const on = chosen.has(c.map), have = c.status !== "not installed";
        const tip = `${c.map} ${p.name}, ${mx.versions[v].toLowerCase()}: ${c.status}${on ? ", in the rotation" : ""}`;
        return `<td><button class="cell ${on ? "on" : "off"} ${have ? "have" : "missing"}" data-map="${c.map}"
          title="${tip}" aria-label="${tip}" aria-pressed="${on}">${on ? CHECK : ""}</button></td>`;
      }).join("");
      return `<tr><th class="place"><button class="row" data-row="${p.id}" title="${p.name}: all on or off">
        <span class="id">${p.id}</span> ${p.name}</button></th>${tds}</tr>`;
    }).join("");

    root.innerHTML = `${STYLE}<ha-card>
      <div class="top">
        <div class="title">Atlas Frame maps</div>
        <label class="only"><input type="checkbox" ${this._only ? "checked" : ""}> Only installed</label>
      </div>
      <div class="sum">${picked.length + extra.length} in the rotation${waiting ? ` · <span class="warn">${waiting} not installed yet</span>, skipped until they are` : ""}</div>
      ${helper ? "" : `<div class="note err"><b>${mx.helper}</b> not found: add the Atlas Frame helpers package (DOCS, Controls).</div>`}
      <div class="wrap"><table>
        <thead><tr><th></th>${head}</tr></thead>
        <tbody>${body}</tbody>
      </table></div>
      ${extra.length ? `<div class="note">Also in the rotation, not in the matrix: ${extra.join(", ")}</div>` : ""}
      <div class="legend">
        <span><i class="cell on have">${CHECK}</i> in the rotation</span>
        <span><i class="cell on missing">${CHECK}</i> chosen, not installed</span>
        <span><i class="cell off have"></i> installed</span>
        <span><i class="cell off missing"></i> not installed</span>
      </div>
      <div class="msg" role="status"></div>
    </ha-card>`;

    root.querySelector(".only input").addEventListener("change", (e) => {
      this._only = e.target.checked; this._render();
    });
    root.querySelectorAll("button.cell").forEach((b) => b.addEventListener("click", () => {
      const next = new Set(chosen);
      next.has(b.dataset.map) ? next.delete(b.dataset.map) : next.add(b.dataset.map);
      this._write(next, mx, extra);
    }));
    const toggleAll = (list) => {
      const next = new Set(chosen);
      const all = list.every((m) => next.has(m));
      list.forEach((m) => (all ? next.delete(m) : next.add(m)));
      this._write(next, mx, extra);
    };
    root.querySelectorAll("button.row").forEach((b) => b.addEventListener("click", () => {
      const p = mx.places.find((x) => x.id === b.dataset.row);
      toggleAll(Object.values(p.cells).map((c) => c.map));
    }));
    root.querySelectorAll("button.col").forEach((b) => b.addEventListener("click", () => {
      toggleAll(rows.map((p) => p.cells[b.dataset.col]).filter(Boolean).map((c) => c.map));
    }));
  }

  _say(text) {
    const m = this.shadowRoot.querySelector(".msg");
    if (m) m.textContent = text;
  }

  _write(next, mx, extra) {
    const versions = Object.keys(mx.versions);
    const parts = mx.places.map((p) => {
      const letters = versions.filter((v) => p.cells[v] && next.has(p.cells[v].map)).join("");
      return letters ? `${p.id}:${letters}` : null;
    }).filter(Boolean);
    const keep = extra.filter((m) => next.has(m));
    const value = [...parts, ...keep].join(" ");
    if (!value) { this._say("Keep at least one map in the rotation."); return; }
    const helper = this._hass.states[mx.helper];
    if (!helper) { this._say(`${mx.helper} not found.`); return; }
    const max = Number(helper.attributes.max || 255);
    if (value.length > max) { this._say(`Too many rows for ${mx.helper} (${value.length} of ${max} characters).`); return; }
    this._pending = next; this._pendingAt = Date.now();
    this._hass.callService("input_text", "set_value", { entity_id: mx.helper, value })
      .catch((e) => { this._pending = null; this._render(); this._say(`Could not save: ${e.message || e}`); });
    this._key = null; this._render();
  }
}

const CHECK = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/></svg>`;
const STYLE = `<style>
  ha-card { padding: 12px 12px 10px; }
  .top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .title { font-size: 1.15em; font-weight: 500; }
  .only { font-size: .85em; color: var(--secondary-text-color); display: flex; align-items: center; gap: 4px; cursor: pointer; }
  .sum { font-size: .9em; color: var(--secondary-text-color); margin: 2px 0 8px; }
  .warn { color: var(--warning-color, #c77700); }
  .wrap { overflow-x: auto; container-type: inline-size; }
  table { border-collapse: collapse; width: 100%; }
  th, td { padding: 2px; text-align: center; }
  thead th { font-size: .78em; font-weight: 500; color: var(--secondary-text-color); }
  th.place { text-align: left; white-space: nowrap; font-weight: 400; }
  button { font: inherit; color: inherit; background: none; border: 0; cursor: pointer; border-radius: 6px; }
  button.row, button.col { padding: 4px 6px; width: 100%; text-align: inherit; }
  button.row:hover, button.col:hover { background: var(--secondary-background-color); }
  .id { display: inline-block; min-width: 2.6em; color: var(--secondary-text-color); font-size: .85em; }
  .cell { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px;
          border-radius: 7px; box-sizing: border-box; vertical-align: middle; }
  .cell svg { width: 18px; height: 18px; fill: currentColor; }
  .cell.on.have { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .cell.on.missing { border: 2px solid var(--warning-color, #c77700); color: var(--warning-color, #c77700); }
  .cell.off.have { border: 2px solid var(--secondary-text-color); opacity: .7; }
  .cell.off.missing { border: 2px dashed var(--divider-color, #8886); }
  button.cell:hover { outline: 2px solid var(--primary-color); outline-offset: 1px; }
  td.none { opacity: 0; }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: .8em; color: var(--secondary-text-color); margin-top: 10px; }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .legend .cell { width: 18px; height: 18px; border-radius: 5px; }
  .legend .cell svg { width: 12px; height: 12px; }
  .note { font-size: .85em; color: var(--secondary-text-color); margin: 8px 0; }
  .err { color: var(--error-color, #db4437); }
  .msg { font-size: .85em; color: var(--error-color, #db4437); min-height: 1em; margin-top: 4px; }
  @container (max-width: 420px) {        /* phones: no ids, smaller cells, the whole matrix in view */
    th.place { font-size: .86em; }
    .id { display: none; }
    th, td { padding: 1px; }
    thead th { font-size: .66em; }
    button.row { padding: 4px 2px; }
    button.col { padding: 4px 0; }
    td .cell { width: 24px; height: 24px; }
  }
</style>`;

customElements.get("atlas-frame-card") || customElements.define("atlas-frame-card", AtlasFrameCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "atlas-frame-card"))
  window.customCards.push({ type: "atlas-frame-card", name: "Atlas Frame maps",
    description: "Which Atlas Frame maps are in the rotation, places by versions, and which are installed." });
console.info(`atlas-frame-card ${VERSION}`);
