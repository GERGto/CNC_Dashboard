# Hardware API (dev)

This backend provides a simple HTTP + SSE API for Raspberry Pi hardware control
and streaming 5 axis load values. For development it serves mock values.

## Endpoints

- GET `/api/health`
  - `{ status: "ok", time: "<iso>" }`
- GET `/api/axes`
  - `{ timestamp, axes: { x,y,z,a,b } }`
- GET `/api/axes/stream` (SSE)
  - `event: axes` with `{ timestamp, axes: { x,y,z,a,b } }` every ~250ms
- POST `/api/shutdown`
  - `{ ok: true, message: "Shutdown scheduled (mock)" }`

## Run

```
node server.js
```

The server listens on `http://localhost:8080` by default.
