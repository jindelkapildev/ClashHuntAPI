import json
import os
import random
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import aiohttp

app = FastAPI()

env_matrix = os.getenv("COC_CONFIG_MATRIX")

if env_matrix:
    CONFIG_MATRIX = json.loads(env_matrix)
else:
    CONFIG_MATRIX = []

COC_BASE_URL = "https://api.clashofclans.com/v1"

@app.api_route("/proxy", methods=["GET", "POST"])
async def forward_coc_request(endpoint: str, tag: str, request: Request, suffix: str = None):
    if not CONFIG_MATRIX:
        return JSONResponse(status_code=500, content={"error": "Server matrix configuration missing."})
    
    chosen_group = random.choice(CONFIG_MATRIX)
    coc_key = chosen_group.get("COC_KEY")
    chosen_proxy = random.choice(chosen_group.get("Proxies", []))
    
    # Clean the tag: remove leading # if present, then properly encode it for Supercell
    clean_tag = tag.strip().replace("#", "%23")
    
    # Construct the URL safely
    # Example: https://api.clashofclans.com/v1/clans/%232LRGQ2L9L
    target_url = f"{COC_BASE_URL}/{endpoint}/{clean_tag}"
    
    # If there is an extra endpoint path (like currentwar/leaguegroup), append it safely
    if suffix:
        target_url = f"{target_url}/{suffix.lstrip('/')}"
        
    query_params = dict(request.query_params)
    # Remove our routing helpers from query parameters forwarded to Supercell
    query_params.pop("endpoint", None)
    query_params.pop("tag", None)
    query_params.pop("suffix", None)
    
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        body = await request.body()

    # Create logs to return if it fails
    debug_logs = {
        "constructed_target_url": target_url,
        "forwarded_query_params": query_params,
        "selected_proxy": chosen_proxy.split("@")[-1] if chosen_proxy and "@" in chosen_proxy else chosen_proxy
    }
    
    headers = {
        "Authorization": f"Bearer {coc_key}",
        "Accept": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                params=query_params,
                data=body,
                proxy=chosen_proxy,
                timeout=12
            ) as coc_response:
                
                response_content = await coc_response.read()
                try:
                    supercell_json = json.loads(response_content) if response_content else {}
                except Exception:
                    supercell_json = {"raw_text": response_content.decode('utf-8', errors='ignore')}
                
                if coc_response.status == 200:
                    return JSONResponse(content=supercell_json, status_code=200)
                
                return JSONResponse(
                    status_code=coc_response.status,
                    content={"supercell_response": supercell_json, "debug_logs": debug_logs}
                )
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e), "debug_logs": debug_logs})
