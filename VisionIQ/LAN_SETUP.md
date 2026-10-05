# Run VisionIQ on a LAN

Run both services on the computer that contains the project and database access.

## 1. Find the host computer IP

In PowerShell:

```powershell
ipconfig
```

Use the IPv4 address for the active Wi-Fi or Ethernet adapter, for example `192.168.1.25`.

## 2. Start the backend (Python)

The backend is Python (Flask + Socket.IO). It also runs the NH5 Highway YOLOv8 +
PaddleOCR models, so it uses the NH5 Highway virtual environment:

```bash
cd VisionIQ
"../NH5 Highway/.venv/bin/pip" install -r backend/requirements.txt   # once
cp backend/.env.example backend/.env                                  # once, then edit it
./start.sh          # builds the frontend on first run, then serves everything on port 8080
```

`./start.sh` is the same as `npm run build` once, then `"../NH5 Highway/.venv/bin/python" backend/server.py`.
Without MySQL settings in `backend/.env` the backend uses a local SQLite file (`backend/data/visioniq.db`).

The backend listens on all interfaces at port `8080` and serves:

- `http://HOST:8080/` - VisionIQ (React frontend, built into `dist/`)
- `/media`, `/download`, `/stream`, `/status`, `/live_ws` - NH5 videos, photos, report.xlsx and live camera stream
  (used by VisionIQ's pages; NH5's old standalone pages are not served -- VisionIQ is the only website)
- `/api/...`, `/socket.io` - VisionIQ API and live stream; `/api/nh5/status|jobs|events|sync` - NH5 data

VisionIQ's own pages drive the NH5 models directly: **Video Upload**, **Live Camera**, **Video Library**,
**Road Maps** and **Detection Model** in the sidebar. Every finished video (or stopped live session) is imported
into the vehicle database within ~10 s (`NH5_SYNC_INTERVAL`), shows up on the dashboards, and its Excel report
(`report.xlsx`) is linked into the **Ontology**: one Vehicle node per unique number plate, connected to every
video, camera, spreadsheet row and event it appears in. **Vehicle Info** tracks a plate across videos.

To start empty again (delete all vehicle records and hide every video processed before now; nothing on disk is
deleted): `"../NH5 Highway/.venv/bin/python" backend/scripts/reset_data.py`. Undo the hiding with `--show-all`.

## 3. Frontend development server (optional)

Only needed while changing the React code; it proxies the API, socket and NH5 paths to port 8080:

```bash
cd VisionIQ
npm run dev -- --host 0.0.0.0
```

The dev frontend listens on all interfaces at port `5173`.

## 4. Open from another computer

On the same Wi-Fi or LAN, open:

```text
http://192.168.1.25:8080
```

(or port `5173` when using the dev server). Replace the IP with the host computer's IPv4 address.

## Windows Firewall

If another computer cannot open the page, allow inbound TCP port `8080` (and `5173` for the dev server) in Windows Defender Firewall. Keep the network marked Private and do not expose these development ports to the public internet.

## Database note

The backend computer must be able to reach the MySQL server configured in `backend/.env`. Other computers do not need MySQL installed because they connect only to the frontend host.

## Separate frontend hosting

When the frontend is hosted without the Vite proxy, set `VITE_API_URL` to the backend LAN URL before building, for example:

```env
VITE_API_URL=http://192.168.1.25:8080
```
