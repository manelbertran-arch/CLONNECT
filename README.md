# Clonnect

SaaS para automatizar DMs de creadores de contenido con IA.

## Estructura

- `/backend` - API FastAPI + PostgreSQL
- `/frontend` - Dashboard React

## Setup

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```
