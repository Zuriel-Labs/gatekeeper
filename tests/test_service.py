"""Tests for gatekeeper.service — systemd service management (user and system scope)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from gatekeeper.service import (
    SERVICE_SYSTEM_TEMPLATE,
    SERVICE_UNIT,
    SERVICE_USER_TEMPLATE,
    _is_systemd_available,
    _resolve_exec_path,
    _resolve_work_dir,
    _unit_exists,
    _unit_path,
    disable_service,
    enable_service,
    install_service,
    restart_service,
    uninstall_service,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(tmp_path):
    """Create a mock settings object with a tmp_path database URL."""
    from gatekeeper.config import Settings

    db_path = tmp_path / "gatekeeper.db"
    return Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        google_client_id="test-id",
        google_client_secret="test-secret",
        google_token_file=str(tmp_path / "token.json"),
    )


# ---------------------------------------------------------------------------
# Unit path / template tests
# ---------------------------------------------------------------------------


class TestUnitPath:
    """Tests for _unit_path and unit file generation."""

    def test_unit_path_user_scope(self, tmp_path):
        """User scope unit file should live under ~/.config/systemd/user/."""
        result = _unit_path("user")
        assert result.name == "gatekeeper.service"
        assert ".config/systemd/user" in str(result)

    def test_unit_path_system_scope(self):
        """System scope unit file should live under /etc/systemd/system/."""
        result = _unit_path("system")
        assert result.name == "gatekeeper.service"
        assert "/etc/systemd/system" in str(result)


class TestServiceTemplates:
    """Tests for service unit templates."""

    def test_user_template_has_required_fields(self):
        """User template must contain core systemd directives."""
        unit = SERVICE_USER_TEMPLATE.format(
            work_dir="/tmp/gk",
            exec_path="/usr/bin/gatekeeper",
        )
        assert "[Unit]" in unit
        assert "[Service]" in unit
        assert "[Install]" in unit
        assert "ExecStart=/usr/bin/gatekeeper serve" in unit
        assert "WorkingDirectory=/tmp/gk" in unit
        assert "Restart=on-failure" in unit
        assert "WantedBy=default.target" in unit

    def test_system_template_has_required_fields(self):
        """System template must contain User, Group, EnvironmentFile, and multi-user target."""
        unit = SERVICE_SYSTEM_TEMPLATE.format(
            user="brimdor",
            group="brimdor",
            work_dir="/home/brimdor/gatekeeper",
            exec_path="/home/brimdor/.local/bin/gatekeeper",
            env_file="/home/brimdor/gatekeeper/.env",
        )
        assert "[Unit]" in unit
        assert "[Service]" in unit
        assert "[Install]" in unit
        assert "ExecStart=/home/brimdor/.local/bin/gatekeeper serve" in unit
        assert "WorkingDirectory=/home/brimdor/gatekeeper" in unit
        assert "User=brimdor" in unit
        assert "Group=brimdor" in unit
        assert "EnvironmentFile=-/home/brimdor/gatekeeper/.env" in unit
        assert "WantedBy=multi-user.target" in unit
        # Should NOT have user-session target
        assert "default.target" not in unit


# ---------------------------------------------------------------------------
# Install tests
# ---------------------------------------------------------------------------


class TestInstallService:
    """Tests for install_service()."""

    def test_install_no_gatekeeper_binary(self, tmp_path):
        """Should fail if gatekeeper binary is not on PATH."""
        with (
            patch("gatekeeper.service._is_systemd_available", return_value=True),
            patch("gatekeeper.service._resolve_exec_path", return_value=None),
        ):
            result = install_service(skip_prompt=True)
            assert result is False

    def test_install_no_systemd(self, tmp_path):
        """Should fail gracefully when systemd is not available."""
        with (
            patch("gatekeeper.service._is_systemd_available", return_value=False),
        ):
            result = install_service(skip_prompt=True)
            assert result is False

    def test_install_user_creates_unit_file(self, tmp_path):
        """Should write a user unit file and run systemctl --user commands."""
        sysd_dir = tmp_path / "sysd"
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("gatekeeper.service._is_systemd_available", return_value=True),
            patch("gatekeeper.service._resolve_exec_path", return_value="/usr/bin/gatekeeper"),
            patch("gatekeeper.service._resolve_work_dir", return_value="/home/user/gatekeeper"),
            patch("gatekeeper.service.SYSTEMD_USER_DIR", sysd_dir),
            patch("gatekeeper.service._systemctl", return_value=mock_result) as mock_ctl,
        ):
            result = install_service(skip_prompt=True, scope="user")
            assert result is True

            # Check unit file was written
            unit_path = sysd_dir / SERVICE_UNIT
            assert unit_path.exists()

            # Verify content
            content = unit_path.read_text()
            assert "ExecStart=/usr/bin/gatekeeper serve" in content
            assert "WorkingDirectory=/home/user/gatekeeper" in content
            assert "WantedBy=default.target" in content

            # Verify systemctl was called correctly
            assert mock_ctl.call_count == 3  # daemon-reload, enable, start

    def test_install_system_creates_unit_file(self, tmp_path):
        """Should write a system unit file via sudo tee and run systemctl commands."""
        sysd_dir = tmp_path / "systemd"
        sysd_dir.mkdir(parents=True)
        unit_path = sysd_dir / SERVICE_UNIT
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("gatekeeper.service._is_systemd_available", return_value=True),
            patch("gatekeeper.service._resolve_exec_path", return_value="/usr/bin/gatekeeper"),
            patch("gatekeeper.service._resolve_work_dir", return_value="/home/user/gatekeeper"),
            patch("gatekeeper.service._unit_path", return_value=unit_path),
            patch("gatekeeper.service._systemctl", return_value=mock_result) as mock_ctl,
            patch("gatekeeper.service.subprocess.run", return_value=mock_result) as mock_run,
        ):
            result = install_service(skip_prompt=True, scope="system")
            assert result is True

            # Verify subprocess.run was called for tee (writing the unit file)
            tee_calls = [c for c in mock_run.call_args_list if "tee" in str(c)]
            assert len(tee_calls) == 1

            # Verify systemctl was called with scope="system"
            for call in mock_ctl.call_args_list:
                assert call.kwargs.get("scope") == "system"

    def test_install_invalid_scope(self):
        """Should reject invalid scope values."""
        result = install_service(skip_prompt=True, scope="invalid")
        assert result is False

    def test_install_system_migrates_from_user(self, tmp_path):
        """When installing as system, should remove existing user service."""
        user_dir = tmp_path / "user_sysd"
        user_dir.mkdir(parents=True)
        user_unit = user_dir / SERVICE_UNIT
        user_unit.write_text("[Service]\nExecStart=gatekeeper serve\n")

        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("gatekeeper.service._is_systemd_available", return_value=True),
            patch("gatekeeper.service._resolve_exec_path", return_value="/usr/bin/gatekeeper"),
            patch("gatekeeper.service._resolve_work_dir", return_value="/home/user/gatekeeper"),
            patch(
                "gatekeeper.service._unit_exists",
                side_effect=lambda scope="system": (
                    scope == "user"  # user service exists, system doesn't yet
                ),
            ),
            patch(
                "gatekeeper.service._unit_path",
                side_effect=lambda scope="system": (
                    Path("/etc/systemd/system/gatekeeper.service")
                    if scope == "system"
                    else user_unit
                ),
            ),
            patch("gatekeeper.service.SYSTEMD_USER_DIR", user_dir),
            patch("gatekeeper.service._systemctl", return_value=mock_result),
            patch("gatekeeper.service.subprocess.run", return_value=mock_result),
        ):
            result = install_service(skip_prompt=True, scope="system")
            assert result is True

            # User service should have been removed
            assert not user_unit.exists()


class TestUninstallService:
    """Tests for uninstall_service()."""

    def test_uninstall_no_unit_user(self, tmp_path):
        """Should report not installed when user unit file doesn't exist."""
        with (
            patch("gatekeeper.service.SYSTEMD_USER_DIR", tmp_path / "sysd"),
        ):
            result = uninstall_service(scope="user")
            assert result is True

    def test_uninstall_removes_user_unit_file(self, tmp_path):
        """Should stop, disable, and remove the user unit file."""
        sysd_dir = tmp_path / "sysd"
        sysd_dir.mkdir(parents=True)
        unit_path = sysd_dir / SERVICE_UNIT
        unit_path.write_text("[Service]\nExecStart=gatekeeper serve\n")
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("gatekeeper.service.SYSTEMD_USER_DIR", sysd_dir),
            patch("gatekeeper.service._unit_path", return_value=unit_path),
            patch("gatekeeper.service._systemctl", return_value=mock_result),
        ):
            result = uninstall_service(scope="user")
            assert result is True
            assert not unit_path.exists()

    def test_uninstall_system_scope(self, tmp_path):
        """Should remove system unit file via sudo rm."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("gatekeeper.service._unit_exists", return_value=True),
            patch("gatekeeper.service._run", return_value=mock_result),
            patch("gatekeeper.service._systemctl", return_value=mock_result),
        ):
            result = uninstall_service(scope="system")
            assert result is True

    def test_uninstall_system_rm_failure(self, tmp_path):
        """Should return False and print error when sudo rm fails."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("gatekeeper.service._unit_exists", return_value=True),
            patch("gatekeeper.service._systemctl", return_value=mock_result),
        ):
            with patch(
                "gatekeeper.service._unit_path",
                return_value=Path("/etc/systemd/system/gatekeeper.service"),
            ):
                with patch(
                    "gatekeeper.service._run",
                    side_effect=subprocess.CalledProcessError(
                        1, "sudo rm", stderr="Permission denied"
                    ),
                ):
                    result = uninstall_service(scope="system")
                    assert result is False


