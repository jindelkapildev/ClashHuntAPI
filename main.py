import json
import os
import random
import asyncio  # Added missing import so it doesn't crash on TimeoutError
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

COC_BASE_URL = "https://api.clashofclans.com"

# Stack decorators to accept both route structures seamlessly
@app.api_route("/v1/{path:path}", methods=["GET", "POST"])
@app.api_route("/proxy/{path:path}", methods=["GET", "POST"])
async def forward_coc_request(path: str, request: Request):
    if not CONFIG_MATRIX:
        raise HTTPException(status_code=500, detail="Server configuration matrix is missing.")
    
    # 1. Pick a random Key block and proxy pipeline
    chosen_group = random.choice(CONFIG_MATRIX)
    coc_key = chosen_group["COC_KEY"]
    chosen_proxy = random.choice(chosen_group["Proxies"])
    
    # Clean up the path so it doesn't double-inject /v1/ if called via /proxy/v1/...
    clean_path = path.lstrip("/")
    if not clean_path.startswith("v1/"):
        target_url = f"{COC_BASE_URL}/v1/{clean_path}"
    else:
        target_url = f"{COC_BASE_URL}/{clean_path}"
        
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
