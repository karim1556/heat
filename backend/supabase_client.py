"""Supabase REST Client for Heat Parametric Insurance Platform.
Provides direct HTTP API integration with Supabase PostgREST tables.
Requires environment variables:
- SUPABASE_URL (e.g. https://xyzcompany.supabase.co)
- SUPABASE_KEY (e.g. your anon key or service role key)
"""

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Load .env from backend directory or project root
backend_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(backend_env_path):
    load_dotenv(backend_env_path)
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

def is_supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)

def _supabase_request(endpoint: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None, headers_extra: Optional[Dict[str, str]] = None) -> Any:
    if not is_supabase_configured():
        raise RuntimeError("Supabase credentials not configured in environment (SUPABASE_URL, SUPABASE_KEY).")

    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    req_headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    if headers_extra:
        req_headers.update(headers_extra)

    data_bytes = json.dumps(payload).encode("utf-8") if payload else None
    request = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method)

    try:
        with urllib.request.urlopen(request) as response:
            resp_text = response.read().decode("utf-8")
            if not resp_text:
                return [] if method == "GET" else {}
            return json.loads(resp_text)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Table not created yet on Supabase cloud
            return [] if method == "GET" else {}
        raise e

def supabase_select(table: str, select: str = "*", match: Optional[Dict[str, Any]] = None, order: Optional[str] = None) -> List[Dict[str, Any]]:
    query_params = [f"select={select}"]
    if match:
        for k, v in match.items():
            if v is not None:
                query_params.append(f"{k}=eq.{v}")
    if order:
        query_params.append(f"order={order}")
    
    endpoint = f"{table}?{'&'.join(query_params)}"
    res = _supabase_request(endpoint, method="GET")
    if isinstance(res, list):
        return res
    return []

def supabase_insert(table: str, row: Dict[str, Any]) -> Dict[str, Any]:
    res = _supabase_request(table, method="POST", payload=row)
    if isinstance(res, list) and len(res) > 0:
        return res[0]
    return row

def supabase_update(table: str, match: Dict[str, Any], updates: Dict[str, Any]) -> List[Dict[str, Any]]:
    query_params = []
    for k, v in match.items():
        query_params.append(f"{k}=eq.{v}")
    endpoint = f"{table}?{'&'.join(query_params)}"
    res = _supabase_request(endpoint, method="PATCH", payload=updates)
    return res if isinstance(res, list) else []
