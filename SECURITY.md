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
