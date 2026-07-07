import json
import os
import random
import datetime
from collections import deque
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
import aiohttp

app = FastAPI()

# Global fixed-size deque to hold logs securely in RAM (stores last 100 requests)
REQUEST_LOGS = deque(maxlen=100)

# 1. Safely load the matrix directly from Vercel's environment variables
env_matrix = os.getenv("COC_CONFIG_MATRIX")

if env_matrix:
    CONFIG_MATRIX = json.loads(env_matrix)
else:
    CONFIG_MATRIX = []
    print("⚠️ Warning: COC_CONFIG_MATRIX environment variable not found!")

COC_BASE_URL = "https://api.clashofclans.com/v1"

# --- NEW: Dashboard API and HTML View ---

@app.get("/api/logs")
async def get_raw_logs():
    """Returns the captured logs list as JSON."""
    return list(REQUEST_LOGS)

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    """Renders a self-updating, elegant dark dashboard UI."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CoC Proxy Analytics Dashboard</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #121212; color: #e0e0e0; margin: 0; padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #333; padding-bottom: 20px; margin-bottom: 20px; }
            h1 { color: #ffbb00; margin: 0; font-size: 24px; }
            .badge { background: #333; padding: 5px 10px; border-radius: 4px; font-size: 14px; font-weight: bold; }
            .table-container { background: #1e1e1e; border-radius: 8px; overflow-x: auto; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
            table { width: 100%; border-collapse: collapse; text-align: left; }
            th, td { padding: 12px 16px; border-bottom: 1px solid #2a2a2a; font-size: 14px; }
            th { background-color: #252525; color: #aaa; font-weight: 600; text-transform: uppercase; font-size: 12px; }
            tr:hover { background-color: #252525; }
            .status-ok { color: #4caf50; font-weight: bold; }
            .status-err { color: #f44336; font-weight: bold; }
            .method { background: #007acc; color: #fff; padding: 2px 6px; border-radius: 3px; font-size: 11px; font-weight: bold; }
            .json-data { font-family: monospace; background: #2d2d2d; padding: 4px; border-radius: 4px; font-size: 12px; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>⚔️ Clash of Clans Proxy Monitor</h1>
                <div class="badge" id="total-counter">Requests Logged: 0</div>
            </header>
            
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>IP Address</th>
                            <th>Method</th>
                            <th>Endpoint</th>
                            <th>Tag / Path</th>
                            <th>Params Used</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="log-rows">
                        <tr>
                            <td colspan="7" style="text-align: center; color: #777;">Awaiting incoming API traffic...</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <script>
            async function fetchLogs() {
                try {
                    const response = await fetch('/api/logs');
                    const logs = await response.json();
                    const tbody = document.getElementById('log-rows');
                    document.getElementById('total-counter').innerText = `Requests Logged: ${logs.length}`;
                    
                    if(logs.length === 0) return;
                    
                    tbody.innerHTML = logs.map(log => {
                        const statusClass = log.status < 400 ? 'status-ok' : 'status-err';
                        const paramsStr = Object.keys(log.params).length ? JSON.stringify(log.params) : '{}';
                        return `
                            <tr>
                                <td>${log.timestamp}</td>
                                <td><code>${log.ip}</code></td>
                                <td><span class="method">${log.method}</span></td>
                                <td><code>/${log.endpoint_type}</code></td>
                                <td><code>${decodeURIComponent(log.encoded_tag)}</code></td>
                                <td><div class="json-data" title='${paramsStr}'>${paramsStr}</div></td>
                                <td class="${statusClass}">${log.status}</td>
                            </tr>
                        `;
                    }).join('');
                } catch (error) {
                    console.error("Failed to refresh logs dashboard:", error);
                }
            }
            
            // Poll for fresh metadata every 3 seconds
            setInterval(fetchLogs, 3000);
            fetchLogs();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# 2. Universal Mirror Route: /v1/{endpoint_type}/{encoded_tag}
@app.api_route("/v1/{endpoint_type}/{encoded_tag}", methods=["GET", "POST"])
async def forward_coc_request(endpoint_type: str, encoded_tag: str, request: Request):
    
    # 1. Pick a random Key block from your list
    if not CONFIG_MATRIX:
        raise HTTPException(status_code=500, detail="Configuration Error: Matrix Empty")
        
    chosen_group = random.choice(CONFIG_MATRIX)
    coc_key = chosen_group["COC_KEY"]
    
    # 2. Pick a random proxy that belongs ONLY to that chosen Key
    chosen_proxy = random.choice(chosen_group["Proxies"])
    
    # 3. Reconstruct the target URL for Supercell
    target_url = f"{COC_BASE_URL}/{endpoint_type}/{encoded_tag}"
    
    # Capture any incoming query parameters and body data
    query_params = dict(request.query_params)
    body = await request.body()
    
    headers = {
        "Authorization": f"Bearer {coc_key}",
        "Accept": "application/json",
        "Content-Type": request.headers.get("Content-Type", "application/json")
    }
    
    # Default metric statuses before hitting external session execution
    status_code = 500
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "Unknown").split(',')[0]

    # 4. Execute the request through the bound proxy pipeline
    async with aiohttp.ClientSession() as session:
        try:
            async with session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                params=query_params,
                data=body,
                proxy=chosen_proxy,
                timeout=10
            ) as coc_response:
                
                response_content = await coc_response.read()
                status_code = coc_response.status
                
                # Append telemetry to the rolling record log before return handling
                REQUEST_LOGS.appendleft({
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ip": client_ip,
                    "method": request.method,
                    "endpoint_type": endpoint_type,
                    "encoded_tag": encoded_tag,
                    "params": query_params,
                    "status": status_code
                })

                return Response(
                    content=response_content,
                    status_code=status_code,
                    media_type="application/json"
                )
                
        except Exception as e:
            # Append execution failures to metrics layout tracker
            REQUEST_LOGS.appendleft({
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ip": client_ip,
                "method": request.method,
                "endpoint_type": endpoint_type,
                "encoded_tag": encoded_tag,
                "params": query_params,
                "status": 500
            })
            raise HTTPException(status_code=500, detail=f"Gateway Error: {str(e)}")
