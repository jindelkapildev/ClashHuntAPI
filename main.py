import json
import os
import random
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
import aiohttp

app = FastAPI()

# 1. Safely load the matrix directly from Vercel's environment variables
env_matrix = os.getenv("COC_CONFIG_MATRIX")

if env_matrix:
    CONFIG_MATRIX = json.loads(env_matrix)
else:
    CONFIG_MATRIX = []
    print("⚠️ Warning: COC_CONFIG_MATRIX environment variable not found!")

# Note: We drop the "/v1" here because our catch-all path route includes the "/v1/" from the client request
COC_BASE_URL = "https://api.clashofclans.com"

# The "{path:path}" wildcard captures everything after the domain including all slashes!
@app.api_route("/v1/{path:path}", methods=["GET", "POST"])
async def forward_coc_request(path: str, request: Request):
    if not CONFIG_MATRIX:
        raise HTTPException(status_code=500, detail="Server configuration matrix is missing.")
    
    # 2. Pick a random Key block and proxy pipeline from your list
    chosen_group = random.choice(CONFIG_MATRIX)
    coc_key = chosen_group["COC_KEY"]
    chosen_proxy = random.choice(chosen_group["Proxies"])
    
    # 3. Reconstruct the clean path target URL for Supercell
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
                
                if coc_response.status == 200 and response_content:
                    json_data = json.loads(response_content)
                    return JSONResponse(content=json_data, status_code=200)
                else:
                    try:
                        error_data = json.loads(response_content) if response_content else {"message": "Empty response body from Supercell"}
                    except Exception:
                        error_data = {"error": "Supercell returned non-JSON data", "raw": response_content.decode('utf-8', errors='ignore')}
                    return JSONResponse(content=error_data, status_code=coc_response.status)
                
        except Exception as e:
            return JSONResponse(content={"error": f"Gateway Exception: {str(e)}"}, status_code=500)
