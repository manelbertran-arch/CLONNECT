"""Diagnostic app for debugging Railway deployment"""
from fastapi import FastAPI
import sys
import os

app = FastAPI()

@app.get("/")
def root():
    return {"status": "diagnostic app v3"}

@app.get("/health/live")
def health_live():
    return {"status": "ok", "version": "diagnostic-v3"}

@app.get("/debug/packages")
def debug_packages():
    """List installed packages"""
    import subprocess
    result = subprocess.run(["pip", "list"], capture_output=True, text=True)
    packages = result.stdout.split('\n')
    return {"packages": packages[:50]}  # First 50 packages

@app.get("/debug/env")
def debug_env():
    """Show relevant environment variables"""
    safe_vars = {}
    for key in ['DATABASE_URL', 'TELEGRAM_BOT_TOKEN', 'OPENAI_API_KEY', 'GROQ_API_KEY', 'PORT', 'PATH']:
        val = os.getenv(key, "NOT_SET")
        if val != "NOT_SET" and key not in ['PATH']:
            # Mask sensitive values
            safe_vars[key] = val[:10] + "..." if len(val) > 10 else "SET"
        else:
            safe_vars[key] = val if key == 'PATH' else "NOT_SET"
    return safe_vars

@app.get("/debug/import/{module}")
def debug_import(module: str):
    """Safely try to import a specific module"""
    import traceback
    try:
        __import__(module)
        return {"status": "ok", "module": module, "imported": True}
    except Exception as e:
        return {
            "status": "error",
            "module": module,
            "error": str(e),
            "error_type": type(e).__name__
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
