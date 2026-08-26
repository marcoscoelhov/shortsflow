from fastapi.testclient import TestClient

from app.main import app


def test_remote_submission_is_idempotent() -> None:
    client = TestClient(app)
    headers = {
        "tailscale-user-login": "operator@example.com",
        "idempotency-key": "test-remote-submission-idempotent",
    }
    payload = {"seed_theme": "Por que o gelo estala?", "niche_id": "curiosidades", "target_duration_sec": "45"}

    first = client.post("/jobs", data=payload, headers=headers, follow_redirects=False)
    second = client.post("/jobs", data=payload, headers=headers, follow_redirects=False)

    assert first.status_code == 303
    assert second.status_code == 303
    assert first.headers["location"] == second.headers["location"]
