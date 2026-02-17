"""
server.py

Minimal FastAPI microservice for the rules engine.
Single endpoint: POST /process_lead

Usage:
    uvicorn server:app --host 0.0.0.0 --port 8000
"""

import os
from fastapi import FastAPI, Header, HTTPException, Request
from wrapper import process_lead, load_config

app = FastAPI()

API_KEY = os.environ.get("API_KEY", "change-me")
config = load_config()


@app.post("/process_lead")
async def handle_process_lead(
    request: Request,
    x_api_key: str = Header(...),
):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    body = await request.json()
    debug = body.pop("debug", False)
    result = process_lead(body, config, debug=debug)
    return result
