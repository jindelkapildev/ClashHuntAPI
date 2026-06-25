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

COC_BASE_URL = "https://api.clashofclans.com/v1"

@app.api_route("/v1/{endpoint_type}/{encoded_tag}", methods=["GET", "POST"])
async def forward_coc_request(endpoint_type: str, encoded_tag: str, request: Request):
    if not CONFIG_MATRIX:
        raise HTTPException(status_code=500, detail="Server configuration matrix is missing.")
    
    # 1. Pick a random Key block and proxy pipeline
    chosen_group = random.choice(CONFIG_MATRIX)
    coc_key = chosen_group["COC_KEY"]
    chosen_proxy = random.choice(chosen_group["Proxies"])
    
    target_url = f"{COC_BASE_URL}/{endpoint_type}/{encoded_tag}"
    query_params = dict(request.query_params)
    
    # 2. FIX: Only read and send the body if the request method actually uses one (like POST)
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        body = await request.body()
        if not body:  # If it's an empty byte string, set it to None
            body = None
    
    headers = {
        "Authorization": f"Bearer {coc_key}",
        "Accept": "application/json",
    }
    
    # Forward the content-type only if it exists in the original request
    if request.headers.get("Content-Type"):
        headers["Content-Type"] = request.headers.get("Content-Type")
    
    # 3. Execute the request through the bound proxy pipeline
    async with aiohttp.ClientSession() as session:
        try:
            async with session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                params=query_params,
                data=body,  # This will safely be None for GET requests
                proxy=chosen_proxy,
                timeout=10
            ) as coc_response:
                
                response_content = await coc_response.read()
                
                if coc_response.status == 200 and response_content:
                    json_data = json.loads(response_content)
                    return JSONResponse(
                        content=json_data,
                        status_code=coc_response.status
                    )
                else:
                    # Handle empty or error responses cleanly
                    try:
                        error_data = json.loads(response_content) if response_content else {"message": "Empty response from Supercell"}
                    except Exception:
                        error_data = {"error": "Could not parse response from Supercell", "raw": str(response_content)}
                        
                    return JSONResponse(
                        content=error_data,
                        status_code=coc_response.status
                    )
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gateway Error: {str(e)}")
