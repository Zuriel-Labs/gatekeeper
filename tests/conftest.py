"""Shared test fixtures for Gatekeeper tests.

Provides:
- In-memory SQLite async DB
- FastAPI test app with patched settings (all modules enabled)
- httpx AsyncClient for integration tests
- Pre-seeded API keys and admin auth headers
"""

import base64
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gatekeeper.db import Base
from gatekeeper.models import ApiKey, RoutePolicy

# ── Settings fixture ──────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def test_settings():
    """Create a Settings object with test values, bypassing .env and file persistence."""
    from gatekeeper.config import Settings

    s = Settings(
        _env_file=None,
        secret_key="test-secret-key-that-is-long-enough",
        admin_password="test-admin-pass",
        admin_username="admin",
        encryption_key=Fernet.generate_key().decode(),
        database_url="sqlite+aiosqlite:///:memory:",
        drive_enabled=True,
        gmail_enabled=True,
        calendar_enabled=True,
        mcp_enabled=False,
    )
    return s


# ── Database fixtures ─────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_engine():
    """Create an in-memory SQLite async engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session for tests."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


# ── App fixture (patched settings + seeded DB) ───────────────────────────


@pytest.fixture(scope="session", autouse=True)
def stub_validate_api_key():
    """Patch API key validation to a no-op fake for the test session."""
    from fastapi import Request

    import gatekeeper.auth
    from gatekeeper.models import ApiKey

    async def _fake_validate(request: Request):
        key = ApiKey(
            name="test",
            key_hash="$2b$12$fakehashfakehashfakehashfakehashfa",
            key_prefix="gkp_test",
            permissions="*",
        )
        request.state.api_key = key
        return key

    original = gatekeeper.auth.validate_api_key
    gatekeeper.auth.validate_api_key = _fake_validate
    import gatekeeper.api.router as router_mod

    router_mod.validate_api_key = _fake_validate
    yield
    gatekeeper.auth.validate_api_key = original
    router_mod.validate_api_key = original


@pytest_asyncio.fixture
async def app(db_engine, test_settings):
    """Create a FastAPI test app with settings overridden and DB seeded.

    Patches gatekeeper.config.settings so all modules pick up the test config,
    then patches the DB session factories so the app uses the in-memory test DB.
    Seeds default route policies for all three modules.
    """
    import gatekeeper.admin.routes
    import gatekeeper.auth
    import gatekeeper.config
    import gatekeeper.db
    from gatekeeper.modules import load_module

    # Patch settings onto the config module BEFORE create_app
    original_settings = gatekeeper.config.settings
    gatekeeper.config.settings = test_settings

    # Patch settings on modules that import settings directly
    original_auth_settings = getattr(gatekeeper.auth, "settings", None)
    gatekeeper.auth.settings = test_settings

    original_routes_settings = getattr(gatekeeper.admin.routes, "settings", None)
    gatekeeper.admin.routes.settings = test_settings

    # Build a test DB session factory
    test_session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Patch DB engine and session factory
    original_engine = gatekeeper.db.engine
    original_async_session = gatekeeper.db.async_session
    gatekeeper.db.engine = db_engine
    gatekeeper.db.async_session = test_session_factory

    # Patch get_db_session dependency used by auth
    original_get_db_session = gatekeeper.auth.get_db_session

    async def _test_get_db_session():
        async with test_session_factory() as session:
            yield session

    gatekeeper.auth.get_db_session = _test_get_db_session

    # Patch async_session in admin routes
    original_admin_async_session = gatekeeper.admin.routes.async_session
    gatekeeper.admin.routes.async_session = test_session_factory

    # Patch google_client settings
    original_gc_settings = None
    try:
        import gatekeeper.google_client

        original_gc_settings = getattr(gatekeeper.google_client, "settings", None)
        gatekeeper.google_client.settings = test_settings
    except Exception:
        pass

    # Patch encryption settings
    original_enc_settings = None
    try:
        import gatekeeper.encryption

        original_enc_settings = getattr(gatekeeper.encryption, "settings", None)
        gatekeeper.encryption.settings = test_settings
    except Exception:
        pass

    # Seed default route policies
    async with test_session_factory() as seed_session:
        for module_name in ["drive", "gmail", "calendar"]:
            mod = load_module(module_name)
            if mod is None:
                continue
            for route in mod.get_routes():
                existing = await seed_session.execute(
                    select(RoutePolicy).where(
                        RoutePolicy.module == module_name,
                        RoutePolicy.route == route.route_id,
                    )
                )
                if existing.scalar_one_or_none() is None:
                    defaults = mod.get_default_policies().get(route.route_id, {})
                    policy = RoutePolicy(
                        module=module_name,
                        route=route.route_id,
                        enabled=defaults.get("enabled", route.enabled_by_default),
                        policy_config=__import__("json").dumps(
                            defaults.get("config", route.default_policy)
                        ),
                        description=route.description,
                    )
                    seed_session.add(policy)
        await seed_session.commit()

    # Clear module cache before creating app
    from gatekeeper.modules import _loaded_modules

    _loaded_modules.clear()

    try:
        from gatekeeper.main import create_app

        application = create_app()
        yield application
    finally:
        # Restore originals
        gatekeeper.config.settings = original_settings
        gatekeeper.db.engine = original_engine
        gatekeeper.db.async_session = original_async_session
        gatekeeper.auth.get_db_session = original_get_db_session
        gatekeeper.admin.routes.async_session = original_admin_async_session
        if original_auth_settings is not None:
            gatekeeper.auth.settings = original_auth_settings
        if original_routes_settings is not None:
            gatekeeper.admin.routes.settings = original_routes_settings
        if original_gc_settings is not None:
            gatekeeper.google_client.settings = original_gc_settings
        if original_enc_settings is not None:
            gatekeeper.encryption.settings = original_enc_settings

        # Clear cached module instances
        _loaded_modules.clear()


# ── HTTP client fixtures ──────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(app):
    """Async HTTP client using the test app's ASGI transport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── API key fixtures ──────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def api_key(db_session):
    """Create a real ApiKey in the DB session and return the raw key string."""
    raw, hash_val, prefix = ApiKey.generate_key()
    key = ApiKey(
        name="test-key",
        key_hash=hash_val,
        key_prefix=prefix,
        permissions="*",
        is_active=True,
    )
    db_session.add(key)
    await db_session.commit()
    await db_session.refresh(key)
    return raw


