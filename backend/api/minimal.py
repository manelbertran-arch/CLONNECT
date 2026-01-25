"""Minimal FastAPI app for testing Railway deployment"""
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "minimal app works"}

@app.get("/health/live")
def health_live():
    return {"status": "ok", "version": "minimal-test"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
