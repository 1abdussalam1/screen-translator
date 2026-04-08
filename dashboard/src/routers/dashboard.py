"""
Dashboard router — proxied through dashboard/src/main.py sub-app.
The actual route is defined in main.py; this module exists for
organisational completeness and can be imported to register
additional endpoints if needed.
"""
from fastapi import APIRouter

router = APIRouter()
