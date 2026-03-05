# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-03-05

### Added

- Dual-app architecture:
  - R Shiny sample app at `/rlang-app`
  - Python Shiny sample app at `/python-app`
- Nginx gateway on host port `8000`
- Docker Compose orchestration for both apps and gateway
- Repository metadata and governance files

### Changed

- Added authentication gate in Nginx via `auth_request`
- Added `auth-admin` FastAPI service for login/logout and user CRUD
- Added PostgreSQL service for users and sessions
- Added `.env.example` for credential/bootstrap configuration
- Added GitHub Pages documentation content under `docs/` aligned with README, SECURITY, and CONTRIBUTING
- Added RBAC role model (`roles`, `user_roles`, `role_app_access`) with app-scoped authorization checks
- Added admin role-management UI (`/admin/roles`) and user-role assignment controls
