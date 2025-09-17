import asyncio
import json
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import requests

history = []
last_buy = None
active_connections = set()

def format_rupiah(nominal):
    try:
        return "{:,}".format(int(nominal)).replace(",", ".")
    except:
        return str(nominal)

async def api_loop():
    global last_buy, history
    api_url = "https://api.treasury.id/api/v1/antigrvty/gold/rate"
    shown_updates = set()
    while True:
        try:
            response = requests.post(api_url, timeout=10)
            if response.ok:
                data = response.json().get("data", {})
                buying_rate = int(data.get("buying_rate", 0))
                selling_rate = int(data.get("selling_rate", 0))
                updated_at = data.get("updated_at")
                if updated_at and updated_at not in shown_updates:
                    # Status
                    status = "➖ Tetap"
                    if last_buy is not None:
                        if buying_rate > last_buy:
                            status = "🚀 Naik"
                        elif buying_rate < last_buy:
                            status = "🔻 Turun"
                    # Simpan ke history
                    row = {
                        "buying_rate": buying_rate,
                        "selling_rate": selling_rate,
                        "status": status,
                        "created_at": updated_at
                    }
                    history.append(row)
                    history[:] = history[-1441:]
                    last_buy = buying_rate
                    shown_updates.add(updated_at)
                    # Broadcast ke semua client websocket
                    # Kirim juga harga yang sudah diformat
                    row_fmt = {
                        "buying_rate": format_rupiah(buying_rate),
                        "selling_rate": format_rupiah(selling_rate),
                        "status": status,
                        "created_at": updated_at
                    }
                    history_fmt = [
                        {
                            "buying_rate": format_rupiah(h["buying_rate"]),
                            "selling_rate": format_rupiah(h["selling_rate"]),
                            "status": h["status"],
                            "created_at": h["created_at"]
                        }
                        for h in history
                    ]
                    msg_out = json.dumps({"history": history_fmt})
                    to_remove = set()
                    for ws_client in list(active_connections):
                        try:
                            await ws_client.send_text(msg_out)
                        except Exception:
                            to_remove.add(ws_client)
                    for ws_client in to_remove:
                        active_connections.remove(ws_client)
            await asyncio.sleep(0.5)
        except Exception as e:
            print("Error:", e)
            await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(api_loop())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

@app.get("/", response_class=HTMLResponse)
async def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Harga Emas Treasury</title>
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
                "symbol": "OANDA:XAUUSD",
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
        <b style="display:block; margin-top:30px;">USD/IDR (Dolar AS ke Rupiah Indonesia) - 15 Menit</b>

        <div style="overflow:hidden; height:370px; width:630px; border:1px solid #ccc; border-radius:6px;">
        <iframe 
            src="https://sslcharts.investing.com/index.php?force_lang=54&pair_ID=2138&timescale=900&candles=80&style=candles"
            width="628"
            height="430"
            style="margin-top:-62px; border:0;"
            scrolling="no"
            frameborder="0"
            allowtransparency="true">
        </iframe>
        </div>
        <b style="display:block; margin-top:30px;">Kalender Ekonomi</b>
        <div style="width:630px; ">
            <iframe src="https://sslecal2.investing.com?columns=exc_flags,exc_currency,exc_importance,exc_actual,exc_forecast,exc_previous&category=_employment,_economicActivity,_inflation,_centralBanks,_confidenceIndex&importance=3&features=datepicker,timezone,timeselector,filters&countries=5,37,48,35,17,36,26,12,72&calType=week&timeZone=27&lang=54" width="650" height="467" frameborder="0" allowtransparency="true" marginwidth="0" marginheight="0"></iframe><div class="poweredBy" style="font-family: Arial, Helvetica, sans-serif;"><span style="font-size: 11px;color: #333333;text-decoration: none;">Kalender Ekonomi Real Time dipersembahkan oleh <a href="https://id.investing.com" rel="nofollow" target="_blank" style="font-size: 11px;color: #06529D; font-weight: bold;" class="underline_link">Investing.com Indonesia</a>.</span></div>        
        </div>

        <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
        <script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
        <script>
            var table = $('#tabel').DataTable({
                "pageLength": 4,
                "lengthMenu": [4, 8, 18, 48, 88, 888, 1441],
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
        def format_rupiah(nominal):
            try:
                return "{:,}".format(int(nominal)).replace(",", ".")
            except:
                return str(nominal)
        def format_history(hist):
            return [
                {
                    "buying_rate": format_rupiah(h["buying_rate"]),
                    "selling_rate": format_rupiah(h["selling_rate"]),
                    "status": h["status"],
                    "created_at": h["created_at"]
                }
                for h in hist
            ]
        await websocket.send_text(json.dumps({"history": format_history(history[-1441:])}))
        while True:
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"ping": True}))
    except WebSocketDisconnect:
        pass
    finally:
        active_connections.discard(websocket)
