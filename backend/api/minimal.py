"""Test app for debugging Railway deployment"""
from fastapi import FastAPI
import sys

app = FastAPI()

@app.get("/")
def root():
    return {"status": "diagnostic app"}

@app.get("/health/live")
def health_live():
    return {"status": "ok", "version": "diagnostic-v2"}

@app.get("/test-import")
def test_import():
    """Try importing the main app to see what fails"""
    import traceback
    try:
        # Try to import main app
        from api import main
        return {"status": "ok", "main_imported": True}
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
