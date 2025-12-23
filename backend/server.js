const http = require("http");
const url = require("url");

const PORT = process.env.PORT || 8080;

function json(res, status, body){
  const data = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(data),
    "Access-Control-Allow-Origin": "*"
  });
  res.end(data);
}

function sendSse(res, event, data){
  res.write(`event: ${event}\n`);
  res.write(`data: ${JSON.stringify(data)}\n\n`);
}

function mockAxesLoad(t){
  const base = (i) => Math.round((Math.sin(t / 700 + i) * 40 + 50) * 10) / 10;
  return {
    x: base(0),
    y: base(1),
    z: base(2),
    a: base(3),
    b: base(4)
  };
}

const server = http.createServer((req, res) => {
  const { pathname } = url.parse(req.url, true);

  if (req.method === "OPTIONS"){
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type"
    });
    return res.end();
  }

  if (pathname === "/api/health" && req.method === "GET"){
    return json(res, 200, { status: "ok", time: new Date().toISOString() });
  }

  if (pathname === "/api/axes" && req.method === "GET"){
    return json(res, 200, {
      timestamp: Date.now(),
      axes: mockAxesLoad(Date.now())
    });
  }

  if (pathname === "/api/axes/stream" && req.method === "GET"){
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "Access-Control-Allow-Origin": "*"
    });

    const interval = setInterval(() => {
      sendSse(res, "axes", { timestamp: Date.now(), axes: mockAxesLoad(Date.now()) });
    }, 250);

    req.on("close", () => clearInterval(interval));
    return;
  }

  if (pathname === "/api/shutdown" && req.method === "POST"){
    // TODO: call real shutdown for Raspberry Pi (e.g. sudo shutdown -h now).
    return json(res, 202, { ok: true, message: "Shutdown scheduled (mock)" });
  }

  json(res, 404, { error: "Not found" });
});

server.listen(PORT, () => {
  console.log(`Hardware API listening on http://localhost:${PORT}`);
});
