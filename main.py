import json
import os
import random
from fastapi import FastAPI, HTTPException, Request, Response
import aiohttp
app = FastAPI()

# 1. Safely load the matrix directly from Vercel's environment variables
env_matrix = os.getenv("COC_CONFIG_MATRIX")

if env_matrix:
    # Convert the secure JSON string back into a Python list
    CONFIG_MATRIX = json.loads(env_matrix)
else:
    # Fallback placeholder for local testing
    CONFIG_MATRIX = []
    print("⚠️ Warning: COC_CONFIG_MATRIX environment variable not found!")
COC_BASE_URL = "https://api.clashofclans.com/v1"

# 2. Universal Mirror Route: /v1/{endpoint_type}/{encoded_tag}
# This captures calls like /v1/players/%232LRGQ2L9L or /v1/clans/%232LRGQ2L9L
@app.api_route("/v1/{endpoint_type}/{encoded_tag}", methods=["GET", "POST"])
async def forward_coc_request(endpoint_type: str, encoded_tag: str, request: Request):
    
    # 1. Pick a random Key block from your list
    chosen_group = random.choice(CONFIG_MATRIX)
    coc_key = chosen_group["COC_KEY"]
    
    # 2. Pick a random proxy that belongs ONLY to that chosen Key
    chosen_proxy = random.choice(chosen_group["Proxies"])
    
    # 3. Reconstruct the target URL for Supercell
    # Matches exactly: https://api.clashofclans.com/v1/players/%232LRGQ2L9L
    target_url = f"{COC_BASE_URL}/{endpoint_type}/{encoded_tag}"
    
    # Capture any incoming query parameters (like ?limit=10) and body data
    query_params = dict(request.query_params)
    body = await request.body()
    
    headers = {
        "Authorization": f"Bearer {coc_key}",
        "Accept": "application/json",
        "Content-Type": request.headers.get("Content-Type", "application/json")
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
                
                return Response(
                    content=response_content,
                    status_code=coc_response.status,
                    media_type="application/json"
                )
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gateway Error: {str(e)}")