from __future__ import annotations

import os
import re
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import bcrypt
import psycopg
from fastapi import FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from psycopg.rows import dict_row

USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_.-]{3,64}$")
ROLE_NAME_REGEX = re.compile(r"^[a-z0-9_-]{3,64}$")
ALLOWED_NEXT_PREFIXES = ("/rlang-app", "/python-app", "/admin")

APP_ACCESS_OPTIONS: list[tuple[str, str]] = [
    ("rlang_app", "R Shiny App (/rlang-app)"),
    ("python_app", "Python Shiny App (/python-app)"),
]
APP_ACCESS_LABELS: dict[str, str] = dict(APP_ACCESS_OPTIONS)
APP_ACCESS_KEYS = {key for key, _ in APP_ACCESS_OPTIONS}


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    session_cookie_name: str
    session_ttl_hours: int
    cookie_secure: bool
    min_password_length: int
    bootstrap_admin_username: str
    bootstrap_admin_password: str


def _read_env(name: str, *, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and (value is None or value == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    if value is None:
        raise RuntimeError(f"Environment variable {name} is not set")
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


SETTINGS = Settings(
    db_host=_read_env("DB_HOST", default="postgres"),
    db_port=int(_read_env("DB_PORT", default="5432")),
    db_name=_read_env("DB_NAME", default="shiny_auth"),
    db_user=_read_env("DB_USER", default="shiny_user"),
    db_password=_read_env("DB_PASSWORD", required=True),
    session_cookie_name=_read_env("APP_SESSION_COOKIE_NAME", default="shiny_session"),
    session_ttl_hours=int(_read_env("APP_SESSION_TTL_HOURS", default="12")),
    cookie_secure=_bool_env("APP_COOKIE_SECURE", default=False),
    min_password_length=int(_read_env("APP_MIN_PASSWORD_LENGTH", default="12")),
    bootstrap_admin_username=_read_env("APP_ADMIN_USERNAME", required=True),
    bootstrap_admin_password=_read_env("APP_ADMIN_PASSWORD", required=True),
)

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


@asynccontextmanager
async def _lifespan(_: FastAPI):
    _initialize_database()
    yield


app = FastAPI(title="Shiny Auth Admin", version="0.2.0", lifespan=_lifespan)


def _get_db_connection() -> psycopg.Connection:
    return psycopg.connect(
        host=SETTINGS.db_host,
        port=SETTINGS.db_port,
        dbname=SETTINGS.db_name,
        user=SETTINGS.db_user,
        password=SETTINGS.db_password,
        row_factory=dict_row,
    )


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _hash_token(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()


def _normalize_next_path(next_path: str | None) -> str:
    if not next_path:
        return "/rlang-app/"
    if not next_path.startswith("/") or next_path.startswith("//"):
        # Security control: prevent open redirects to external domains.
        return "/rlang-app/"
    if any(next_path.startswith(prefix) for prefix in ALLOWED_NEXT_PREFIXES):
        return next_path
    return "/rlang-app/"


def _admin_redirect(*, message: str | None = None, error: str | None = None) -> RedirectResponse:
    query: dict[str, str] = {}
    if message:
        query["message"] = message
    if error:
        query["error"] = error
    suffix = f"?{urlencode(query)}" if query else ""
    return RedirectResponse(url=f"/admin/users{suffix}", status_code=status.HTTP_303_SEE_OTHER)


def _roles_redirect(*, message: str | None = None, error: str | None = None) -> RedirectResponse:
    query: dict[str, str] = {}
    if message:
        query["message"] = message
    if error:
        query["error"] = error
    suffix = f"?{urlencode(query)}" if query else ""
    return RedirectResponse(url=f"/admin/roles{suffix}", status_code=status.HTTP_303_SEE_OTHER)


def _validate_password_rules(password: str) -> str | None:
    if len(password) < SETTINGS.min_password_length:
        return f"Password must have at least {SETTINGS.min_password_length} characters."
    return None


def _validate_username_rules(username: str) -> str | None:
    if not USERNAME_REGEX.fullmatch(username):
        return "Username must match [a-zA-Z0-9_.-] and be 3-64 chars."
    return None


def _validate_role_name(role_name: str) -> str | None:
    if not ROLE_NAME_REGEX.fullmatch(role_name):
        return "Role name must match [a-z0-9_-] and be 3-64 chars."
    return None


def _normalize_app_keys(app_keys: list[str]) -> list[str]:
    normalized = sorted({key.strip() for key in app_keys if key.strip() in APP_ACCESS_KEYS})
    return normalized


def _validate_csrf(session: dict[str, Any], csrf_token: str | None) -> None:
    # Security control: all state-changing browser form submissions require CSRF validation.
    if not csrf_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing CSRF token.")
    if not secrets.compare_digest(session["csrf_token"], csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")


def _create_session(conn: psycopg.Connection, user_id: int) -> str:
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SETTINGS.session_ttl_hours)

    with conn.cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE expires_at <= NOW()")
        cur.execute(
            """
            INSERT INTO sessions (user_id, token_hash, csrf_token, expires_at)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, token_hash, csrf_token, expires_at),
        )
    return raw_token


def _get_active_session(request: Request) -> dict[str, Any] | None:
    raw_token = request.cookies.get(SETTINGS.session_cookie_name)
    if not raw_token:
        return None

    token_hash = _hash_token(raw_token)
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  s.id AS session_id,
                  s.user_id AS user_id,
                  s.csrf_token AS csrf_token,
                  s.expires_at AS expires_at,
                  u.username AS username,
                  u.is_admin AS is_admin,
                  u.is_active AS is_active
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = %s
                  AND s.expires_at > NOW()
                  AND u.is_active = TRUE
                """,
                (token_hash,),
            )
            return cur.fetchone()


def _set_session_cookie(response: RedirectResponse, raw_token: str) -> None:
    # Security control: HttpOnly cookie blocks JavaScript token access (XSS hardening).
    response.set_cookie(
        key=SETTINGS.session_cookie_name,
        value=raw_token,
        max_age=SETTINGS.session_ttl_hours * 3600,
        httponly=True,
        secure=SETTINGS.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: RedirectResponse) -> None:
    response.delete_cookie(key=SETTINGS.session_cookie_name, path="/")


def _extract_requested_app_key(request: Request) -> str | None:
    original_uri = request.headers.get("x-original-uri", "")
    if not original_uri:
        return None

    path = urlsplit(original_uri).path
    if path == "/rlang-app" or path.startswith("/rlang-app/"):
        return "rlang_app"
    if path == "/python-app" or path.startswith("/python-app/"):
        return "python_app"
    return None


def _user_has_app_access(conn: psycopg.Connection, user_id: int, app_key: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM user_roles ur
            JOIN role_app_access raa ON raa.role_id = ur.role_id
            WHERE ur.user_id = %s
              AND raa.app_key = %s
            LIMIT 1
            """,
            (user_id, app_key),
        )
        return cur.fetchone() is not None


def _fetch_roles_with_permissions(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              r.id,
              r.name,
              r.description,
              r.created_at,
              r.updated_at,
              COALESCE(
                ARRAY_AGG(DISTINCT raa.app_key) FILTER (WHERE raa.app_key IS NOT NULL),
                '{}'::text[]
              ) AS app_keys,
              COUNT(DISTINCT ur.user_id)::int AS user_count
            FROM roles r
            LEFT JOIN role_app_access raa ON raa.role_id = r.id
            LEFT JOIN user_roles ur ON ur.role_id = r.id
            GROUP BY r.id
            ORDER BY r.name ASC
            """
        )
        rows = cur.fetchall()

    for row in rows:
        row["app_keys"] = sorted(row["app_keys"])
        row["app_labels"] = [APP_ACCESS_LABELS[key] for key in row["app_keys"] if key in APP_ACCESS_LABELS]
    return rows


def _fetch_user_roles_map(conn: psycopg.Connection) -> dict[int, list[dict[str, Any]]]:
    mapping: dict[int, list[dict[str, Any]]] = defaultdict(list)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              ur.user_id,
              r.id AS role_id,
              r.name AS role_name
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            ORDER BY r.name ASC
            """
        )
        for row in cur.fetchall():
            mapping[int(row["user_id"])].append(
                {
                    "id": int(row["role_id"]),
                    "name": row["role_name"],
                }
            )
    return mapping


def _replace_role_permissions(conn: psycopg.Connection, role_id: int, app_keys: list[str]) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM role_app_access WHERE role_id = %s", (role_id,))
        for app_key in app_keys:
            cur.execute(
                """
                INSERT INTO role_app_access (role_id, app_key)
                VALUES (%s, %s)
                ON CONFLICT (role_id, app_key) DO NOTHING
                """,
                (role_id, app_key),
            )


def _require_admin_session(request: Request, next_path: str) -> tuple[dict[str, Any] | None, RedirectResponse | None]:
    session = _get_active_session(request)
    if not session:
        return None, RedirectResponse(url=f"/auth/login?next={next_path}", status_code=status.HTTP_303_SEE_OTHER)
    if not session["is_admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required.")
    return session, None


def _initialize_database() -> None:
    for attempt in range(1, 31):
        try:
            with _get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS users (
                          id BIGSERIAL PRIMARY KEY,
                          username TEXT NOT NULL UNIQUE,
                          password_hash TEXT NOT NULL,
                          is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                          is_active BOOLEAN NOT NULL DEFAULT TRUE,
                          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS sessions (
                          id BIGSERIAL PRIMARY KEY,
                          user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                          token_hash CHAR(64) NOT NULL UNIQUE,
                          csrf_token TEXT NOT NULL,
                          expires_at TIMESTAMPTZ NOT NULL,
                          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS roles (
                          id BIGSERIAL PRIMARY KEY,
                          name TEXT NOT NULL UNIQUE,
                          description TEXT NOT NULL DEFAULT '',
                          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS role_app_access (
                          role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                          app_key TEXT NOT NULL CHECK (app_key IN ('rlang_app', 'python_app')),
                          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                          PRIMARY KEY (role_id, app_key)
                        )
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS user_roles (
                          user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                          role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                          PRIMARY KEY (user_id, role_id)
                        )
                        """
                    )

                    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions (expires_at)")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id)")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_role_id ON user_roles (role_id)")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_role_app_access_app_key ON role_app_access (app_key)")

                    admin_password_hash = _hash_password(SETTINGS.bootstrap_admin_password)
                    # Security control: bootstrap admin is always stored hashed, never plaintext.
                    cur.execute(
                        """
                        INSERT INTO users (username, password_hash, is_admin, is_active)
                        VALUES (%s, %s, TRUE, TRUE)
                        ON CONFLICT (username)
                        DO UPDATE SET
                          password_hash = EXCLUDED.password_hash,
                          is_admin = TRUE,
                          is_active = TRUE,
                          updated_at = NOW()
                        """,
                        (SETTINGS.bootstrap_admin_username, admin_password_hash),
                    )

                    default_roles = [
                        ("rlang_access", "Access to R Shiny app", ["rlang_app"]),
                        ("python_access", "Access to Python Shiny app", ["python_app"]),
                        ("all_apps_access", "Access to all Shiny apps", ["rlang_app", "python_app"]),
                    ]
                    for role_name, role_description, app_keys in default_roles:
                        cur.execute(
                            """
                            INSERT INTO roles (name, description)
                            VALUES (%s, %s)
                            ON CONFLICT (name)
                            DO NOTHING
                            RETURNING id
                            """,
                            (role_name, role_description),
                        )
                        role_row = cur.fetchone()
                        if role_row:
                            role_id = int(role_row["id"])
                        else:
                            cur.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
                            role_id = int(cur.fetchone()["id"])
                        for app_key in app_keys:
                            cur.execute(
                                """
                                INSERT INTO role_app_access (role_id, app_key)
                                VALUES (%s, %s)
                                ON CONFLICT (role_id, app_key) DO NOTHING
                                """,
                                (role_id, app_key),
                            )

                conn.commit()
            return
        except psycopg.OperationalError:
            if attempt == 30:
                raise
            time.sleep(2)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/auth/login", response_class=HTMLResponse)