# ---------------------------------------------------------------------------
# Enable / disable tests
# ---------------------------------------------------------------------------


class TestEnableDisable:
    """Tests for enable_service() and disable_service()."""

    def test_enable_no_unit(self, tmp_path):
        """Should fail if unit file doesn't exist."""
        with patch("gatekeeper.service._unit_path", return_value=tmp_path / "nonexistent.service"):
            result = enable_service()
            assert result is False

    def test_enable_starts_service(self, tmp_path):
        """Should enable and start the service."""
        unit_path = tmp_path / SERVICE_UNIT
        unit_path.write_text("[Service]\nExecStart=gatekeeper serve\n")
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("gatekeeper.service._unit_path", return_value=unit_path),
            patch("gatekeeper.service._systemctl", return_value=mock_result) as mock_ctl,
        ):
            result = enable_service()
            assert result is True
            # enable and start
            assert mock_ctl.call_count == 2

    def test_enable_with_system_scope(self, tmp_path):
        """Should pass scope='system' to systemctl calls."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("gatekeeper.service._run", return_value=MagicMock(returncode=0)),
            patch("gatekeeper.service._systemctl", return_value=mock_result) as mock_ctl,
        ):
            result = disable_service(scope="system")
            assert result is True
            # Verify scope was passed
            for call in mock_ctl.call_args_list:
                assert call.kwargs.get("scope") == "system"

    def test_disable_stops_service(self, tmp_path):
        """Should stop and disable the service."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")

        with patch("gatekeeper.service._systemctl", return_value=mock_result) as mock_ctl:
            result = disable_service()
            assert result is True
            # stop and disable
            assert mock_ctl.call_count == 2

    def test_restart_service(self, tmp_path):
        """Should restart the service via systemctl."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        unit_path = tmp_path / "gatekeeper.service"
        unit_path.write_text("[Unit]\nDescription=test\n")

        with (
            patch("gatekeeper.service._unit_path", return_value=unit_path),
            patch("gatekeeper.service._systemctl", return_value=mock_result) as mock_ctl,
        ):
            result = restart_service()
            assert result is True
            mock_ctl.assert_called_once_with("restart", "gatekeeper", scope="user")

    def test_restart_service_not_installed(self, tmp_path):
        """Should fail if service unit is not installed."""
        unit_path = tmp_path / "gatekeeper.service"

        with patch("gatekeeper.service._unit_path", return_value=unit_path):
            result = restart_service()
            assert result is False

    def test_restart_with_system_scope(self, tmp_path):
        """Should restart system service via sudo systemctl."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        unit_path = tmp_path / "gatekeeper.service"
        unit_path.write_text("[Unit]\nDescription=test\n")

        with (
            patch("gatekeeper.service._unit_path", return_value=unit_path),
            patch("gatekeeper.service._run", return_value=mock_result),
            patch("gatekeeper.service._systemctl", return_value=mock_result) as mock_ctl,
        ):
            result = restart_service(scope="system")
            assert result is True
            mock_ctl.assert_called_once_with("restart", "gatekeeper", scope="system")


