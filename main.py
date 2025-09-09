import asyncio
import json
import threading
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import websocket

history = []
last_buy = None
active_connections = set()

def get_wib_now():
    return (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")

def ws_thread():
    global last_buy, history
    def on_message(ws, message):
        global last_buy, history
        msg = json.loads(message)
        if msg.get("event") == "gold-rate-event":
            data = json.loads(msg["data"])
            current_buy = float(data["buying_rate"].replace('.', ''))
            status = "➖ Tetap"
            if last_buy is not None:
                if current_buy > last_buy:
                    status = "🚀 Naik"
                elif current_buy < last_buy:
                    status = "🔻 Turun"
            data["status"] = status
            # Ganti waktu dengan waktu backend (WIB)
            data["created_at"] = get_wib_now()
            history.append(data)
            history[:] = history[-88:]
            last_buy = current_buy

            # Broadcast ke semua client websocket
            msg_out = json.dumps({"history": history[-88:]})
            to_remove = set()
            for ws_client in list(active_connections):
                try:
                    asyncio.run_coroutine_threadsafe(
                        ws_client.send_text(msg_out),
                        loop
                    )
                except Exception as e:
                    print("Client error:", e)
                    to_remove.add(ws_client)
            for ws_client in to_remove:
                active_connections.remove(ws_client)

    def on_open(ws):
        subscribe_msg = {
            "event": "pusher:subscribe",
            "data": {
                "channel": "gold-rate"
            }
        }
        ws.send(json.dumps(subscribe_msg))
        print("Subscribed to gold-rate channel")

    ws_url = "wss://ws-ap1.pusher.com/app/52e99bd2c3c42e577e13?protocol=7&client=js&version=7.0.3&flash=false"
    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message
    )
    ws.run_forever()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = asyncio.get_event_loop()
    threading.Thread(target=ws_thread, daemon=True).start()
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/", response_class=HTMLResponse)
async def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Harga Emas Real-time (2 Kolom, Waktu & Data)</title>
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css"/>
        <style>
            body { font-family: Arial; margin: 40px; }
            table.dataTable thead th { font-weight: bold; }
            th.waktu, td.waktu {
                width: 150px;
                min-width: 100px;
                max-width: 180px;
                white-space: nowrap;
                text-align: left;
            }
        </style>
    </head>
    <body>
        <h2>MONITORING Harga Emas Treasury</h2>
        <div id="jam" style="font-size:1.3em; color:#ff1744; font-weight:bold; margin-bottom:15px;"></div>
        <table id="tabel" class="display" style="width:100%">
            <thead>
                <tr>
                    <th class="waktu">Waktu</th>
                    <th>Data</th>
                </tr>
            </thead>
            <tbody></tbody>
        </table>
        <div style="margin-top:40px;">
            <h3>Chart Harga Emas (XAUUSD)</h3>
            <div id="tradingview_chart"></div>
            <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
            <script type="text/javascript">
            new TradingView.widget({
                "width": "100%",
                "height": 400,
                "symbol": "OANDA:XAUUSD", // Ganti sesuai pair yang kamu mau
                "interval": "15",
                "timezone": "Asia/Jakarta",
                "theme": "light",
                "style": "1",
                "locale": "id",
                "toolbar_bg": "#f1f3f6",
                "enable_publishing": false,
                "hide_top_toolbar": false,
                "save_image": false,
                "container_id": "tradingview_chart"
            });
            </script>
        </div>
        <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
        <script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
        <script>
            var table = $('#tabel').DataTable({
                "pageLength": 4,
                "lengthMenu": [4, 8, 18, 48, 88],
                "order": [],
                "columns": [
                    { "data": "waktu" },
                    { "data": "all" }
                ]
            });

            function updateTable(history) {
                // Urutkan data berdasarkan waktu (created_at) DESCENDING (terbaru di atas)
                history.sort(function(a, b) {
                    return new Date(b.created_at) - new Date(a.created_at);
                });
                var dataArr = history.map(function(d) {
                    return {
                        waktu: d.created_at,
                        all: `Harga Beli: ${d.buying_rate} | Harga Jual: ${d.selling_rate} | Status: ${d.status || "➖"}`
                    };
                });
                table.clear();
                table.rows.add(dataArr);
                table.draw(false);
                table.page('first').draw(false);
            }

            function connectWS() {
                var ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
                ws.onmessage = function(event) {
                    var data = JSON.parse(event.data);
                    if (data.history) updateTable(data.history);
                };
                ws.onclose = function() {
                    setTimeout(connectWS, 1000);
                };
            }
            connectWS();
            
            function updateJam() {
                var now = new Date();
                // WIB = UTC+7
                now.setHours(now.getUTCHours() + 7);
                var tgl = now.toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' });
                var jam = now.toLocaleTimeString('id-ID', { hour12: false });
                document.getElementById("jam").textContent = tgl + " " + jam + " WIB";
            }
            setInterval(updateJam, 1000);
            updateJam();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    try:
        await websocket.send_text(json.dumps({"history": history[-88:]}))
        while True:
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"ping": True}))
    except WebSocketDisconnect:
        pass
    finally:
        active_connections.remove(websocket)
