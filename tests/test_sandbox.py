"""
@file test_sandbox.py
@description Unit tests for sandbox configuration and manager operations
@module tests/test_sandbox
"""

from unittest.mock import MagicMock

import pytest

from sqldoctor.config import SandboxConfig
from sqldoctor.sandbox.manager import SandboxManager, SandboxManagerError


def test_sandbox_config_defaults() -> None:
    """Test SandboxConfig default parameters and URI formatting."""
    config = SandboxConfig()
    assert config.pg_version == 17
    assert config.port == 54329
    assert config.statement_timeout_ms == 10000

    manager = SandboxManager(config)
    assert manager.connection_uri == "postgresql://postgres:postgres@localhost:54329/postgres"


def test_sandbox_manager_lifecycle_mocked(mocker: MagicMock) -> None:
    """Test start and stop container lifecycle methods with mocked Docker client."""
    mock_docker_client = MagicMock()
    mock_container = MagicMock()
    mock_container.status = "running"

    mock_docker_client.containers.get.return_value = mock_container
    mock_docker_client.containers.run.return_value = mock_container

    config = SandboxConfig()
    manager = SandboxManager(config)
    manager._client = mock_docker_client

    # Test is_running
    assert manager.is_running() is True

    # Test stop
    manager.stop()
    mock_container.stop.assert_called_once_with(timeout=5)
    mock_container.remove.assert_called_once_with(force=True)

    # Test start without wait
    manager.start(wait=False)
    mock_docker_client.containers.run.assert_called_once()


def test_sandbox_manager_error_when_docker_unreachable(mocker: MagicMock) -> None:
    """Test clear error handling when Docker daemon is not running."""
    import docker.errors

    mocker.patch(
        "docker.from_env",
        side_effect=docker.errors.DockerException("Daemon connection refused"),
    )

    manager = SandboxManager(SandboxConfig())
    with pytest.raises(SandboxManagerError, match="Failed to connect to Docker daemon"):
        _ = manager.client
