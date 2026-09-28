from __future__ import annotations

import json
import math
import os
import secrets
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = Path(os.getenv("STATSKILL_DATA_FILE", BASE_DIR / "demo.json"))
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "STATSKILL_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5175,http://127.0.0.1:5175",
    ).split(",")
    if origin.strip()
]


app = FastAPI(
    title="StatSkill AI API",
    version="1.0.0",
    description=(
        "Demo authentication and complete user data API for StatSkill AI. "
        "The demo JSON file is the source of truth."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_LOCK = Lock()
SESSIONS: dict[str, str] = {}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6)


class UserUpdateRequest(BaseModel):
    name: str | None = None


class AdminDataUpdate(BaseModel):
    data: dict[str, Any]


def read_demo() -> dict[str, Any]:
    with DATA_LOCK:
        if not DATA_FILE.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Demo data file not found: {DATA_FILE}",
            )
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Invalid JSON in {DATA_FILE}: {exc}",
            ) from exc


def write_demo(data: dict[str, Any]) -> None:
    with DATA_LOCK:
        DATA_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def sanitize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in user.items()
        if key.lower() not in {"password", "password_hash"}
    }


def find_account_data(data: dict[str, Any], email: str) -> dict[str, Any] | None:
    normalized_email = email.strip().lower()
    for account_data in [data, *(data.get("accounts") or [])]:
        user = account_data.get("user") or {}
        if user.get("email", "").strip().lower() == normalized_email:
            return account_data
    return None


def empty_account_data(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "user": user,
        "assessments": [],
        "courses": [],
        "selfAssessment": {},
        "learningHours": {},
        "modules": [],
        "documents": [],
        "certificates": [],
        "notifications": [],
    }


def average(values: list[float | int | str]) -> float:
    numbers: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            numbers.append(number)
    return sum(numbers) / len(numbers) if numbers else 0.0


ENGINE_DEFINITIONS = [
    {
        "key": "statisticalMethods",
        "name": "Statistical Methods",
        "benchmark": 3.5,
        "weight": 1.15,
        "description": "Inference, sampling, regression and time-series analysis.",
        "subSkills": [
            "Descriptive Statistics",
            "Hypothesis Testing",
            "Regression Analysis",
            "Time Series Analysis",
        ],
    },
    {
        "key": "dataQuality",
        "name": "Data Quality",
        "benchmark": 3.5,
        "weight": 1.05,
        "description": "Validation, error detection, review and quality assurance.",
        "subSkills": [
            "Data Validation",
            "Error Detection",
            "Imputation",
            "Audit & Review",
        ],
    },
    {
        "key": "python",
        "name": "Python",
        "benchmark": 3.0,
        "weight": 1.0,
        "description": "Python for data analysis, automation and statistical workflows.",
        "subSkills": ["pandas", "Visualisation", "Automation", "Statistical Libraries"],
    },
    {
        "key": "gis",
        "name": "GIS & Spatial Statistics",
        "benchmark": 3.0,
        "weight": 1.0,
        "description": "Spatial datasets, mapping, GIS tools and geographic analysis.",
        "subSkills": [
            "Map Projections",
            "Spatial Joins",
            "GIS Tools",
            "Choropleth Mapping",
        ],
    },
    {
        "key": "machineLearning",
        "name": "Machine Learning",
        "benchmark": 3.0,
        "weight": 0.95,
        "description": "Predictive modelling, evaluation and feature engineering.",
        "subSkills": [
            "Supervised Learning",
            "Model Evaluation",
            "Feature Engineering",
            "ML Frameworks",
        ],
    },
]


