// Road-map editor: draw road / roadside / zebra-crossing zones and lanes (with a
// travel-direction arrow) over a frame from a fixed camera. Points are kept
// normalized to 0..1 of the frame, matching event_engine.Scene.
(() => {
  const cfg = window.SCENE_EDITOR;
  const TYPES = {
    road: { label: "Road area", fill: "rgba(170,170,170,0.28)", stroke: "#c4c4c4" },
    roadside: { label: "Roadside / footpath", fill: "rgba(80,200,110,0.26)", stroke: "#50c86e" },
    crossing: { label: "Zebra crossing", fill: "rgba(255,255,255,0.32)", stroke: "#ffffff" },
    lane: { label: "Lane", fill: "rgba(0,200,255,0.14)", stroke: "#00c8ff" },
  };
  const CLOSE_RADIUS_PX = 12;

  const canvas = document.getElementById("scene-canvas");
  const ctx = canvas.getContext("2d");
  const hint = document.getElementById("editor-hint");
  const list = document.getElementById("shape-list");
  const statusEl = document.getElementById("save-status");
  const nameInput = document.getElementById("scene-name");
  const saveBtn = document.getElementById("save-btn");
  const toolButtons = document.querySelectorAll("[data-tool]");

  const state = {
    zones: (cfg.scene.zones || []).map(z => ({ type: z.type, points: z.points })),
    lanes: (cfg.scene.lanes || []).map(l => ({ name: l.name, points: l.points, direction: l.direction || null })),
    tool: "road",
    draft: [],             // corners of the polygon being drawn
    directionLane: null,   // lane waiting for its direction arrow
    directionDraft: [],
    highlight: null,       // {kind: "zone"|"lane", index}
    mouse: null,
    dirty: false,
  };

  const img = new Image();
  img.onload = () => { resize(); renderList(); updateHint(); };
  img.src = cfg.frameUrl;

  // --- geometry ---------------------------------------------------------------
  const size = () => ({ w: canvas.clientWidth, h: canvas.clientHeight });
  const toPx = p => [p[0] * size().w, p[1] * size().h];
  function toNorm(evt) {
    const r = canvas.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (evt.clientX - r.left) / r.width));
    const y = Math.min(1, Math.max(0, (evt.clientY - r.top) / r.height));
    return [Math.round(x * 1e5) / 1e5, Math.round(y * 1e5) / 1e5];
  }
  function distPx(a, b) {
    const [ax, ay] = toPx(a), [bx, by] = toPx(b);
    return Math.hypot(ax - bx, ay - by);
  }

  function resize() {
    const wrap = canvas.parentElement;
    const w = wrap.clientWidth;
    const h = Math.round(w * img.naturalHeight / img.naturalWidth);
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }
  window.addEventListener("resize", resize);

  // --- drawing ----------------------------------------------------------------
  function polygon(points, style, emphasized) {
    if (points.length < 2) return;
    ctx.beginPath();
    points.forEach((p, i) => { const [x, y] = toPx(p); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.closePath();
    ctx.fillStyle = style.fill;
    ctx.fill();
    ctx.lineWidth = emphasized ? 4 : 2;
    ctx.strokeStyle = style.stroke;
    ctx.stroke();
  }

  function arrow(from, to, color) {
    const [x0, y0] = toPx(from), [x1, y1] = toPx(to);
    const angle = Math.atan2(y1 - y0, x1 - x0);
    const head = 16;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x1 - head * Math.cos(angle - 0.45), y1 - head * Math.sin(angle - 0.45));
    ctx.lineTo(x1 - head * Math.cos(angle + 0.45), y1 - head * Math.sin(angle + 0.45));
    ctx.closePath();
    ctx.fill();
  }

  function label(text, points, color) {
    const cx = points.reduce((s, p) => s + p[0], 0) / points.length;
    const cy = points.reduce((s, p) => s + p[1], 0) / points.length;
    const [x, y] = toPx([cx, cy]);
    ctx.font = "600 13px -apple-system, Segoe UI, Roboto, sans-serif";
    const w = ctx.measureText(text).width;
    ctx.fillStyle = "rgba(0,0,0,0.65)";
    ctx.fillRect(x - w / 2 - 6, y - 11, w + 12, 20);
    ctx.fillStyle = color;
    ctx.fillText(text, x - w / 2, y + 4);
  }

  function draw() {
    const { w, h } = size();
    ctx.clearRect(0, 0, w, h);
    if (img.complete) ctx.drawImage(img, 0, 0, w, h);

    state.zones.forEach((z, i) => {
      const on = state.highlight && state.highlight.kind === "zone" && state.highlight.index === i;
      polygon(z.points, TYPES[z.type], on);
    });
    state.lanes.forEach((l, i) => {
      const on = state.highlight && state.highlight.kind === "lane" && state.highlight.index === i;
      polygon(l.points, TYPES.lane, on);
      if (l.direction) arrow(l.direction[0], l.direction[1], "#ffd400");
      label(l.name, l.points, "#00c8ff");
    });

    // polygon in progress, with a rubber band to the cursor
    if (state.draft.length) {
      const style = TYPES[state.tool];
      ctx.strokeStyle = style.stroke;
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      state.draft.forEach((p, i) => { const [x, y] = toPx(p); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
      if (state.mouse) { const [mx, my] = toPx(state.mouse); ctx.lineTo(mx, my); }
      ctx.stroke();
      ctx.setLineDash([]);
      state.draft.forEach((p, i) => {
        const [x, y] = toPx(p);
        const closable = i === 0 && state.draft.length >= 3 && state.mouse && distPx(p, state.mouse) < CLOSE_RADIUS_PX;
        ctx.beginPath();
        ctx.arc(x, y, closable ? 8 : 4, 0, Math.PI * 2);
        ctx.fillStyle = closable ? "#ffd400" : style.stroke;
        ctx.fill();
      });
    }

    if (state.directionLane !== null && state.directionDraft.length === 1 && state.mouse) {
      arrow(state.directionDraft[0], state.mouse, "#ffd400");
    }
  }

  // --- editing ----------------------------------------------------------------
  function markDirty() {
    state.dirty = true;
    statusEl.textContent = "Unsaved changes";
  }

  function nextLaneName() {
    const names = new Set(state.lanes.map(l => l.name));
    let n = state.lanes.length + 1;
    while (names.has(`Lane ${n}`)) n++;
    return `Lane ${n}`;
  }

  function finishDraft() {
    if (state.draft.length < 3) return;
    if (state.tool === "lane") {
      state.lanes.push({ name: nextLaneName(), points: state.draft, direction: null });
      state.directionLane = state.lanes.length - 1;
      state.directionDraft = [];
    } else {
      state.zones.push({ type: state.tool, points: state.draft });
    }
    state.draft = [];
    markDirty();
    renderList();
    updateHint();
    draw();
  }

  function cancel() {
    state.draft = [];
    state.directionLane = null;
    state.directionDraft = [];
    updateHint();
    draw();
  }

  function setTool(tool) {
    if (state.draft.length && tool !== state.tool) state.draft = [];
    state.directionLane = null;
    state.directionDraft = [];
    state.tool = tool;
    toolButtons.forEach(b => b.classList.toggle("active", b.dataset.tool === tool));
    updateHint();
    draw();
  }

  canvas.addEventListener("click", evt => {
    const p = toNorm(evt);
    if (state.directionLane !== null) {
      state.directionDraft.push(p);
      if (state.directionDraft.length === 2) {
        if (distPx(state.directionDraft[0], state.directionDraft[1]) < 10) {
          state.directionDraft = [];
        } else {
          state.lanes[state.directionLane].direction = state.directionDraft;
          state.directionLane = null;
          state.directionDraft = [];
          markDirty();
          renderList();
        }
      }
    } else if (state.draft.length >= 3 && distPx(state.draft[0], p) < CLOSE_RADIUS_PX) {
      finishDraft();
      return;
    } else {
      state.draft.push(p);
    }
    updateHint();
    draw();
  });

  canvas.addEventListener("mousemove", evt => { state.mouse = toNorm(evt); draw(); });
  canvas.addEventListener("mouseleave", () => { state.mouse = null; draw(); });

  document.addEventListener("keydown", evt => {
    if (evt.target.tagName === "INPUT") return;
    if (evt.key === "Enter") { evt.preventDefault(); finishDraft(); }
    else if (evt.key === "Escape") { cancel(); }
    else if (evt.key === "Backspace" && state.draft.length) {
      evt.preventDefault();
      state.draft.pop();
      updateHint();
      draw();
    }
  });

  toolButtons.forEach(b => b.addEventListener("click", () => setTool(b.dataset.tool)));

  function updateHint() {
    if (state.directionLane !== null) {
      const lane = state.lanes[state.directionLane];
      hint.innerHTML = state.directionDraft.length === 0
        ? `<strong>${lane.name}:</strong> click where traffic in this lane comes <strong>from</strong>. <kbd>Esc</kbd> skips (wrong-side detection stays off for this lane).`
        : `<strong>${lane.name}:</strong> now click where the traffic <strong>goes to</strong>.`;
      return;
    }
    const what = TYPES[state.tool].label.toLowerCase();
    hint.innerHTML = state.draft.length === 0
      ? `Click to place the corners of the <strong>${what}</strong>. Click the first point again (or press <kbd>Enter</kbd>) to close it.`
      : `${state.draft.length} point${state.draft.length === 1 ? "" : "s"} &mdash; click the first point or press <kbd>Enter</kbd> to finish, <kbd>Backspace</kbd> undoes a point, <kbd>Esc</kbd> cancels.`;
  }

  function renderList() {
    list.innerHTML = "";
    const items = [
      ...state.zones.map((z, i) => ({ kind: "zone", index: i, style: TYPES[z.type], text: TYPES[z.type].label })),
      ...state.lanes.map((l, i) => ({ kind: "lane", index: i, style: TYPES.lane, lane: l })),
    ];
    if (!items.length) {
      list.innerHTML = '<li class="empty-note">Nothing drawn yet.</li>';
      return;
    }
    items.forEach(item => {
      const li = document.createElement("li");
      li.className = "shape-item";
      li.addEventListener("mouseenter", () => { state.highlight = { kind: item.kind, index: item.index }; draw(); });
      li.addEventListener("mouseleave", () => { state.highlight = null; draw(); });

      const chip = document.createElement("span");
      chip.className = "shape-chip";
      chip.style.background = item.style.stroke;
      li.appendChild(chip);

      if (item.kind === "lane") {
        const input = document.createElement("input");
        input.type = "text";
        input.value = item.lane.name;
        input.className = "shape-name";
        input.addEventListener("change", () => { item.lane.name = input.value.trim() || item.lane.name; markDirty(); draw(); });
        li.appendChild(input);
        const dir = document.createElement("button");
        dir.type = "button";
        dir.className = "shape-btn" + (item.lane.direction ? "" : " warn");
        dir.textContent = item.lane.direction ? "redraw arrow" : "set direction";
        dir.addEventListener("click", () => {
          state.draft = [];
          state.directionLane = item.index;
          state.directionDraft = [];
          updateHint();
          draw();
        });
        li.appendChild(dir);
      } else {
        const span = document.createElement("span");
        span.className = "shape-text";
        span.textContent = item.text;
        li.appendChild(span);
      }

      const del = document.createElement("button");
      del.type = "button";
      del.className = "shape-btn danger";
      del.textContent = "delete";
      del.addEventListener("click", () => {
        if (item.kind === "zone") state.zones.splice(item.index, 1);
        else state.lanes.splice(item.index, 1);
        state.highlight = null;
        cancel();
        markDirty();
        renderList();
      });
      li.appendChild(del);
      list.appendChild(li);
    });
  }

  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    statusEl.textContent = "Saving...";
    try {
      const res = await fetch(cfg.saveUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nameInput.value, zones: state.zones, lanes: state.lanes }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `save failed (${res.status})`);
      state.dirty = false;
      statusEl.textContent = `Saved at ${new Date().toLocaleTimeString()}`;
    } catch (err) {
      statusEl.textContent = "Not saved: " + err.message;
    } finally {
      saveBtn.disabled = false;
    }
  });
  nameInput.addEventListener("input", markDirty);

  window.addEventListener("beforeunload", evt => {
    if (state.dirty) { evt.preventDefault(); evt.returnValue = ""; }
  });
})();