@pytest_asyncio.fixture
async def drive_only_key(db_session):
    """Create an ApiKey with only 'drive' permissions."""
    raw, hash_val, prefix = ApiKey.generate_key()
    key = ApiKey(
        name="drive-only-key",
        key_hash=hash_val,
        key_prefix=prefix,
        permissions="drive",
        is_active=True,
    )
    db_session.add(key)
    await db_session.commit()
    await db_session.refresh(key)
    return raw


@pytest_asyncio.fixture
async def inactive_key(db_session):
    """Create an inactive ApiKey."""
    raw, hash_val, prefix = ApiKey.generate_key()
    key = ApiKey(
        name="inactive-key",
        key_hash=hash_val,
        key_prefix=prefix,
        permissions="*",
        is_active=False,
    )
    db_session.add(key)
    await db_session.commit()
    await db_session.refresh(key)
    return raw


# ── Auth header fixtures ──────────────────────────────────────────────────


@pytest.fixture
def admin_headers(test_settings):
    """Return HTTP Basic auth headers for the test admin user."""
    cred = f"{test_settings.admin_username}:{test_settings.admin_password}"
    encoded = base64.b64encode(cred.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


@pytest.fixture
def wrong_admin_headers():
    """Return HTTP Basic auth headers with wrong password."""
    encoded = base64.b64encode(b"admin:wrong-password").decode()
    return {"Authorization": f"Basic {encoded}"}
