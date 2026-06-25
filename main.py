import json
import os
import random
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
import aiohttp

app = FastAPI()

env_matrix = os.getenv("COC_CONFIG_MATRIX")

if env_matrix:
    CONFIG_MATRIX = json.loads(env_matrix)
else:
    CONFIG_MATRIX = []
    print("⚠️ Warning: COC_CONFIG_MATRIX environment variable not found!")

# Note the base URL drops the "/v1" since the path will include it!
COC_BASE_URL = "https://api.clashofclans.com"

# Using {path:path} captures multi-slash paths completely!
@app.api_route("/v1/{path:path}", methods=["GET", "POST"])
async def forward_coc_request(path: str, request: Request):
    if not CONFIG_MATRIX:
        raise HTTPException(status_code=500, detail="Server configuration matrix is missing.")
    
    # 1. Pick a random Key block and proxy pipeline
    chosen_group = random.choice(CONFIG_MATRIX)
    coc_key = chosen_group["COC_KEY"]
    chosen_proxy = random.choice(chosen_group["Proxies"])
    
    # Reconstruct the target URL completely
    target_url = f"{COC_BASE_URL}/v1/{path}"
    query_params = dict(request.query_params)
    
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        body = await request.body()
        if not body:
            body = None
            
    headers = {
        "Authorization": f"Bearer {coc_key}",
        "Accept": "application/json"
    }
    
    # 2. Execute the request through the proxy matrix
    # Keep timeout low so we fail gracefully before Vercel kills the function
    async with aiohttp.ClientSession() as session:
        try:
            async with session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                params=query_params,
                data=body,
                proxy=chosen_proxy,
                timeout=8  
            ) as coc_response:
                
                response_content = await coc_response.read()
                
                if coc_response.status == 200 and response_content:
                    json_data = json.loads(response_content)
                    return JSONResponse(content=json_data, status_code=200)
                else:
                    try:
                        error_data = json.loads(response_content) if response_content else {"message": "Empty body from Supercell"}
                    except Exception:
                        error_data = {"error": "Supercell returned non-JSON data", "raw": response_content.decode('utf-8', errors='ignore')}
                    return JSONResponse(content=error_data, status_code=coc_response.status)
                
        except asyncio.TimeoutError:
            return JSONResponse(content={"error": "Proxy connection timed out contacting Supercell"}, status_code=504)
        except Exception as e:
            return JSONResponse(content={"error": f"Gateway Exception: {str(e)}"}, status_code=500)
