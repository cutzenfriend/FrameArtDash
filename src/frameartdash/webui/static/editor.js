// FrameArtDash card editor: place live cards on the background by drag and drop.
(() => {
  const E = { schema: null, layout: null, sel: null, entities: null, mdi: null, snap: true, types: {}, saveTimer: null,
    reloadTimer: null, frame: null, ready: false };
  const el = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const round = (v) => Math.round(v * 100) / 100;
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);

  async function req(path, opts = {}) {
    const res = await fetch(path, { credentials: "same-origin", ...opts });
    if (res.status === 401) { location.href = "/login"; throw new Error("not logged in"); }
    const body = (res.headers.get("content-type") || "").includes("json") ? await res.json() : null;
    if (!res.ok) throw new Error((body && body.error) || res.statusText);
    return body;
  }

  function status(text, cls = "") {
    const s = el("edStatus"); if (!s) return;
    s.textContent = text; s.className = "ed-status " + cls;
  }

  // -- icons ----------------------------------------------------------------------
  async function loadMdi() {
    if (!E.mdi) E.mdi = await req("/static/mdi.json");
    return E.mdi;
  }
  const glyph = (name) => {
    const code = E.mdi && E.mdi[String(name || "").replace(/^mdi:/, "")];
    return code ? String.fromCodePoint(code) : "";
  };

  // -- init -------------------------------------------------------------------------
  async function init() {
    if (E.ready) { reloadFrame(); return; }
    E.ready = true;
    const [schema, layout] = await Promise.all([req("/api/cards/schema"), req("/api/cards")]);
    E.schema = schema; E.layout = layout;
    for (const t of schema.types) E.types[t.type] = t;
    loadMdi().then(() => { renderSide(); renderAddMenu(); }).catch(() => {});
    loadEntities();
    renderAddMenu();
    setupStage();
    renderOverlay();
    renderSide();
    reloadFrame();
  }

  async function loadEntities(fresh = false) {
    try {
      E.entities = (await req("/api/ha/entities" + (fresh ? "?fresh=1" : ""))).entities;
      E.entityMap = Object.fromEntries(E.entities.map((e) => [e.id, e]));
      renderSide();
    } catch (e) {
      E.entities = []; E.entityMap = {};
      status("Home Assistant: " + e.message, "bad");
    }
  }

  function renderAddMenu() {
    const sel = el("edAdd");
    const groups = {};
    for (const t of E.schema.types) (groups[t.group] = groups[t.group] || []).push(t);
    sel.innerHTML = `<option value="">＋ Add card…</option>` + Object.entries(groups).map(([g, ts]) =>
      `<optgroup label="${esc(g)}">${ts.map((t) => `<option value="${t.type}">${esc(t.label)}</option>`).join("")}</optgroup>`).join("");
    sel.onchange = () => { if (sel.value) addCard(sel.value); sel.value = ""; };
  }

  // -- stage ------------------------------------------------------------------------
  function setupStage() {
    const stage = el("edStage");
    new ResizeObserver(scaleFrames).observe(stage);
    stage.addEventListener("pointerdown", (ev) => {
      if (ev.target === stage || ev.target === el("edOverlay")) { select(null); stage.focus(); }
    });
    stage.addEventListener("keydown", onKey);
    el("edSnap").onchange = (e) => (E.snap = e.target.checked);
    el("edRefresh").onclick = () => { loadEntities(true); reloadFrame(); };
  }

  function scaleFrames() {
    const stage = el("edStage");
    const s = stage.clientWidth / 1920;
    stage.querySelectorAll("iframe").forEach((f) => (f.style.transform = `scale(${s})`));
  }

  function reloadFrame() {
    const stage = el("edStage");
    const next = document.createElement("iframe");
    next.className = "loading";
    next.setAttribute("tabindex", "-1");
    next.src = "/canvas.html?t=" + Date.now();
    next.onload = () => {
      stage.querySelectorAll("iframe").forEach((f) => f !== next && f.remove());
      next.classList.remove("loading");
      E.frame = next;
      syncFrame();
    };
    stage.insertBefore(next, el("edOverlay"));
    scaleFrames();
  }
  const scheduleReload = () => { clearTimeout(E.reloadTimer); E.reloadTimer = setTimeout(reloadFrame, 700); };

  function frameCard(id) {
    try { return E.frame && E.frame.contentDocument.querySelector(`[data-card="${CSS.escape(id)}"]`); } catch { return null; }
  }
  function syncFrame() {
    for (const c of E.layout.cards) placeEl(frameCard(c.id), c);
  }
  function placeEl(node, c) {
    if (!node) return;
    node.style.left = c.x + "%"; node.style.top = c.y + "%"; node.style.width = c.w + "%"; node.style.height = c.h + "%";
  }

  function renderOverlay() {
    const ov = el("edOverlay");
    ov.innerHTML = E.layout.cards.length ? "" : `<div class="ed-empty">Add your first card with <b>＋ Add card</b> above.</div>`;
    E.layout.cards.forEach((c) => {
      const box = document.createElement("div");
      box.className = "ed-box" + (c.id === E.sel ? " sel" : "");
      box.dataset.id = c.id;
      placeEl(box, c);
      const label = E.types[c.type] ? E.types[c.type].label : c.type;
      box.innerHTML = `<div class="tag">${esc(label)}</div>` + ["nw", "n", "ne", "e", "se", "s", "sw", "w"].map((h) => `<div class="ed-h" data-h="${h}"></div>`).join("");
      box.addEventListener("pointerdown", (ev) => startDrag(ev, c.id, ev.target.dataset.h || null));
      ov.appendChild(box);
    });
  }

  // -- drag & snap ------------------------------------------------------------------
  function clearGuides() { el("edStage").querySelectorAll(".ed-guide").forEach((g) => g.remove()); }
  function guide(kind, pos) {
    const g = document.createElement("div");
    g.className = "ed-guide " + kind;
    g.style[kind === "v" ? "left" : "top"] = pos + "%";
    el("edStage").appendChild(g);
  }

  function snapAxis(value, size, candidates, threshold, edges) {
    // edges: which edges of the moving box may snap (start, center, end)
    let best = null;
    for (const [edge, off] of edges.map((e) => [e, e === "start" ? 0 : e === "end" ? size : size / 2])) {
      for (const c of candidates) {
        const d = c - (value + off);
        if (Math.abs(d) <= threshold && (!best || Math.abs(d) < Math.abs(best.d))) best = { d, line: c };
      }
    }
    return best;
  }

  function startDrag(ev, id, handle) {
    ev.preventDefault(); ev.stopPropagation();
    const card = E.layout.cards.find((c) => c.id === id);
    if (!card) return;
    select(card.id);
    el("edStage").focus();
    const stage = el("edStage").getBoundingClientRect();
    const start = { x: ev.clientX, y: ev.clientY, card: { ...card } };
    const others = E.layout.cards.filter((c) => c.id !== card.id);
    const xs = [0, 50, 100, ...others.flatMap((c) => [c.x, c.x + c.w, c.x + c.w / 2])];
    const ys = [0, 50, 100, ...others.flatMap((c) => [c.y, c.y + c.h, c.y + c.h / 2])];
    const thx = 8 / stage.width * 100, thy = 8 / stage.height * 100;
    const box = el("edOverlay").querySelector(`[data-id="${CSS.escape(card.id)}"]`);
    const target = ev.target;
    target.setPointerCapture(ev.pointerId);

    const move = (e) => {
      const dx = (e.clientX - start.x) / stage.width * 100;
      const dy = (e.clientY - start.y) / stage.height * 100;
      const o = start.card;
      let { x, y, w, h } = o;
      clearGuides();
      if (!handle) {
        x = clamp(o.x + dx, 0, 100 - o.w); y = clamp(o.y + dy, 0, 100 - o.h);
        if (E.snap && !e.altKey) {
          const sx = snapAxis(x, w, xs, thx, ["start", "center", "end"]);
          const sy = snapAxis(y, h, ys, thy, ["start", "center", "end"]);
          if (sx) { x += sx.d; guide("v", sx.line); }
          if (sy) { y += sy.d; guide("h", sy.line); }
        }
      } else {
        if (handle.includes("e")) w = clamp(o.w + dx, 2, 100 - o.x);
        if (handle.includes("s")) h = clamp(o.h + dy, 2, 100 - o.y);
        if (handle.includes("w")) { x = clamp(o.x + dx, 0, o.x + o.w - 2); w = o.x + o.w - x; }
        if (handle.includes("n")) { y = clamp(o.y + dy, 0, o.y + o.h - 2); h = o.y + o.h - y; }
        if (E.snap && !e.altKey) {
          if (handle.includes("e")) { const s = snapAxis(x, w, xs, thx, ["end"]); if (s) { w += s.d; guide("v", s.line); } }
          if (handle.includes("s")) { const s = snapAxis(y, h, ys, thy, ["end"]); if (s) { h += s.d; guide("h", s.line); } }
          if (handle.includes("w")) { const s = snapAxis(x, w, xs, thx, ["start"]); if (s) { x += s.d; w -= s.d; guide("v", s.line); } }
          if (handle.includes("n")) { const s = snapAxis(y, h, ys, thy, ["start"]); if (s) { y += s.d; h -= s.d; guide("h", s.line); } }
        }
      }
      Object.assign(card, { x: round(x), y: round(y), w: round(w), h: round(h) });
      placeEl(box, card); placeEl(frameCard(card.id), card);
      renderGeo();
    };
    const up = () => {
      target.removeEventListener("pointermove", move);
      target.removeEventListener("pointerup", up);
      clearGuides();
      if (card.x !== start.card.x || card.y !== start.card.y || card.w !== start.card.w || card.h !== start.card.h) save();
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", up);
  }

  function onKey(ev) {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
    const card = current();
    if (ev.key === "Escape") { select(null); return; }
    if (!card) return;
    const step = ev.shiftKey ? 2 : 0.5;
    const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (moves[ev.key]) {
      ev.preventDefault();
      card.x = round(clamp(card.x + moves[ev.key][0], 0, 100 - card.w));
      card.y = round(clamp(card.y + moves[ev.key][1], 0, 100 - card.h));
      placeEl(el("edOverlay").querySelector(`[data-id="${CSS.escape(card.id)}"]`), card);
      placeEl(frameCard(card.id), card);
      renderGeo(); save(false);
    } else if (ev.key === "Delete" || ev.key === "Backspace") {
      ev.preventDefault(); removeCard(card.id);
    } else if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "d") {
      ev.preventDefault(); duplicate(card.id);
    }
  }

  // -- layout operations ---------------------------------------------------------------
  const current = () => E.layout.cards.find((c) => c.id === E.sel) || null;
  const newId = () => Math.random().toString(16).slice(2, 10);

  function select(id) {
    E.sel = id;
    el("edOverlay").querySelectorAll(".ed-box").forEach((b) => b.classList.toggle("sel", b.dataset.id === id));
    renderSide();
  }

  function addCard(type) {
    const t = E.types[type];
    const [w, h] = t.size;
    const card = { id: newId(), type, x: round((100 - w) / 2), y: round((100 - h) / 2), w, h, options: {} };
    E.layout.cards.push(card);
    E.sel = card.id;
    renderOverlay(); renderSide();
    save(true);
  }

  function duplicate(id) {
    const src = E.layout.cards.find((c) => c.id === id);
    if (!src) return;
    const card = JSON.parse(JSON.stringify(src));
    card.id = newId();
    card.x = round(clamp(card.x + 2, 0, 100 - card.w)); card.y = round(clamp(card.y + 2, 0, 100 - card.h));
    E.layout.cards.push(card); E.sel = card.id;
    renderOverlay(); renderSide(); save(true);
  }

  function removeCard(id) {
    E.layout.cards = E.layout.cards.filter((c) => c.id !== id);
    E.sel = null;
    renderOverlay(); renderSide(); save(true);
  }

  function reorder(id, dir) {
    const i = E.layout.cards.findIndex((c) => c.id === id);
    const j = dir === "front" ? E.layout.cards.length - 1 : 0;
    if (i < 0 || i === j) return;
    const [card] = E.layout.cards.splice(i, 1);
    if (dir === "front") E.layout.cards.push(card); else E.layout.cards.unshift(card);
    renderOverlay(); save(true);
  }

  function save(reload = false) {
    clearTimeout(E.saveTimer);
    status("Saving…");
    E.saveTimer = setTimeout(async () => {
      try {
        const saved = await req("/api/cards", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(E.layout) });
        // Keep local object identity for the selected card, take normalized values.
        E.layout = saved;
        status("Saved", "ok");
        if (reload) { renderOverlay(); renderSide(); scheduleReload(); }
      } catch (e) { status(e.message, "bad"); }
    }, reload ? 150 : 400);
  }

  // -- side panel -----------------------------------------------------------------------
  function entityOptions(domains) {
    const list = (E.entities || []).filter((e) => !domains || !domains.length || domains.includes(e.id.split(".")[0]));
    return list.map((e) => `<option value="${esc(e.id)}">${esc(e.name)} · ${esc(e.state)}${e.unit ? " " + esc(e.unit) : ""}</option>`).join("");
  }
  function liveText(id) {
    if (!id) return "";
    const e = E.entityMap && E.entityMap[id];
    if (!E.entityMap || !E.entities.length) return "";
    return e ? `<div class="live">${esc(e.name)}: ${esc(e.state)} ${esc(e.unit || "")}</div>` : `<div class="live bad">Entity not found</div>`;
  }

  function fieldHtml(opt, value, scope) {
    const id = `ed_${scope}_${opt.key}`;
    const help = opt.help ? `<div class="help">${esc(opt.help)}</div>` : "";
    const data = `data-scope="${scope}" data-key="${opt.key}" data-kind="${opt.kind}"`;
    let input;
    switch (opt.kind) {
      case "bool":
        return `<div class="f"><label class="switch"><input type="checkbox" id="${id}" ${data} ${value ? "checked" : ""}> ${esc(opt.label)}</label>${help}</div>`;
      case "select":
        input = `<select id="${id}" ${data}>${opt.options.map((o) => `<option value="${esc(o)}" ${String(value) === o ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
        break;
      case "textarea":
        input = `<textarea id="${id}" ${data}>${esc(value)}</textarea>`;
        break;
      case "number":
        input = `<input type="number" step="any" id="${id}" ${data} value="${esc(value)}">`;
        break;
      case "color":
        input = `<div class="row2"><input type="color" value="${esc(/^#[0-9a-f]{6}$/i.test(value) ? value : "#e3c27a")}" data-mirror="${id}">
                 <input type="text" id="${id}" ${data} value="${esc(value)}" placeholder="theme accent"></div>`;
        break;
      case "icon":
        input = `<div class="row2"><span class="icon-prev" id="${id}_prev">${glyph(value)}</span>
                 <input type="text" id="${id}" ${data} value="${esc(value)}" placeholder="e.g. thermometer"></div>`;
        break;
      case "entity":
        input = `<input type="text" id="${id}" ${data} value="${esc(value)}" list="${id}_dl" placeholder="search entity…" autocomplete="off">
                 <datalist id="${id}_dl">${entityOptions(opt.domains)}</datalist>${liveText(value)}`;
        break;
      case "entities": {
        const items = (value || []).map((v, i) => `<div class="chip"><span title="${esc(v)}">${esc((E.entityMap && E.entityMap[v] && E.entityMap[v].name) || v)}</span>
          <button type="button" data-move="${i}" title="Move up">↑</button><button type="button" data-remove="${i}" title="Remove">✕</button></div>`).join("");
        input = `<div class="chips" data-chips="${opt.key}">${items}</div>
                 <input type="text" id="${id}" data-scope="${scope}" data-key="${opt.key}" data-kind="entities-add" list="${id}_dl" placeholder="add entity…" autocomplete="off">
                 <datalist id="${id}_dl">${entityOptions(opt.domains)}</datalist>`;
        break;
      }
      default:
        input = `<input type="text" id="${id}" ${data} value="${esc(value)}">`;
    }
    return `<div class="f"><label for="${id}">${esc(opt.label)}</label>${input}${help}</div>`;
  }

  function renderGeo() {
    const card = current(); if (!card) return;
    for (const k of ["x", "y", "w", "h"]) { const i = el("ed_geo_" + k); if (i && document.activeElement !== i) i.value = card[k]; }
  }

  function renderSide() {
    const side = el("edSide");
    if (!side || !E.layout) return;
    const card = current();
    if (!card) {
      const s = E.layout.style;
      side.innerHTML = `<h3>Layout</h3><p class="desc">Select a card to edit it, or drag it on the canvas. These settings apply to all cards.</p>
        ${E.schema.style.map((o) => fieldHtml(o, s[o.key], "style")).join("")}
        <h4>Cards (${E.layout.cards.length})</h4>
        <div class="ed-list">${[...E.layout.cards].reverse().map((c) => {
          const t = E.types[c.type] || { label: c.type, icon: "card" };
          const what = c.options.title || c.options.name || c.options.entity || (c.options.entities || []).join(", ") || "";
          return `<button type="button" data-select="${esc(c.id)}"><i class="mdi">${glyph(t.icon)}</i>${esc(t.label)}<small>${esc(String(what).slice(0, 28))}</small></button>`;
        }).join("") || `<span class="desc">No cards yet.</span>`}</div>`;
    } else {
      const t = E.types[card.type];
      side.innerHTML = `<h3><span class="icon-prev" style="width:auto;line-height:1">${glyph(t.icon)}</span>${esc(t.label)}</h3>
        <p class="desc">${esc(t.description || "")}</p>
        <div class="ed-actions">
          <button class="btn small" type="button" data-act="dup">Duplicate</button>
          <button class="btn small" type="button" data-act="front">To front</button>
          <button class="btn small" type="button" data-act="back">To back</button>
          <button class="btn small danger" type="button" data-act="del">Delete</button>
          <button class="btn small ghost" type="button" data-act="done">Done</button>
        </div>
        <h4>Position (% of the picture)</h4>
        <div class="geo">${["x", "y", "w", "h"].map((k) => `<div><label>${{ x: "Left", y: "Top", w: "Width", h: "Height" }[k]}</label>
          <input type="number" step="0.5" id="ed_geo_${k}" data-geo="${k}" value="${card[k]}"></div>`).join("")}</div>
        <h4>Content</h4>
        ${t.options.map((o) => fieldHtml(o, card.options[o.key], "card")).join("")}
        <h4>Appearance</h4>
        ${E.schema.common.map((o) => fieldHtml(o, card.options[o.key], "card")).join("")}`;
    }
    bindSide(side);
  }

  function bindSide(side) {
    side.querySelectorAll("[data-select]").forEach((b) => (b.onclick = () => select(b.dataset.select)));
    side.querySelectorAll("[data-act]").forEach((b) => (b.onclick = () => {
      const card = current(); if (!card) return;
      ({ dup: () => duplicate(card.id), front: () => reorder(card.id, "front"), back: () => reorder(card.id, "back"),
         del: () => removeCard(card.id), done: () => select(null) })[b.dataset.act]();
    }));
    side.querySelectorAll("[data-geo]").forEach((i) => (i.onchange = () => {
      const card = current(); const k = i.dataset.geo; const v = parseFloat(i.value);
      if (!card || Number.isNaN(v)) return;
      card[k] = round(v);
      card.w = clamp(card.w, 2, 100); card.h = clamp(card.h, 2, 100);
      card.x = clamp(card.x, 0, 100 - card.w); card.y = clamp(card.y, 0, 100 - card.h);
      placeEl(el("edOverlay").querySelector(`[data-id="${CSS.escape(card.id)}"]`), card);
      placeEl(frameCard(card.id), card); renderGeo(); save(false);
    }));
    side.querySelectorAll("[data-mirror]").forEach((c) => (c.oninput = () => {
      const t = el(c.dataset.mirror); t.value = c.value; t.dispatchEvent(new Event("change"));
    }));
    side.querySelectorAll("[data-key]").forEach((i) => {
      const evt = i.dataset.kind === "bool" || i.tagName === "SELECT" ? "change" : "change";
      i.addEventListener(evt, () => onField(i));
      if (i.dataset.kind === "icon") i.addEventListener("input", () => { const p = el(i.id + "_prev"); if (p) p.textContent = glyph(i.value); });
    });
    side.querySelectorAll("[data-chips]").forEach((box) => {
      const key = box.dataset.chips;
      box.querySelectorAll("[data-remove]").forEach((b) => (b.onclick = () => {
        const list = current().options[key]; list.splice(+b.dataset.remove, 1); renderSide(); save(true);
      }));
      box.querySelectorAll("[data-move]").forEach((b) => (b.onclick = () => {
        const list = current().options[key]; const i = +b.dataset.move;
        if (i > 0) { [list[i - 1], list[i]] = [list[i], list[i - 1]]; renderSide(); save(true); }
      }));
    });
  }

  function onField(input) {
    const { scope, key, kind } = input.dataset;
    let value = input.type === "checkbox" ? input.checked : input.value;
    if (kind === "number") value = value === "" ? "" : Number(value);
    if (kind === "icon" || kind === "entity") value = String(value).trim();
    if (scope === "style") {
      E.layout.style[key] = value;
    } else {
      const card = current(); if (!card) return;
      if (kind === "entities-add") {
        const v = String(value).trim();
        if (!v) return;
        card.options[key] = [...(card.options[key] || []), v];
        input.value = "";
        renderSide();
      } else {
        card.options[key] = value;
        if (kind === "entity") renderSide();
      }
    }
    save(true);
  }

  window.FAD_editor = { init, reload: reloadFrame };
})();
