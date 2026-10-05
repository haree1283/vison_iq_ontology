// Shared by the result and live pages: render the most recent events (newest
// first) from a /status or /live_status payload into a <ul class="event-list">.
function renderEvents(ul, events) {
  if (!events || !events.length) return;
  ul.replaceChildren(...events.slice().reverse().map(ev => {
    const li = document.createElement("li");
    li.className = `event-item sev-${ev.severity}`;
    const time = document.createElement("span");
    time.className = "event-time";
    time.textContent = `${ev.time_s.toFixed(1)}s`;
    const text = document.createElement("span");
    text.textContent = ev.label + (ev.track_id !== null ? `  #${ev.track_id} ${ev.object_class}` : "");
    li.append(time, text);
    return li;
  }));
}

// per-type vehicle counts: each tracked vehicle counted once (people are not vehicles)
const VEHICLE_TYPES = [["car", "Cars"], ["motorcycle", "Motorcycles"], ["auto", "Autos"], ["bus", "Buses"],
                       ["truck", "Trucks"], ["bicycle", "Bicycles"]];
function renderVehicleTypes(el, s) {
  if (!el) return;
  const t = s.vehicle_types || {};
  const total = VEHICLE_TYPES.reduce((n, [k]) => n + (t[k] || 0), 0);
  el.innerHTML = `<div class="vtype total"><div class="stat-value">${total}</div><div class="stat-label">All vehicles</div></div>` +
    VEHICLE_TYPES.map(([k, label]) =>
      `<div class="vtype"><div class="stat-value">${t[k] || 0}</div><div class="stat-label">${label}</div></div>`).join('');
}

// processing speed: frames done (of total), frames per second, milliseconds per frame, time left
function renderSpeed(s) {
  const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
  set('sp-frames', s.total_frames ? `${s.frame_idx} / ${s.total_frames}` : `${s.frame_idx}`);
  set('sp-fps', s.processing_fps ? `${s.processing_fps}` : '–');
  set('sp-ms', s.ms_per_frame ? `${s.ms_per_frame} ms` : '–');
  if (s.eta_secs != null && s.status === 'processing') {
    const m = Math.floor(s.eta_secs / 60), sec = s.eta_secs % 60;
    set('sp-eta', m ? `${m}m ${sec}s` : `${sec}s`);
  } else {
    set('sp-eta', s.status === 'done' ? 'done' : '–');
  }
}
