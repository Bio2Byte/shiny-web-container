---
title: Overview
---

# Shiny Web Container Template

Production-oriented template for serving multiple Shiny applications behind a single gateway on port `8000`.

- R Shiny app: `/rlang-app`
- Python Shiny app: `/python-app`
- Auth UI: `/auth/login`
- User admin UI: `/admin/users`

## What This Template Includes

- Multi-container runtime with Docker Compose
- NGINX gateway with path-based routing
- Authentication gate with NGINX `auth_request`
- FastAPI auth/admin service
- Role-based access control (RBAC) per Shiny app
- PostgreSQL user/session persistence
- Security and governance metadata for publication-ready repos

## Documentation Map

- [Quick Start](./quickstart)
- [Architecture](./architecture)
- [Authentication](./authentication)
- [Security](./security)
- [Contributing](./contributing)

## Source of Truth

These pages are derived from and should stay aligned with:

- [`README.md`]({{ site.github.repository_url }}/blob/main/README.md)
- [`SECURITY.md`]({{ site.github.repository_url }}/blob/main/SECURITY.md)
- [`CONTRIBUTING.md`]({{ site.github.repository_url }}/blob/main/CONTRIBUTING.md)
- [`CHANGELOG.md`]({{ site.github.repository_url }}/blob/main/CHANGELOG.md)
- [`LICENSE`]({{ site.github.repository_url }}/blob/main/LICENSE)
- [`CITATION.cff`]({{ site.github.repository_url }}/blob/main/CITATION.cff)
