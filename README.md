# StatSkill AI FastAPI

## Run

```bash
cd fastapi_backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API reads `demo.json` from this directory by default.

## Frontend

Set:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Restart Vite after changing `.env`.

## Demo login

- Email: `ananya.verma@demo.gov.in`
- Password: `Demo@12345`

## Endpoints

- `GET /health`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/me`
- `GET /api/me/data`
- `GET /api/users/{email}/data` (demo lookup)
- `PUT /api/me/profile`

`/api/auth/login` returns the complete user payload: profile, competencies, dashboard metrics, assessments/assignments, courses, learning path/modules, self-assessment, learning hours, documents, certificates, notifications and derived competency/benchmark analysis.

The server never returns the demo password in authenticated data responses.
