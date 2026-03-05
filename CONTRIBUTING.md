# Contributing

Thanks for contributing to this template.

## Development Flow

1. Fork and create a feature branch.
2. Keep changes minimal and focused.
3. Verify the stack runs locally:
   - `docker compose up --build`
4. Validate both endpoints:
   - `http://localhost:8000/rlang-app`
   - `http://localhost:8000/python-app`
5. Open a pull request with:
   - problem statement
   - implementation details
   - test evidence

## Standards

- Prefer simple solutions and small blast radius.
- Preserve backward compatibility unless explicitly discussed.
- Do not commit secrets, credentials, or sensitive data.

## Commit Guidance

- Use clear, imperative commit messages.
- Include only files related to the change.

## Add a New Shiny App to the Stack

This stack is designed for path-based routing behind NGINX on port `8000`, with auth enforcement handled at gateway level.

### 1. Choose App Path and Service Name

Pick a unique URL prefix and matching compose service name.
Examples:

- URL path: `/my-new-app/`
- service name: `my-new-app`
- container port: `3840` (or any free internal port)

Keep paths lowercase and hyphenated to match existing conventions.

### 2. Add Application Source

Create the app source directory in repository root and add the app entrypoint.
Examples:

- R Shiny: `my-new-app/app.R`
- Python Shiny: `my-new-app/app.py`

Use a self-contained sample app that can start with no external runtime secrets.

### 3. Add Dockerfile for the New App Service

Create a Dockerfile under `docker/<service-name>/Dockerfile`.

Expected pattern:

1. choose stable base image (`rocker/r-ver:*` for R, `python:3.12-slim` for Python)
2. install runtime dependencies
3. copy app code into `/app`
4. expose internal port only
5. start server binding to `0.0.0.0`

Do not publish container ports directly to host unless there is a specific requirement; traffic should flow through `gateway`.

### 4. Register the Service in `docker-compose.yml`

Add a new service block with:

1. `build.context` and `build.dockerfile`
2. `init: true`
3. healthcheck probing its local listening port
4. `restart: unless-stopped`
5. `stop_grace_period`

Then update `gateway.depends_on` to include the new service with `condition: service_healthy`.

### 5. Add NGINX Route in `docker/nginx/nginx.conf`

Add route handling for the new path.

Required behavior:

1. `location = /my-new-app` should redirect to `/my-new-app/`
2. `location /my-new-app/` should proxy to the new service
3. protected routes should include `auth_request /_auth_check;`
4. protected routes should include `error_page 401 = @auth_signin;`

Follow existing proxy settings (`proxy_http_version`, `Upgrade`, `Connection`, `Host`, `proxy_read_timeout`, `proxy_buffering`).

### 6. Update Documentation

Update all developer-facing docs:

1. `README.md`: add the new app URL in the Open section.
2. `README.md`: update technical stack and topology/sequence diagrams if impacted.
3. `README.md`: update auth flow notes if behavior differs.
4. `CHANGELOG.md`: add an entry for the new app integration.
5. `SECURITY.md`: update only if schema/auth behavior changed.

### 7. Validate End-to-End

Run:

1. `docker compose config`
2. `docker compose build <new-service> gateway`
3. `docker compose up -d --no-build`
4. `docker compose ps`

Smoke tests:

1. Open `http://localhost:8000/my-new-app/`
2. Confirm unauthenticated users are redirected to `/auth/login`
3. Login and verify the app loads
4. Logout via `/auth/logout` and confirm access is blocked again

### 8. Pull Request Checklist for New App Additions

Include in PR description:

1. New app path and service name
2. Changed files list (`docker-compose`, `nginx`, Dockerfile, docs)
3. Health check strategy
4. Auth protection confirmation
5. Manual test evidence (URLs + expected behavior)
