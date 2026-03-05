# Shiny Web Container Template

Production-style boilerplate for running two sample Shiny applications behind a single gateway on port `8000`:

- R Shiny app at `/rlang-app`
- Python Shiny app at `/python-app`
- Auth UI at `/auth/login`
- User admin UI at `/admin/users`

This repository is designed as a template/exhibition project for building containerized Shiny systems.

## Current MVP

- Multi-container runtime with `docker compose`
- Reverse proxy routing with Nginx
- R Shiny sample app with:
  - table
  - Plotly scatter plot
- Python Shiny sample app with:
  - table
  - Plotly scatter plot
- Runtime hardening:
  - app-level health checks
  - gateway waits for healthy backends
  - graceful stop periods and init process per container
- Authentication:
  - NGINX `auth_request` gate in front of both Shiny apps
  - FastAPI auth service for login/session validation
  - PostgreSQL for users and sessions
  - Admin CRUD UI for user management

## Technical Stack (Developer Reference)

| Layer | Technology | Why It Is Used |
|---|---|---|
| Container orchestration | Docker Compose | Runs and connects multiple containers as one local stack |
| Gateway / routing | Nginx (`nginx:1.27-alpine`) | Single public entrypoint on `:8000`, path-based routing to multiple apps |
| R web app | Shiny for R + Plotly | Interactive R dashboard sample with table + scatter plot |
| Python web app | Shiny for Python + Plotly + Pandas | Interactive Python dashboard sample with table + scatter plot |
| Auth and admin | FastAPI + Jinja templates | Login/logout, session checks, and admin CRUD for users |
| Persistence | PostgreSQL 16 | Stores users and active sessions |
| Base runtime images | `rocker/r-ver:4.4.1`, `python:3.12-slim` | Stable language runtimes for reproducible local/dev containers |

## Container Topology (Mermaid)

```mermaid
flowchart LR
    user["Developer Browser"] --> gateway["gateway (Nginx) :8000"]
    gateway --> auth["auth-admin (FastAPI) :8080"]
    gateway --> rshiny["r-shiny container :3838"]
    gateway --> pyshiny["python-shiny container :3839"]
    auth --> pg["postgres :5432"]

    rshiny --> rapp["R Shiny app (rlang-app/app.R)"]
    pyshiny --> papp["Python Shiny app (python-app/app.py)"]
```

## Nginx Routing Role (Mermaid)

```mermaid
sequenceDiagram
    participant B as Browser
    participant N as Nginx Gateway (:8000)
    participant A as auth-admin (:8080)
    participant R as r-shiny (:3838)
    participant P as python-shiny (:3839)

    B->>N: GET /rlang-app/
    N->>A: auth_request /auth/check
    A-->>N: 401 (not authenticated)
    N-->>B: 302 /auth/login?next=/rlang-app/
    B->>N: POST /auth/login (credentials)
    N->>A: Proxy login
    A-->>B: Session cookie
    B->>N: GET /python-app/ (with cookie)
    N->>A: auth_request /auth/check
    A-->>N: 200 OK
    N->>P: Proxy request
    P-->>N: Shiny response
    N-->>B: Response
```

## Quick Start

### Prerequisites

- Docker Engine 24+
- Docker Compose v2+

### Run

```bash
cp .env.example .env
docker compose build auth-admin
docker compose up -d --no-build
```

For a full clean build on a new machine:

```bash
cp .env.example .env
docker compose up --build
```

### Open

- <http://localhost:8000/auth/login>
- <http://localhost:8000/auth/logout>
- <http://localhost:8000/admin/users>
- <http://localhost:8000/rlang-app>
- <http://localhost:8000/python-app>

### Bootstrap Admin Credentials

- Username: value of `APP_ADMIN_USERNAME` from `.env`
- Password: value of `APP_ADMIN_PASSWORD` from `.env`

The auth service enforces this bootstrap admin user on startup by update/inserting it in PostgreSQL.

## Authentication Layer Usage

### Access Flow

1. Open a protected route such as `/rlang-app/` or `/python-app/`.
2. NGINX calls internal `/_auth_check` (`auth_request`) against the auth service.
3. If no valid session cookie exists, you are redirected to `/auth/login?next=<original-path>`.
4. Submit credentials on `/auth/login`.
5. On success, the auth service sets the session cookie and redirects back to `next`.

### Admin Operations

Use `/admin/users` (admin-only) to:

- create users
- set/reset user passwords
- activate/deactivate users
- delete users (except your own account)

### Logout

- Regular users can open `/auth/logout` to access a dedicated logout page.
- Session termination is executed via CSRF-protected `POST /auth/logout`.
- Active session row is removed from PostgreSQL and the browser cookie is cleared.

### Environment Variables (Auth)

- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`: database credentials
- `APP_ADMIN_USERNAME`, `APP_ADMIN_PASSWORD`: bootstrap admin identity
- `APP_SESSION_COOKIE_NAME`: session cookie key
- `APP_SESSION_TTL_HOURS`: session lifetime
- `APP_COOKIE_SECURE`: set `true` when running behind HTTPS
- `APP_MIN_PASSWORD_LENGTH`: server-side password policy floor

## Authentication ER Diagram (Mermaid)

```mermaid
erDiagram
    USERS ||--o{ SESSIONS : "owns"

    USERS {
        BIGSERIAL id PK
        TEXT username UK
        TEXT password_hash
        BOOLEAN is_admin
        BOOLEAN is_active
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    SESSIONS {
        BIGSERIAL id PK
        BIGINT user_id FK
        CHAR(64) token_hash UK
        TEXT csrf_token
        TIMESTAMPTZ expires_at
        TIMESTAMPTZ created_at
    }
```

## Project Layout

```text
.
├── docker-compose.yml
├── .env.example
├── docker
│   ├── auth-admin/Dockerfile
│   ├── nginx/nginx.conf
│   ├── python-shiny/Dockerfile
│   └── r-shiny/Dockerfile
├── auth-admin
│   ├── app/main.py
│   └── app/templates/*.html
├── python-app/app.py
└── rlang-app/app.R
```

## Security Notes

- Passwords are stored with bcrypt hashes, never plaintext.
- Session cookies are HttpOnly + SameSite and validated on every protected request.
- CSRF tokens are enforced for all state-changing admin/logout forms.
- No secrets are hardcoded in tracked files.
- Containers expose only gateway port `8000` to the host.

## Metadata

- Citation: `CITATION.cff`
- License: `LICENSE`
- Contribution guide: `CONTRIBUTING.md`
- Code of Conduct: `CODE_OF_CONDUCT.md`
- Security policy: `SECURITY.md`
- Changelog: `CHANGELOG.md`
