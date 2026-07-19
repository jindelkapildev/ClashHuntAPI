import json
import os
import random
import asyncio
from fastapi import FastAPI, HTTPException, Request
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

@app.api_route("/v1/{path:path}", methods=["GET", "POST"])
@app.api_route("/proxy/{path:path}", methods=["GET", "POST"])
@app.api_route("/proxy", methods=["GET", "POST"])  # Added to catch /proxy directly without 307 redirect loops
async def forward_coc_request(request: Request, path: str = ""):
    if not CONFIG_MATRIX:
        raise HTTPException(status_code=500, detail="Server configuration matrix is missing.")
    
    query_params = dict(request.query_params)
    
    # --- SMART PATH RECONSTRUCTION ---
    # Check if client passed the endpoint details inside Search Params instead of the URL path
    if not path or path.strip("/") == "":
        endpoint = query_params.pop("endpoint", None)
        tag = query_params.pop("tag", None)
        suffix = query_params.pop("suffix", None)
        
        if endpoint:
            # Reconstruct: v1/clans/%232LRGQ2L9L/currentwar
            constructed_path = f"v1/{endpoint}"
            if tag:
                # Tags must have their '#' encoded or cleaned up safely
                clean_tag = tag.replace("#", "%23")
                constructed_path += f"/{clean_tag}"
            if suffix:
                constructed_path += f"/{suffix}"
                
            target_url = f"{COC_BASE_URL}/{constructed_path}"
        else:
            # Fallback if someone literally just hit `/proxy` with no params
            return JSONResponse(content={"error": "No endpoint or path specified"}, status_code=400)
    else:
        # Standard path processing if called like /proxy/v1/clans
        clean_path = path.lstrip("/")
        if not clean_path.startswith("v1/"):
            target_url = f"{COC_BASE_URL}/v1/{clean_path}"
        else:
            target_url = f"{COC_BASE_URL}/{clean_path}"
    # ---------------------------------

    # 1. Pick a random Key block and proxy pipeline
    chosen_group = random.choice(CONFIG_MATRIX)
    coc_key = chosen_group["COC_KEY"]
    chosen_proxy = random.choice(chosen_group["Proxies"])
    
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
                params=query_params, # The popped items won't be duplicated here
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
