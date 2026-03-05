---
title: Contributing
---

# Contributing

For full contribution rules see [`CONTRIBUTING.md`]({{ site.github.repository_url }}/blob/main/CONTRIBUTING.md).

## Standard Flow

1. Create a feature branch.
2. Keep scope minimal and focused.
3. Validate locally with Compose.
4. Submit PR with problem, implementation, and test evidence.

## Add a New Shiny App

When integrating a new Shiny app in this template:

1. Choose unique route and service name.
2. Add app source and dedicated Dockerfile.
3. Register service + healthcheck in `docker-compose.yml`.
4. Add NGINX route and apply auth gate (`auth_request` + `401` redirect).
5. Update docs and changelog.
6. Verify login-protected access and logout behavior.

## PR Checklist

- Service is healthy in `docker compose ps`
- Route works through `gateway` only
- Unauthenticated access redirects to login
- Authenticated access reaches app
- Security/docs updates included when relevant
