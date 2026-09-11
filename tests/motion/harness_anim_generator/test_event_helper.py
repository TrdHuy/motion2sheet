from pathlib import Path

from motion2sheet.motion.harness_anim_generator.events import EventClient, _notification


class Response:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_event_helper_adds_identity_sequence_and_retries_same_envelope(tmp_path, monkeypatch):
    bodies = []

    def urlopen(request, timeout):
        bodies.append(request.data)
        if len(bodies) < 3:
            raise ConnectionRefusedError("not ready")
        return Response()

    monkeypatch.setattr(
        "motion2sheet.motion.harness_anim_generator.events.urllib.request.urlopen", urlopen
    )
    client = EventClient(
        run_id="run",
        event_url="http://127.0.0.1/events",
        token="token",
        state_path=tmp_path / "sequence",
        attempts=3,
        backoff_seconds=0,
    )
    first = client.send("agent.heartbeat")
    second = client.send("agent.log", payload={"message": "hello"})
    assert first["eventId"]
    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert bodies[0] == bodies[1] == bodies[2]


def test_notify_helper_maps_semantic_cli_to_generic_event(monkeypatch, tmp_path):
    observed = {}

    class FakeClient:
        def __init__(self, **kwargs):
            observed["init"] = kwargs

        def send(self, event_type, **kwargs):
            observed["send"] = (event_type, kwargs)

    monkeypatch.setattr(
        "motion2sheet.motion.harness_anim_generator.events.EventClient", FakeClient
    )
    monkeypatch.setenv("HARNESS_RUN_ID", "run")
    monkeypatch.setenv("HARNESS_EVENT_URL", "http://127.0.0.1/events")
    monkeypatch.setenv("HARNESS_TOKEN", "token")
    monkeypatch.setenv("HARNESS_EVENT_STATE", str(tmp_path / "sequence"))
    assert _notification(
        ["skill-complete", "discover-references", "--iteration", "2", "--summary", "done"]
    ) == 0
    assert observed["init"]["token"] == "token"
    assert observed["send"] == (
        "skill.step.completed",
        {"payload": {"step": "discover-references", "summary": "done"}, "iteration": 2},
    )
