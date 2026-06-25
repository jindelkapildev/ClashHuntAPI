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
    print("⚠️ Warning: COC_CONFIG_MATRIX environment variable not found!")

COC_BASE_URL = "https://api.clashofclans.com/v1"

@app.api_route("/forward", methods=["GET", "POST"])
async def forward_coc_request(url: str, request: Request):
    if not CONFIG_MATRIX:
        return JSONResponse(
            status_code=500, 
            content={"debug_error": "Server configuration matrix is missing or empty in Environment Variables."}
        )
    
    # 1. Capture chosen pipeline elements
    chosen_group = random.choice(CONFIG_MATRIX)
    coc_key = chosen_group.get("COC_KEY", "MISSING_KEY")
    proxies_list = chosen_group.get("Proxies", [])
    chosen_proxy = random.choice(proxies_list) if proxies_list else None
    
    # Clean the input path
    clean_subpath = url.lstrip("/")
    target_url = f"{COC_BASE_URL}/{clean_subpath}"
    
    # Track incoming parameters
    query_params = dict(request.query_params)
    query_params.pop("url", None) 
    
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        body = await request.body()
        if not body:
            body = None

    # Masking keys for visibility without exposing your full tokens
    masked_key = f"{coc_key[:12]}...{coc_key[-12:]}" if len(coc_key) > 24 else "INVALID_SHORT_KEY"
    masked_proxy = chosen_proxy
    if chosen_proxy and "@" in chosen_proxy:
        parts = chosen_proxy.split("@")
        masked_proxy = f"http://***:***@{parts[-1]}"

    # Compile the internal debug tracker state
    debug_logs = {
        "received_url_param": url,
        "constructed_target_url": target_url,
        "forwarded_query_params": query_params,
        "selected_key_preview": masked_key,
        "selected_proxy_preview": masked_proxy,
        "http_method": request.method
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
                
                # Try parsing response content as JSON
                try:
                    supercell_json = json.loads(response_content) if response_content else {}
                except Exception:
                    supercell_json = {"raw_text": response_content.decode('utf-8', errors='ignore')}
                
                # If it's a 200, return the raw data directly
                if coc_response.status == 200:
                    return JSONResponse(content=supercell_json, status_code=200)
                
                # If it fails, bundle the Supercell response TOGETHER with our internal server state
                return JSONResponse(
                    status_code=coc_response.status,
                    content={
                        "supercell_response": supercell_json,
                        "proxy_gateway_debug_logs": debug_logs
                    }
                )
                
        except Exception as e:
            return JSONResponse(
                status_code=500, 
                content={
                    "error": f"Gateway Request Exception occurred: {str(e)}",
                    "proxy_gateway_debug_logs": debug_logs
                }
            )
