"""
@file manager.py
@description Lifecycle manager for the PostgreSQL sandbox container
@module sqldoctor/sandbox/manager
"""

import time
from pathlib import Path
from typing import Any

import psycopg
from docker.errors import DockerException, NotFound

import docker
from sqldoctor.config import SandboxConfig


class SandboxManagerError(Exception):
    """Raised when container lifecycle operations fail."""


class SandboxManager:
    """Controls creation, lifecycle, and readiness polling for sandbox container."""

    CONTAINER_NAME = "sqldoctor-sandbox"

    def __init__(self, config: SandboxConfig) -> None:
        """Initialize SandboxManager with configuration.

        Args:
            config: SandboxConfig instance with image, port, and credentials.
        """
        self.config = config
        self._client: Any = None

    @property
    def client(self) -> Any:
        """Lazy-loaded Docker client."""
        if self._client is None:
            try:
                self._client = docker.from_env()  # type: ignore[attr-defined]
            except DockerException as exc:
                raise SandboxManagerError(
                    f"Failed to connect to Docker daemon: {exc}. Is Docker running?"
                ) from exc
        return self._client

    @property
    def connection_uri(self) -> str:
        """Formatted PostgreSQL connection URI for local sandbox."""
        return (
            f"postgresql://{self.config.user}:{self.config.password}"
            f"@localhost:{self.config.port}/{self.config.database}"
        )

    def is_running(self) -> bool:
        """Check if sandbox container is currently running."""
        try:
            container = self.client.containers.get(self.CONTAINER_NAME)
            return bool(container.status == "running")
        except (NotFound, DockerException):
            return False

    def build_image(self, dockerfile_dir: Path | str = "docker") -> None:
        """Build the custom PostgreSQL sandbox image with HypoPG.

        Args:
            dockerfile_dir: Directory containing Dockerfile.
        """
        path = Path(dockerfile_dir).resolve()
        if not path.exists():
            raise SandboxManagerError(f"Dockerfile directory not found: {path}")

        try:
            self.client.images.build(
                path=str(path),
                tag=self.config.image,
                rm=True,
            )
        except DockerException as exc:
            raise SandboxManagerError(
                f"Failed to build sandbox image {self.config.image}: {exc}"
            ) from exc

    def start(self, wait: bool = True, timeout_sec: int = 45) -> None:
        """Start or restart the sandbox container and wait for readiness.

        Args:
            wait: Whether to poll and block until PostgreSQL is accepting queries.
            timeout_sec: Maximum seconds to await readiness.
        """
        # Ensure any stale container with the same name is removed
        self.stop()

        # Check if base image exists; build if missing
        try:
            self.client.images.get(self.config.image)
        except NotFound:
            self.build_image()

        try:
            self.client.containers.run(
                self.config.image,
                name=self.CONTAINER_NAME,
                detach=True,
                ports={"5432/tcp": self.config.port},
                environment={
                    "POSTGRES_USER": self.config.user,
                    "POSTGRES_PASSWORD": self.config.password,
                    "POSTGRES_DB": self.config.database,
                },
                restart_policy={"Name": "no"},
            )
        except DockerException as exc:
            raise SandboxManagerError(f"Failed to run sandbox container: {exc}") from exc

        if wait:
            self.wait_until_ready(timeout_sec=timeout_sec)

    def wait_until_ready(self, timeout_sec: int = 45) -> None:
        """Poll the container until PostgreSQL accepts queries and HypoPG is loaded.

        Args:
            timeout_sec: Timeout in seconds before giving up.
        """
        start_time = time.monotonic()
        last_error = ""

        while time.monotonic() - start_time < timeout_sec:
            try:
                with psycopg.connect(self.connection_uri, connect_timeout=2) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1;")
                        # Verify hypopg extension availability
                        cur.execute("CREATE EXTENSION IF NOT EXISTS hypopg;")
                        conn.commit()
                        return
            except Exception as exc:
                last_error = str(exc)
                time.sleep(1.0)

        raise SandboxManagerError(
            f"Sandbox failed to become ready within {timeout_sec}s. Last error: {last_error}"
        )

    def stop(self) -> None:
        """Stop and remove sandbox container if it exists."""
        try:
            container = self.client.containers.get(self.CONTAINER_NAME)
            container.stop(timeout=5)
            container.remove(force=True)
        except NotFound:
            pass
        except DockerException as exc:
            raise SandboxManagerError(
                f"Failed to stop container {self.CONTAINER_NAME}: {exc}"
            ) from exc