def auth_login_page(request: Request, next: str | None = None) -> Response:
    existing_session = _get_active_session(request)
    next_path = _normalize_next_path(next)
    if existing_session:
        return RedirectResponse(url=next_path, status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None, "next_path": next_path},
    )


@app.post("/auth/login", response_class=HTMLResponse)
def auth_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next_path: str = Form("/rlang-app/"),
) -> Response:
    username = username.strip()
    next_path = _normalize_next_path(next_path)

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, username, password_hash, is_active
                FROM users
                WHERE username = %s
                """,
                (username,),
            )
            user = cur.fetchone()
            if not user or not user["is_active"] or not _verify_password(password, user["password_hash"]):
                return templates.TemplateResponse(
                    request=request,
                    name="login.html",
                    context={
                        "error": "Invalid credentials.",
                        "next_path": next_path,
                    },
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

            raw_token = _create_session(conn, int(user["id"]))
        conn.commit()

    response = RedirectResponse(url=next_path, status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, raw_token)
    return response


@app.get("/auth/logout", response_class=HTMLResponse)
def auth_logout_page(request: Request) -> Response:
    session = _get_active_session(request)
    return templates.TemplateResponse(
        request=request,
        name="logout.html",
        context={"session": session},
    )


@app.post("/auth/logout")
def auth_logout(request: Request, csrf_token: str = Form(...)) -> RedirectResponse:
    session = _get_active_session(request)
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    _clear_session_cookie(response)
    if not session:
        return response

    _validate_csrf(session, csrf_token)
    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE id = %s", (session["session_id"],))
        conn.commit()
    return response


@app.get("/auth/forbidden", response_class=HTMLResponse)
def auth_forbidden_page(request: Request) -> Response:
    session = _get_active_session(request)
    return templates.TemplateResponse(
        request=request,
        name="forbidden.html",
        context={"session": session},
        status_code=status.HTTP_403_FORBIDDEN,
    )


@app.get("/auth/check")
def auth_check(request: Request) -> PlainTextResponse:
    session = _get_active_session(request)
    if not session:
        return PlainTextResponse("unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

    app_key = _extract_requested_app_key(request)
    if app_key and not session["is_admin"]:
        with _get_db_connection() as conn:
            if not _user_has_app_access(conn, int(session["user_id"]), app_key):
                return PlainTextResponse("forbidden", status_code=status.HTTP_403_FORBIDDEN)

    response = PlainTextResponse("ok", status_code=status.HTTP_200_OK)
    response.headers["X-Auth-User"] = session["username"]
    response.headers["X-Auth-Role"] = "admin" if session["is_admin"] else "user"
    if app_key:
        response.headers["X-Auth-App"] = app_key
    return response


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(
    request: Request,
    message: str | None = None,
    error: str | None = None,
) -> Response:
    session, redirect = _require_admin_session(request, "/admin/users")
    if redirect:
        return redirect

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, username, is_admin, is_active, created_at, updated_at
                FROM users
                ORDER BY username ASC
                """
            )
            users = cur.fetchall()
        roles = _fetch_roles_with_permissions(conn)
        user_roles_by_user = _fetch_user_roles_map(conn)

    return templates.TemplateResponse(
        request=request,
        name="admin_users.html",
        context={
            "users": users,
            "roles": roles,
            "user_roles_by_user": user_roles_by_user,
            "session": session,
            "message": message,
            "error": error,
            "min_password_length": SETTINGS.min_password_length,
        },
    )