def calculate_competencies(data: dict[str, Any]) -> dict[str, Any]:
    assessments = data.get("assessments") or []
    courses = data.get("courses") or []
    self_assessment = data.get("selfAssessment") or {}
    learning_hours = data.get("learningHours") or {}
    direct_scores = {
        str(key): float(value)
        for key, value in (data.get("competencyScores") or {}).items()
        if _is_finite_number(value)
    }

    competencies: list[dict[str, Any]] = []

    for definition in ENGINE_DEFINITIONS:
        key = definition["key"]
        domain_assessments = [
            item for item in assessments if item.get("domain") == key
        ]
        domain_courses = [
            item for item in courses if item.get("domain") == key
        ]

        quiz = average([item.get("score", 0) for item in domain_assessments]) / 20
        course = average([item.get("score", 0) for item in domain_courses]) / 20
        self_values = self_assessment.get(key) or []
        self_score = average(self_values)
        hours = float(learning_hours.get(key, 0) or 0)
        effort = min(5.0, hours / 8.0)

        calculated_score = max(
            0.0,
            min(5.0, quiz * 0.50 + course * 0.25 + self_score * 0.15 + effort * 0.10),
        )
        score = direct_scores.get(key, calculated_score)
        score = max(0.0, min(5.0, score))

        if score >= 3.5:
            level = "Strong"
        elif score >= 2:
            level = "Moderate"
        else:
            level = "Weak"

        benchmark = float(definition["benchmark"])
        gap = max(0.0, benchmark - score)

        trend = "Stable"
        if len(domain_assessments) > 1:
            first = float(domain_assessments[0].get("score", 0))
            last = float(domain_assessments[-1].get("score", 0))
            delta = last - first
            if delta >= 5:
                trend = "Improving"
            elif delta <= -5:
                trend = "Declining"

        competencies.append(
            {
                **definition,
                "score": round(score, 2),
                "level": level,
                "trend": trend,
                "gap": round(gap, 2),
                "gapPercent": round((gap / benchmark) * 100) if benchmark else 0,
                "evidence": {
                    "quizAverage": round(average([item.get("score", 0) for item in domain_assessments])),
                    "courseAverage": round(average([item.get("score", 0) for item in domain_courses])),
                    "selfAssessment": round(self_score * 20),
                    "learningHours": hours,
                },
                "subSkills": [
                    {
                        "name": name,
                        "score": round(
                            float((self_values[index] if index < len(self_values) else 0) or 0) * 20
                        ),
                    }
                    for index, name in enumerate(definition["subSkills"])
                ],
            }
        )

    total_weight = sum(float(item["weight"]) for item in competencies) or 1
    weighted = (
        sum(item["score"] * float(item["weight"]) for item in competencies)
        / total_weight
    )
    quiz_average = round(average([item.get("score", 0) for item in assessments]))
    total_hours = sum(float(value or 0) for value in learning_hours.values())

    overall_score = round(
        min(
            100,
            max(
                0,
                weighted * 20 * 0.82
                + quiz_average * 0.12
                + min(total_hours, 100) * 0.06,
            ),
        )
    )

    top_gaps = sorted(competencies, key=lambda item: item["gap"], reverse=True)[:3]
    recommendations_by_key = {
        "gis": "Complete GIS for Statistics and practise spatial joins and choropleth mapping.",
        "machineLearning": "Strengthen Python foundations before moving into model evaluation and ML.",
        "python": "Build pandas, visualisation and automation skills through practical datasets.",
        "dataQuality": "Practise validation, error detection and statistical audit workflows.",
        "statisticalMethods": "Target sampling, regression and time-series exercises for greater analytical depth.",
    }

    total_module_progress = average(
        [float(module.get("progress", 0) or 0) for module in data.get("modules", [])]
    )
    completed_modules = sum(
        1 for module in data.get("modules", []) if str(module.get("status", "")).lower() == "completed"
    )
    assessments_count = len(assessments)
    courses_count = len(courses)
    completed_course_count = sum(
        1 for course in courses if str(course.get("status", "")).lower() in {"completed", "complete"}
    )

    # Demo JSON has scores but no explicit completion/status on assessments/courses.
    # Therefore this count means "records with outcome/score supplied by the demo".
    assessments_with_score = sum(
        1 for item in assessments if _is_finite_number(item.get("score"))
    )

    return {
        "overallScore": overall_score,
        "criticalGaps": sum(item["level"] == "Weak" for item in competencies),
        "moderateGaps": sum(item["level"] == "Moderate" for item in competencies),
        "strongSkills": sum(item["level"] == "Strong" for item in competencies),
        "assessmentAverage": quiz_average,
        "learningHours": round(total_hours, 2),
        "learningHoursByDomain": {
            key: float(value or 0) for key, value in learning_hours.items()
        },
        "assessmentHistory": [dict(item) for item in assessments],
        "competencies": competencies,
        "topGaps": top_gaps,
        "recommendations": [
            recommendations_by_key[item["key"]]
            for item in top_gaps
            if item["key"] in recommendations_by_key
        ],
        "methodology": "50% assessments · 25% courses · 15% self-assessment · 10% learning effort",
        "learningProgress": round(total_module_progress),
        "completedModules": completed_modules,
        "totalModules": len(data.get("modules", [])),
        "assessmentsCompleted": assessments_with_score,
        "assessmentsTotal": assessments_count,
        "coursesCompleted": completed_course_count,
        "coursesTotal": courses_count,
    }


