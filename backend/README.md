# Hardware API (dev)

This backend provides a simple HTTP + SSE API for Raspberry Pi hardware control
and streaming axis/spindle load values. For development it serves mock values.

## Endpoints

- GET `/api/health`
  - `{ status: "ok", time: "<iso>" }`
- GET `/api/axes`
  - `{ timestamp, axes: { spindle,x,y,z } }`
- GET `/api/axes/stream` (SSE)
  - `event: axes` with `{ timestamp, axes: { spindle,x,y,z } }` every ~250ms
  - Optional query: `?intervalMs=250`
- GET `/api/settings`
  - `{ graphWindowSec }`
- POST `/api/settings`
  - `{ graphWindowSec }`
- POST `/api/shutdown`
  - `{ ok: true, message: "Shutdown scheduled (mock)" }`

## Run

```
python server.py
```

Optional:

```
set PORT=8080
set AXES_INTERVAL_MS=250
```

The server listens on `http://localhost:8080` by default.