# ---------------------------------------------------------------------------
# Resolve path tests
# ---------------------------------------------------------------------------


class TestResolvePaths:
    """Tests for _resolve_exec_path and _resolve_work_dir."""

    def test_resolve_exec_path_found(self):
        """Should find gatekeeper on PATH."""
        with patch("shutil.which", return_value="/usr/bin/gatekeeper"):
            assert _resolve_exec_path() == "/usr/bin/gatekeeper"

    def test_resolve_exec_path_not_found(self):
        """Should return None when gatekeeper is not on PATH."""
        with patch("shutil.which", return_value=None):
            assert _resolve_exec_path() is None

    def test_resolve_work_dir_with_env(self, tmp_path):
        """Should detect .env in the current directory."""
        (tmp_path / ".env").write_text("TEST=1\n")
        with patch.object(Path, "cwd", return_value=tmp_path):
            result = _resolve_work_dir()
            assert result == str(tmp_path)


class TestSystemdAvailability:
    """Tests for _is_systemd_available()."""

    def test_systemd_available_when_running(self):
        """Should return True when systemd user session is running."""
        mock_result = MagicMock(returncode=0, stdout="running", stderr="")
        with patch("gatekeeper.service._run", return_value=mock_result):
            assert _is_systemd_available("user") is True

    def test_systemd_unavailable_when_missing(self):
        """Should return False when systemctl is not found."""
        with patch("gatekeeper.service._run", side_effect=OSError("systemctl not found")):
            assert _is_systemd_available("user") is False

    def test_system_scope_available_on_linux(self):
        """Should return True when systemd is running at system level."""
        mock_result = MagicMock(returncode=0, stdout="running", stderr="")
        with patch("gatekeeper.service._run", return_value=mock_result):
            assert _is_systemd_available("system") is True