@app.post("/admin/users/create")
def admin_create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    is_admin: str | None = Form(default=None),
) -> RedirectResponse:
    session, redirect = _require_admin_session(request, "/admin/users")
    if redirect:
        return redirect
    _validate_csrf(session, csrf_token)

    username = username.strip()
    username_error = _validate_username_rules(username)
    if username_error:
        return _admin_redirect(error=username_error)

    password_error = _validate_password_rules(password)
    if password_error:
        return _admin_redirect(error=password_error)

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
            if cur.fetchone():
                return _admin_redirect(error="Username already exists.")

            cur.execute(
                """
                INSERT INTO users (username, password_hash, is_admin, is_active)
                VALUES (%s, %s, %s, TRUE)
                """,
                (username, _hash_password(password), is_admin == "on"),
            )
        conn.commit()

    return _admin_redirect(message=f"User '{username}' created.")


@app.post("/admin/users/{user_id}/password")
def admin_set_password(
    request: Request,
    user_id: int,
    password: str = Form(...),
    csrf_token: str = Form(...),
) -> RedirectResponse:
    session, redirect = _require_admin_session(request, "/admin/users")
    if redirect:
        return redirect
    _validate_csrf(session, csrf_token)

    password_error = _validate_password_rules(password)
    if password_error:
        return _admin_redirect(error=password_error)

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET password_hash = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING username
                """,
                (_hash_password(password), user_id),
            )
            updated = cur.fetchone()
            if not updated:
                return _admin_redirect(error="User not found.")
        conn.commit()
    return _admin_redirect(message=f"Password updated for '{updated['username']}'.")


@app.post("/admin/users/{user_id}/toggle-active")
def admin_toggle_user_active(
    request: Request,
    user_id: int,
    csrf_token: str = Form(...),
) -> RedirectResponse:
    session, redirect = _require_admin_session(request, "/admin/users")
    if redirect:
        return redirect
    _validate_csrf(session, csrf_token)

    if int(session["user_id"]) == user_id:
        return _admin_redirect(error="You cannot deactivate your own account.")

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username, is_admin, is_active FROM users WHERE id = %s",
                (user_id,),
            )
            target = cur.fetchone()
            if not target:
                return _admin_redirect(error="User not found.")

            if target["is_admin"] and target["is_active"]:
                cur.execute("SELECT COUNT(*) AS count FROM users WHERE is_admin = TRUE AND is_active = TRUE")
                admin_count = int(cur.fetchone()["count"])
                if admin_count <= 1:
                    return _admin_redirect(error="Cannot deactivate the last active admin.")

            cur.execute(
                """
                UPDATE users
                SET is_active = NOT is_active, updated_at = NOW()
                WHERE id = %s
                RETURNING username, is_active
                """,
                (user_id,),
            )
            updated = cur.fetchone()
            if not updated:
                return _admin_redirect(error="User not found.")

            if not updated["is_active"]:
                cur.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        conn.commit()

    status_label = "activated" if updated["is_active"] else "deactivated"
    return _admin_redirect(message=f"User '{updated['username']}' {status_label}.")


@app.post("/admin/users/{user_id}/delete")
def admin_delete_user(
    request: Request,
    user_id: int,
    csrf_token: str = Form(...),
) -> RedirectResponse:
    session, redirect = _require_admin_session(request, "/admin/users")
    if redirect:
        return redirect
    _validate_csrf(session, csrf_token)

    if int(session["user_id"]) == user_id:
        return _admin_redirect(error="You cannot delete your own account.")

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username, is_admin, is_active FROM users WHERE id = %s",
                (user_id,),
            )
            target = cur.fetchone()
            if not target:
                return _admin_redirect(error="User not found.")

            if target["is_admin"] and target["is_active"]:
                cur.execute("SELECT COUNT(*) AS count FROM users WHERE is_admin = TRUE AND is_active = TRUE")
                admin_count = int(cur.fetchone()["count"])
                if admin_count <= 1:
                    return _admin_redirect(error="Cannot delete the last active admin.")

            cur.execute("DELETE FROM users WHERE id = %s RETURNING username", (user_id,))
            deleted = cur.fetchone()
        conn.commit()

    return _admin_redirect(message=f"User '{deleted['username']}' deleted.")


@app.post("/admin/users/{user_id}/roles/add")
def admin_add_user_role(
    request: Request,
    user_id: int,
    role_id: int = Form(...),
    csrf_token: str = Form(...),
) -> RedirectResponse:
    session, redirect = _require_admin_session(request, "/admin/users")
    if redirect:
        return redirect
    _validate_csrf(session, csrf_token)

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if not user:
                return _admin_redirect(error="User not found.")

            cur.execute("SELECT name FROM roles WHERE id = %s", (role_id,))
            role = cur.fetchone()
            if not role:
                return _admin_redirect(error="Role not found.")

            cur.execute(
                """
                INSERT INTO user_roles (user_id, role_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, role_id) DO NOTHING
                """,
                (user_id, role_id),
            )
        conn.commit()

    return _admin_redirect(message=f"Role '{role['name']}' assigned to '{user['username']}'.")


@app.post("/admin/users/{user_id}/roles/{role_id}/remove")
def admin_remove_user_role(
    request: Request,
    user_id: int,
    role_id: int,
    csrf_token: str = Form(...),
) -> RedirectResponse:
    session, redirect = _require_admin_session(request, "/admin/users")
    if redirect:
        return redirect
    _validate_csrf(session, csrf_token)

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if not user:
                return _admin_redirect(error="User not found.")

            cur.execute("SELECT name FROM roles WHERE id = %s", (role_id,))
            role = cur.fetchone()
            if not role:
                return _admin_redirect(error="Role not found.")

            cur.execute(
                "DELETE FROM user_roles WHERE user_id = %s AND role_id = %s",
                (user_id, role_id),
            )
        conn.commit()

    return _admin_redirect(message=f"Role '{role['name']}' removed from '{user['username']}'.")


@app.get("/admin/roles", response_class=HTMLResponse)
def admin_roles_page(
    request: Request,
    message: str | None = None,
    error: str | None = None,
) -> Response:
    session, redirect = _require_admin_session(request, "/admin/roles")
    if redirect:
        return redirect

    with _get_db_connection() as conn:
        roles = _fetch_roles_with_permissions(conn)

    return templates.TemplateResponse(
        request=request,
        name="admin_roles.html",
        context={
            "session": session,
            "roles": roles,
            "app_access_options": APP_ACCESS_OPTIONS,
            "message": message,
            "error": error,
        },
    )


@app.post("/admin/roles/create")
def admin_create_role(
    request: Request,
    role_name: str = Form(...),
    description: str = Form(""),
    app_keys: list[str] = Form(default=[]),
    csrf_token: str = Form(...),
) -> RedirectResponse:
    session, redirect = _require_admin_session(request, "/admin/roles")
    if redirect:
        return redirect
    _validate_csrf(session, csrf_token)

    role_name = role_name.strip().lower()
    role_name_error = _validate_role_name(role_name)
    if role_name_error:
        return _roles_redirect(error=role_name_error)

    description = description.strip()
    normalized_app_keys = _normalize_app_keys(app_keys)
    if not normalized_app_keys:
        return _roles_redirect(error="Select at least one app access for the role.")

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM roles WHERE name = %s", (role_name,))
            if cur.fetchone():
                return _roles_redirect(error="Role name already exists.")

            cur.execute(
                """
                INSERT INTO roles (name, description)
                VALUES (%s, %s)
                RETURNING id
                """,
                (role_name, description),
            )
            role_id = int(cur.fetchone()["id"])

        _replace_role_permissions(conn, role_id, normalized_app_keys)
        conn.commit()

    return _roles_redirect(message=f"Role '{role_name}' created.")


@app.post("/admin/roles/{role_id}/update")
def admin_update_role(
    request: Request,
    role_id: int,
    role_name: str = Form(...),
    description: str = Form(""),
    app_keys: list[str] = Form(default=[]),
    csrf_token: str = Form(...),
) -> RedirectResponse:
    session, redirect = _require_admin_session(request, "/admin/roles")
    if redirect:
        return redirect
    _validate_csrf(session, csrf_token)

    role_name = role_name.strip().lower()
    role_name_error = _validate_role_name(role_name)
    if role_name_error:
        return _roles_redirect(error=role_name_error)

    description = description.strip()
    normalized_app_keys = _normalize_app_keys(app_keys)
    if not normalized_app_keys:
        return _roles_redirect(error="Select at least one app access for the role.")

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM roles WHERE id = %s", (role_id,))
            if not cur.fetchone():
                return _roles_redirect(error="Role not found.")

            cur.execute("SELECT 1 FROM roles WHERE name = %s AND id <> %s", (role_name, role_id))
            if cur.fetchone():
                return _roles_redirect(error="Role name already exists.")

            cur.execute(
                """
                UPDATE roles
                SET name = %s, description = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (role_name, description, role_id),
            )

        _replace_role_permissions(conn, role_id, normalized_app_keys)
        conn.commit()

    return _roles_redirect(message=f"Role '{role_name}' updated.")


@app.post("/admin/roles/{role_id}/delete")
def admin_delete_role(
    request: Request,
    role_id: int,
    csrf_token: str = Form(...),
) -> RedirectResponse:
    session, redirect = _require_admin_session(request, "/admin/roles")
    if redirect:
        return redirect
    _validate_csrf(session, csrf_token)

    with _get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM roles WHERE id = %s", (role_id,))
            role = cur.fetchone()
            if not role:
                return _roles_redirect(error="Role not found.")

            cur.execute(
                "SELECT COUNT(*) AS count FROM user_roles WHERE role_id = %s",
                (role_id,),
            )
            assigned_count = int(cur.fetchone()["count"])

            cur.execute("DELETE FROM roles WHERE id = %s", (role_id,))
        conn.commit()

    return _roles_redirect(
        message=f"Role '{role['name']}' deleted (removed from {assigned_count} user(s))."
    )
