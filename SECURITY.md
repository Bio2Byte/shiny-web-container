# Security Policy

## Supported Versions

This project currently supports the latest `main` branch.

## Reporting a Vulnerability

Please report suspected vulnerabilities privately to project maintainers.
Do not open public issues for unpatched vulnerabilities.

Include:

- affected component (R app, Python app, gateway, compose)
- reproduction steps
- impact assessment
- suggested mitigation (if available)

## Security Baseline

- No hardcoded credentials in source.
- Containerized service boundaries.
- Gateway-only host exposure on port `8000`.
- Password hashing with bcrypt.
- Nginx `auth_request` gate for protected Shiny routes.
- Session-based auth with HttpOnly cookies and CSRF protection for state-changing forms.
- Role-based authorization for per-app access control.

## Authentication Layer Technical Overview

### Components and Trust Boundaries

- `gateway` (Nginx) is the only public entrypoint and enforces authentication before traffic reaches protected Shiny routes.
- `auth-admin` (FastAPI) owns identity logic: login, logout, session validation, role checks, and admin CRUD for users/roles.
- `postgres` stores users, roles, role-app grants, user-role mappings, and active sessions.
- `r-shiny` and `python-shiny` are treated as protected upstream apps and do not implement independent login logic.

### Route Protection Model

- Protected routes: `/rlang-app/` and `/python-app/`.
- Nginx uses `auth_request` to call an internal endpoint (`/_auth_check`) that proxies to `auth-admin:/auth/check`.
- If auth returns `401`, Nginx redirects the client to `/auth/login?next=<original_path>`.
- If auth returns `403`, Nginx serves `/auth/forbidden` (authenticated but not authorized).
- If auth returns `200`, Nginx forwards the request to the target Shiny app.

### NGINX Implementation Notes

- `/_auth_check` is declared `internal`, so clients cannot call it directly.
- For auth sub-requests, Nginx disables body forwarding (`proxy_pass_request_body off`) and clears `Content-Length` to keep checks lightweight.
- Nginx forwards client cookies to `auth-admin` during checks (`proxy_set_header Cookie $http_cookie`) so session validation is server-side.
- The gateway blocks direct public access to `/auth/check` with `404`; only internal `/_auth_check` is valid for route protection.
- Unauthenticated access to protected routes is handled with `error_page 401 = @auth_signin`, which centralizes redirect behavior.
- `@auth_signin` preserves target navigation via `?next=$request_uri`.
- `/auth/*` and `/admin/*` are proxied to `auth-admin`, while `/rlang-app/*` and `/python-app/*` are proxied only after successful auth checks.
- Nginx app locations map both `401` and `403` explicitly: `401` goes to sign-in redirect and `403` goes to the forbidden page.

### Session and Credential Handling

- Passwords are hashed with `bcrypt` before storage.
- Authentication is session-cookie based.
- Session cookies are configured `HttpOnly`, `SameSite=Lax`, and `Secure` is controlled by `APP_COOKIE_SECURE`.
- Session identifiers are stored server-side as SHA-256 token hashes (`token_hash`), not raw tokens.
- Session validity requires all of: active user, existing session row, and non-expired session timestamp.
- Authorization validity for app routes requires role grant: `admin` users bypass role checks, while non-admin users need `user_roles` membership connected to `role_app_access` for the requested app key.

### CSRF and Logout Semantics

- State-changing operations require CSRF token validation (admin user mutations and logout).
- `GET /auth/logout` provides a user-facing confirmation page.
- `POST /auth/logout` validates CSRF, deletes the server-side session row, and clears the browser cookie.

### Auth-App Implementation Notes

- The auth service initializes schema and bootstrap admin during app lifespan startup.
- Database writes and reads use parameterized SQL through `psycopg` to prevent SQL injection.

Login flow details:

1. Verify submitted password against stored bcrypt hash.
2. Generate a random session token.
3. Store only SHA-256 token hash in `sessions.token_hash`.
4. Generate and store a distinct CSRF token.
5. Set raw session token as the browser cookie value.

`/auth/check` validation checks:

1. Cookie exists.
2. Token hash exists in `sessions`.
3. Session is not expired (`expires_at > NOW()`).
4. Associated user is still active.
5. If request targets a protected app, role permission exists for that app.

`/auth/check` response contract:

1. `200` for valid sessions.
2. `401` for missing, invalid, or expired sessions.
3. `403` for authenticated users missing required app permission.

User-management safeguards:

1. Prevent deleting/deactivating the last active admin.
2. Prevent self-delete and self-deactivation for current admin session.
3. Invalidate all sessions when a user is deactivated.
4. Role assignment changes take effect immediately for subsequent auth checks.

### Admin and Safety Constraints

- Bootstrap admin credentials are sourced from environment variables and upserted at auth-service startup.
- Deletion/deactivation protections prevent removing the last active admin account.
- Deactivating a user invalidates all active sessions for that user.

### Security Assumptions

- Production deployments should run behind HTTPS and set `APP_COOKIE_SECURE=true`.
- Secrets are supplied via environment management and are not committed to source control.
- Internal service-to-service traffic runs inside the Compose network boundary.