class TestUnitExists:
    """Tests for _unit_exists()."""

    def test_unit_exists_user_scope(self, tmp_path):
        """Should check Path.exists() for user scope."""
        unit_path = tmp_path / "gatekeeper.service"
        unit_path.write_text("[Unit]\n")
        with patch("gatekeeper.service._unit_path", return_value=unit_path):
            assert _unit_exists("user") is True

    def test_unit_not_exists_user_scope(self, tmp_path):
        """Should return False when user unit file doesn't exist."""
        unit_path = tmp_path / "nonexistent.service"
        with patch("gatekeeper.service._unit_path", return_value=unit_path):
            assert _unit_exists("user") is False

    def test_unit_exists_system_scope(self):
        """Should use sudo test -f for system scope."""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with (
            patch(
                "gatekeeper.service._unit_path",
                return_value=Path("/etc/systemd/system/gatekeeper.service"),
            ),
            patch("gatekeeper.service._run", return_value=mock_result),
        ):
            assert _unit_exists("system") is True

    def test_unit_not_exists_system_scope(self):
        """Should return False when sudo test -f fails for system scope."""
        mock_result = MagicMock(returncode=1, stdout="", stderr="")
        with (
            patch(
                "gatekeeper.service._unit_path",
                return_value=Path("/etc/systemd/system/gatekeeper.service"),
            ),
            patch("gatekeeper.service._run", return_value=mock_result),
        ):
            assert _unit_exists("system") is False


class TestDetectScope:
    """Tests for _detect_scope()."""

    def test_detect_system_when_no_user_session(self):
        """Should return 'system' when system systemd available but user not."""
        with (
            patch(
                "gatekeeper.service._is_systemd_available",
                side_effect=lambda scope: scope == "system",
            ),
        ):
            from gatekeeper.service import _detect_scope

            assert _detect_scope() == "system"

    def test_detect_user_when_both_available(self):
        """Should return 'user' when both scopes available."""
        with (
            patch("gatekeeper.service._is_systemd_available", return_value=True),
        ):
            from gatekeeper.service import _detect_scope

            assert _detect_scope() == "user"

    def test_detect_user_when_only_user_available(self):
        """Should return 'user' when only user scope available."""
        with (
            patch(
                "gatekeeper.service._is_systemd_available",
                side_effect=lambda scope: scope == "user",
            ),
        ):
            from gatekeeper.service import _detect_scope

            assert _detect_scope() == "user"