def build_user_payload(data: dict[str, Any]) -> dict[str, Any]:
    user = data.get("user") or {}
    engine = calculate_competencies(data)

    payload = {
        "user": sanitize_user(user),
        "id": user.get("id"),
        "profile": {
            "name": user.get("name"),
            "email": user.get("email"),
            "role": user.get("role"),
            "department": user.get("department"),
            "projectId": user.get("projectId"),
        },
        "competencyScores": {
            item["key"]: item["score"] for item in engine["competencies"]
        },
        "competencies": engine["competencies"],
        "dashboard": {
            "overallCompetency": engine["overallScore"],
            "criticalSkillGaps": engine["criticalGaps"] + engine["moderateGaps"],
            "learningProgress": engine["learningProgress"],
            "assessmentsCompleted": engine["assessmentsCompleted"],
            "assessmentsTotal": engine["assessmentsTotal"],
            "completedModules": engine["completedModules"],
            "totalModules": engine["totalModules"],
            "learningHours": engine["learningHours"],
        },
        "summary": engine,
        "assessments": data.get("assessments") or [],
        "assignments": data.get("assessments") or [],
        "courses": data.get("courses") or [],
        "learningPath": data.get("modules") or [],
        "modules": data.get("modules") or [],
        "selfAssessment": data.get("selfAssessment") or {},
        "learningHours": data.get("learningHours") or {},
        "documents": data.get("documents") or [],
        "certificates": data.get("certificates") or [],
        "notifications": data.get("notifications") or [],
    }

    return payload


def _is_finite_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def get_session_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    token = authorization.split(" ", 1)[1].strip()
    email = SESSIONS.get(token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session.",
        )

    account_data = find_account_data(read_demo(), email)
    if account_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session user no longer exists.",
        )

    return account_data["user"]




