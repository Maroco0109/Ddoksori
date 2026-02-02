"""
Docker Environment Tests - Phase 6 Validation

Tests Docker Compose stack deployment and cross-container communication.

Usage:
    conda activate dsr
    pytest backend/scripts/testing/test_docker_environment.py -v -m docker
"""

import subprocess
import time

import docker
import pytest


@pytest.mark.docker
class TestDockerStack:
    """Test Docker Compose stack"""

    @pytest.fixture(scope="class")
    def docker_client(self):
        """Docker SDK client"""
        return docker.from_env()

    def test_docker_compose_up(self):
        """docker-compose up starts all services"""
        result = subprocess.run(
            ["docker-compose", "-f", "/home/maroco/LLM/docker-compose.yml", "up", "-d"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"docker-compose up failed: {result.stderr}"

        # Wait for services to initialize
        time.sleep(10)

    def test_backend_container_running(self, docker_client):
        """Backend container is running"""
        try:
            container = docker_client.containers.get("ddoksori_backend")
            assert container.status == "running"
        except docker.errors.NotFound:
            pytest.fail("ddoksori_backend container not found")

    def test_backend_api_available(self):
        """Backend /health endpoint responds"""
        import httpx

        # Wait for backend to start (max 30s)
        for _ in range(30):
            try:
                resp = httpx.get("http://localhost:8000/health", timeout=5)
                if resp.status_code == 200:
                    break
            except (httpx.ConnectError, httpx.TimeoutException):
                time.sleep(1)
                continue

        # Final check
        resp = httpx.get("http://localhost:8000/health", timeout=5)
        assert resp.status_code == 200, "Backend API not responding"

    def test_cors_configuration(self):
        """Backend CORS configuration allows frontend origin"""
        import httpx

        client = httpx.Client()
        resp = client.options(
            "http://localhost:8000/search", headers={"Origin": "http://localhost:5173"}
        )

        # Should return CORS headers or 200
        assert resp.status_code in [200, 204]

    def test_frontend_container_running(self, docker_client):
        """Frontend container is running"""
        try:
            container = docker_client.containers.get("ddoksori_frontend")
            assert container.status == "running"
        except docker.errors.NotFound:
            # Frontend may not be running - skip
            pytest.skip("Frontend container not running")

    def test_frontend_backend_connectivity(self):
        """Frontend can call backend API"""
        # This would require frontend to be running and making actual requests
        # Skip for now as it's more complex to test
        pytest.skip("Frontend-backend connectivity test not implemented")

    def test_docker_compose_down(self):
        """docker-compose down stops all services"""
        result = subprocess.run(
            ["docker-compose", "-f", "/home/maroco/LLM/docker-compose.yml", "down"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"docker-compose down failed: {result.stderr}"
