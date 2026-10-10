# ContextLens

ContextLens is a Knight Hacks 2026 project. This repository currently contains only the shared project structure so the existing frontend and backend implementations can be integrated without overwriting one another.

## Project ownership

- `frontend/`: React and Vite client, owned by the frontend developer.
- `backend/`: Python analysis and service modules, owned by the backend developer.
- `demo/`: future demonstration videos and supporting assets.

The placeholder modules do not implement application behavior.

## Branch workflow

- `main`: stable shared branch.
- `frontend-dev`: frontend development.
- `backend-dev`: backend development.

Developers should work on their respective development branches and merge into `main` through pull requests.

## Start the frontend

```bash
cd frontend
npm install
npm run dev
```

## Backend setup

The backend is intentionally unimplemented. After the tested backend code and its dependencies are integrated:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