def require_admin_key(x_admin_key: str | None) -> None:
    expected = os.getenv("STATSKILL_ADMIN_KEY")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="STATSKILL_ADMIN_KEY is not configured on the server.",
        )
    if not x_admin_key or not secrets.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=403, detail="Invalid admin API key.")


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>StatSkill AI — Backend API</title>
  <style>
    :root {
      --bg: #090e17;
      --card-bg: #121c2e;
      --border: #1e3150;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: #00d2ff;
      --accent-glow: rgba(0, 210, 255, 0.25);
      --green: #10b981;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .container {
      max-width: 680px;
      width: 100%;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 36px;
      box-shadow: 0 20px 40px rgba(0,0,0,0.5);
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 600;
      color: var(--green);
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 4px 10px;
      border-radius: 999px;
      margin-bottom: 16px;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--green);
      box-shadow: 0 0 8px var(--green);
    }
    h1 {
      font-size: 26px;
      margin-bottom: 8px;
      background: linear-gradient(135deg, #ffffff 40%, var(--accent) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    p.lead {
      color: var(--muted);
      font-size: 15px;
      line-height: 1.5;
      margin-bottom: 24px;
    }
    .links-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 24px;
    }
    .btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 12px 16px;
      border-radius: 10px;
      text-decoration: none;
      font-size: 14px;
      font-weight: 600;
      transition: all 0.2s ease;
    }
    .btn-primary {
      background: linear-gradient(135deg, #0284c7, #0369a1);
      color: #ffffff;
      border: 1px solid #38bdf8;
    }
    .btn-primary:hover {
      box-shadow: 0 4px 16px var(--accent-glow);
      transform: translateY(-1px);
    }
    .btn-secondary {
      background: #17243b;
      color: #38bdf8;
      border: 1px solid var(--border);
    }
    .btn-secondary:hover {
      background: #1d2f4d;
      border-color: #38bdf8;
    }
    .card {
      background: #0d1624;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px;
      margin-bottom: 16px;
    }
    .card h3 {
      font-size: 14px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--muted);
      margin-bottom: 10px;
    }
    .cred-row {
      display: flex;
      justify-content: space-between;
      padding: 6px 0;
      font-size: 14px;
      border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    .cred-row:last-child { border-bottom: none; }
    .cred-label { color: var(--muted); }
    .cred-val { font-family: monospace; color: #38bdf8; font-weight: 600; }
    .endpoint-list {
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 13px;
      font-family: monospace;
      color: #94a3b8;
    }
    .endpoint-list span.method {
      display: inline-block;
      width: 45px;
      font-weight: bold;
      color: var(--accent);
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="badge"><span class="dot"></span> Backend Active · Port 8000</div>
    <h1>StatSkill AI — FastAPI Backend</h1>
    <p class="lead">The FastAPI authentication and user data service is running and serving requests for StatSkill AI.</p>

    <div class="links-grid">
    <a href="http://localhost:5173" class="btn btn-primary" target="_blank">🌐 Open Frontend (App)</a>
      <a href="/docs" class="btn btn-secondary">📖 Interactive Swagger API</a>
      <a href="/health" class="btn btn-secondary">❤️ Health Check</a>
    </div>

    <div class="card">
      <h3>🔑 Demo Login Credentials</h3>
      <div class="cred-row">
        <span class="cred-label">Email</span>
        <span class="cred-val">ananya.verma@demo.gov.in</span>
      </div>
      <div class="cred-row">
        <span class="cred-label">Password</span>
        <span class="cred-val">Demo@12345</span>
      </div>
    </div>

    <div class="card">
      <h3>📡 Core Endpoints</h3>
      <ul class="endpoint-list">
        <li><span class="method">POST</span> /api/auth/login</li>
        <li><span class="method">POST</span> /api/auth/register</li>
        <li><span class="method">GET</span> /api/me/data</li>
        <li><span class="method">GET</span> /api/users/{email}/data</li>
        <li><span class="method">PUT</span> /api/me/profile</li>
      </ul>
    </div>
  </div>
</body>
</html>"""


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(request: LoginRequest) -> dict[str, Any]:
    data = read_demo()
    account_data = find_account_data(data, str(request.email))
    if account_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    user = account_data["user"]
    password_matches = secrets.compare_digest(
        str(user.get("password", "")),
        request.password,
    )

    if not password_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = secrets.token_urlsafe(32)
    SESSIONS[token] = user["email"]

    return {
        "access_token": token,
        "token_type": "bearer",
        "data": build_user_payload(account_data),
    }


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest) -> dict[str, Any]:
    data = read_demo()
    email = str(request.email).strip().lower()
    if find_account_data(data, email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")

    user = {
        "id": f"USR-{secrets.token_hex(4).upper()}",
        "name": name,
        "email": email,
        "password": request.password,
        "role": "Statistical Investigator",
        "department": "MoSPI",
        "projectId": "SIH26101",
    }
    account_data = empty_account_data(user)
    data.setdefault("accounts", []).append(account_data)
    write_demo(data)

    token = secrets.token_urlsafe(32)
    SESSIONS[token] = email
    return {
        "access_token": token,
        "token_type": "bearer",
        "data": build_user_payload(account_data),
    }


@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    if authorization and authorization.lower().startswith("bearer "):
        SESSIONS.pop(authorization.split(" ", 1)[1].strip(), None)
    return {"ok": True}


@app.get("/api/me")
def me(user: dict[str, Any] = Depends(get_session_user)) -> dict[str, Any]:
    data = read_demo()
    account_data = find_account_data(data, user["email"])
    if account_data is None:
        raise HTTPException(status_code=401, detail="Session user no longer exists.")
    return {"user": sanitize_user(user), "data": build_user_payload(account_data)}


@app.get("/api/me/data")
def my_data(user: dict[str, Any] = Depends(get_session_user)) -> dict[str, Any]:
    account_data = find_account_data(read_demo(), user["email"])
    if account_data is None:
        raise HTTPException(status_code=401, detail="Session user no longer exists.")
    return build_user_payload(account_data)


@app.get("/api/users/{email}/data")
def public_demo_lookup(email: EmailStr) -> dict[str, Any]:
    data = read_demo()
    user = data.get("user") or {}
    if user.get("email", "").lower() != str(email).lower():
        raise HTTPException(status_code=404, detail="User not found.")

    return build_user_payload(data)




@app.put("/api/admin/data")
def replace_demo_data(
    request: AdminDataUpdate,
    x_admin_key: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin_key(x_admin_key)

    data = request.data
    if not isinstance(data.get("user"), dict):
        raise HTTPException(status_code=400, detail="data.user must be an object.")
    if not data["user"].get("email") or not data["user"].get("password"):
        raise HTTPException(status_code=400, detail="data.user.email and data.user.password are required.")

    write_demo(data)
    return build_user_payload(data)


@app.put("/api/me/profile")
def update_profile(
    request: UserUpdateRequest,
    user: dict[str, Any] = Depends(get_session_user),
) -> dict[str, Any]:
    data = read_demo()
    account_data = find_account_data(data, user["email"])
    if account_data is None:
        raise HTTPException(status_code=401, detail="Session user no longer exists.")
    stored_user = account_data.get("user") or {}

    if request.name is not None:
        cleaned = request.name.strip()
        if not cleaned:
            raise HTTPException(status_code=400, detail="Name cannot be empty.")
        stored_user["name"] = cleaned

    account_data["user"] = stored_user
    write_demo(data)
    return build_user_payload(account_data)
