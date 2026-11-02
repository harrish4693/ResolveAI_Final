"""
Standalone Verification Script: Real Process Restart & Persistence Test

Tests:
1. Spawns Uvicorn backend process 1.
2. Sets autonomy mode to 'conservative' (non-default) via PUT /api/admin/autonomy.
3. Sets incident INC-RESTART-REAL-001 status to 'investigating' via POST /api/analytics/incidents/{id}/status.
4. Kills process 1 completely (terminates PID, verifies exit).
5. Spawns Uvicorn backend process 2 (new PID, fresh memory).
6. Queries GET /api/admin/autonomy -> asserts mode is STILL 'conservative'.
7. Queries GET /api/analytics/incidents -> asserts incident INC-RESTART-REAL-001 is STILL 'investigating'.
8. Cleanly terminates process 2.
"""

import os
import sys
import time
import subprocess
import httpx
import asyncio

# Ensure backend root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app.main  # Initializes all SQLAlchemy mappers
from app.database import async_session_factory
from app.users.models import User
from app.shared.models import UserRole
from app.auth.password import get_password_hash
from app.auth.jwt import create_access_token
from sqlalchemy import select


async def get_or_create_admin_token() -> str:
    """Ensure an admin user exists and return an access token."""
    async with async_session_factory() as session:
        stmt = select(User).where(User.email == "admin_restart_test@resolveai.com")
        admin = (await session.execute(stmt)).scalar_one_or_none()
        if not admin:
            admin = User(
                email="admin_restart_test@resolveai.com",
                full_name="Admin Restart Test",
                password_hash=get_password_hash("AdminPass123!"),
                role=UserRole.ADMIN,
                tenant_id="default",
            )
            session.add(admin)
            await session.commit()
            await session.refresh(admin)
        return create_access_token(admin.id, "admin")


def wait_for_server(url: str, timeout: float = 30.0) -> bool:
    """Poll URL until server responds 200."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(f"{url}/health/live", timeout=2.0)
            if r.status_code == 200:
                return True
        except Exception:
            time.sleep(0.5)
    return False


def start_uvicorn(port: int = 8000) -> subprocess.Popen:
    """Start uvicorn in a subprocess."""
    python_exe = sys.executable
    cmd = [
        python_exe,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    proc = subprocess.Popen(
        cmd,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def stop_uvicorn(proc: subprocess.Popen):
    """Terminate uvicorn process and ensure it has exited."""
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


async def main():
    base_url = "http://127.0.0.1:8000"
    print("\n--- STEP 1: Setting up Admin token ---")
    token = await get_or_create_admin_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print("Admin token generated.")

    print("\n--- STEP 2: Spawning Process 1 (Uvicorn) ---")
    proc1 = start_uvicorn(8000)
    print(f"Process 1 started with PID: {proc1.pid}")

    try:
        ready = wait_for_server(base_url, timeout=25.0)
        assert ready, "Process 1 failed to become ready on port 8000"
        print("Process 1 is alive and responding on http://127.0.0.1:8000/health/live")

        print("\n--- STEP 3: Saving non-default autonomy mode (conservative) ---")
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            put_res = await client.put(
                "/api/admin/autonomy",
                headers=headers,
                json={"mode": "conservative"},
            )
            assert put_res.status_code == 200, f"Failed PUT /api/admin/autonomy: {put_res.text}"
            data = put_res.json()
            assert data["mode"] == "conservative", f"Expected conservative, got {data['mode']}"
            print(f"Autonomy mode successfully updated to: {data['mode']}")

            print("\n--- STEP 4: Updating incident status to 'investigating' ---")
            incident_id = "INC-RESTART-REAL-001"
            inc_res = await client.post(
                f"/api/analytics/incidents/{incident_id}/status",
                headers=headers,
                json={"status": "investigating"},
            )
            assert inc_res.status_code == 200, f"Failed to update incident: {inc_res.text}"
            inc_data = inc_res.json()
            assert inc_data["status"] == "investigating"
            print(f"Incident {incident_id} successfully updated to: {inc_data['status']}")

    finally:
        print("\n--- STEP 5: Completely stopping Process 1 ---")
        stop_uvicorn(proc1)
        print(f"Process 1 (PID {proc1.pid}) stopped completely.")

    # Small delay to ensure port is released
    time.sleep(2.0)

    print("\n--- STEP 6: Spawning Process 2 (Fresh Uvicorn, New PID) ---")
    proc2 = start_uvicorn(8000)
    print(f"Process 2 started with NEW PID: {proc2.pid}")

    try:
        ready = wait_for_server(base_url, timeout=25.0)
        assert ready, "Process 2 failed to become ready on port 8000"
        print("Process 2 is alive and responding on http://127.0.0.1:8000/health/live")

        print("\n--- STEP 7: Verifying Autonomy Mode survived restart ---")
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            get_auto = await client.get("/api/admin/autonomy", headers=headers)
            assert get_auto.status_code == 200, f"Failed GET /api/admin/autonomy: {get_auto.text}"
            auto_data = get_auto.json()
            print(f"Recovered autonomy mode: {auto_data['mode']}")
            assert auto_data["mode"] == "conservative", (
                f"PERSISTENCE FAILURE: Expected 'conservative' after restart, got '{auto_data['mode']}'"
            )

            print("\n--- STEP 8: Verifying Incident Lifecycle Status survived restart ---")
            get_inc = await client.get("/api/analytics/incidents", headers=headers)
            assert get_inc.status_code == 200, f"Failed GET /api/analytics/incidents: {get_inc.text}"
            incidents_payload = get_inc.json()
            all_incidents = incidents_payload.get("candidates", []) + incidents_payload.get("confirmed", [])
            target = next((item for item in all_incidents if item["incident_id"] == "INC-RESTART-REAL-001"), None)
            assert target is not None, (
                f"PERSISTENCE FAILURE: Incident INC-RESTART-REAL-001 missing after restart! Got: {[i['incident_id'] for i in all_incidents]}"
            )
            print(f"Recovered incident: {target['incident_id']} with status '{target['status']}'")
            assert target["status"] == "investigating", (
                f"PERSISTENCE FAILURE: Expected status 'investigating', got '{target['status']}'"
            )

        print("\n=======================================================")
        print("REAL PROCESS RESTART PERSISTENCE VERIFICATION: PASSED!")
        print("=======================================================")

    finally:
        print("\n--- STEP 9: Cleaning up Process 2 ---")
        stop_uvicorn(proc2)
        print("Process 2 terminated.")


if __name__ == "__main__":
    asyncio.run(main())
