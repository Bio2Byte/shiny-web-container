---
title: Authentication
---

# Authentication

## High-Level Flow

1. User requests `/rlang-app/` or `/python-app/`.
2. NGINX issues internal auth subrequest to `/_auth_check`.
3. `/_auth_check` proxies to `auth-admin:/auth/check`.
4. If `401`, user is redirected to `/auth/login?next=<original-path>`.
5. If `200`, request is proxied to target Shiny app.

## User-Facing Endpoints

- `GET /auth/login` - login form
- `POST /auth/login` - credential verification + session creation
- `GET /auth/logout` - logout confirmation page
- `POST /auth/logout` - CSRF-validated logout, session delete, cookie clear
- `GET /admin/users` - admin-only user management UI

## Session Model

- Passwords stored as bcrypt hashes.
- Browser receives opaque session token cookie.
- Server stores SHA-256 hash of token (`sessions.token_hash`), not raw token.
- Session is valid only if:
  - user is active
  - session exists
  - session is unexpired

## CSRF Controls

- State-changing requests require a CSRF token.
- Covered operations:
  - logout
  - admin create/update/delete/toggle actions

## Auth Schema (ER)

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
