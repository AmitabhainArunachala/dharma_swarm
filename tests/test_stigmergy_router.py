from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers import stigmergy as stigmergy_router


def _stigmergy_client() -> TestClient:
    app = FastAPI()
    app.include_router(stigmergy_router.router)
    return TestClient(app)


def test_promote_mark_raises_salience_and_records_operator_action(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marks_path = tmp_path / "marks.jsonl"
    marks_path.write_text(
        json.dumps(
            {
                "id": "mark-1",
                "agent": "glm5-researcher",
                "file_path": "docs/CLAUDE.md",
                "action": "write",
                "observation": "Important runtime finding",
                "salience": 0.61,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(stigmergy_router, "MARKS_PATH", marks_path)

    client = _stigmergy_client()
    resp = client.post(
        "/api/stigmergy/marks/mark-1/promote",
        json={"salience": 0.95, "promoted_by": "dashboard_test"},
    )

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["id"] == "mark-1"
    assert body["salience"] == 0.95
    assert body["promoted_by"] == "dashboard_test"

    persisted = json.loads(marks_path.read_text(encoding="utf-8").strip())
    assert persisted["salience"] == 0.95
    assert persisted["operator_actions"][-1]["action"] == "promote"
    assert persisted["operator_actions"][-1]["promoted_by"] == "dashboard_test"


def test_list_marks_filters_by_agent_alias(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marks_path = tmp_path / "marks.jsonl"
    marks_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "mark-1",
                        "agent": "glm-researcher",
                        "file_path": "docs/GLM.md",
                        "action": "synthesize",
                        "observation": "GLM synthesis insight",
                        "salience": 0.91,
                    }
                ),
                json.dumps(
                    {
                        "id": "mark-2",
                        "agent": "other-agent",
                        "file_path": "docs/OTHER.md",
                        "action": "write",
                        "observation": "Other note",
                        "salience": 0.22,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(stigmergy_router, "MARKS_PATH", marks_path)

    client = _stigmergy_client()
    resp = client.get("/api/stigmergy/marks?agent=glm5-researcher&limit=10")

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert [item["id"] for item in body] == ["mark-1"]
    assert body[0]["agent"] == "glm-researcher"
