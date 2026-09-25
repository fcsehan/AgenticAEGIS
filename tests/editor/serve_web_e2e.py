"""Disposable real editor server for browser tests; no user projects are opened."""

import json
import shutil
import tempfile
from pathlib import Path

import uvicorn
from fastapi import Request

from aegis.editor.app import create_editor_app


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aegis-browser-e2e-") as directory:
        root = Path(directory).resolve()
        workspace = root / "projects"
        workspace.mkdir()
        shutil.copytree(
            Path(__file__).parents[2] / "aegis/domains/pharma", workspace / "sample/pharma"
        )
        app = create_editor_app(workspace, root / "config")
        original_routes = len(app.router.routes)

        @app.get("/_fixture/workspace")
        def fixture_workspace() -> dict[str, str]:
            return {"path": str(workspace / "workshop"), "sample": str(workspace / "sample")}

        @app.post("/_fixture/reload")
        def fixture_reload(request: Request) -> dict[str, bool]:
            # A fresh application state reloads all disk data. Process restart is
            # additionally covered by the documented CLI/browser acceptance run.
            fresh = create_editor_app(workspace, root / "config")
            request.app.state.editor_state = fresh.state.editor_state
            return {"reloaded": True}

        @app.get("/_fixture/v1/models")
        def models() -> dict:
            return {"data": [{"id": "fixture-model"}]}

        @app.post("/_fixture/v1/chat/completions")
        async def completion(request: Request) -> dict:
            body = await request.json()
            tool = body["tools"][0]["function"]["name"]
            if tool == "report_capability":
                arguments = [{"supported": True}]
            elif tool == "propose_rule":
                arguments = [
                    {
                        "modality": "PERMITTED",
                        "agent_role": "pharmacistAgent",
                        "code_of_conduct": "PharmaCompliance",
                        "action_type": "reportAdverseEvent",
                        "proposition_parameters": {"severity": "majorInteraction"},
                        "defeasible": True,
                        "reasoning": "Deterministic browser fixture",
                        "natural_language_summary": (
                            "Fixture permission for adverse event reporting"
                        ),
                    }
                ]
            elif tool == "extract_normative_statement":
                arguments = [
                    {
                        "source_ref": "Fixture paragraph 1",
                        "modality": "PERMITTED",
                        "subject": "employee",
                        "action": "report incidents",
                        "confidence": 1.0,
                    },
                    {
                        "source_ref": "Fixture paragraph 1",
                        "modality": "FORBIDDEN",
                        "subject": "employee",
                        "action": "delete records",
                        "confidence": 1.0,
                    },
                ]
            elif tool == "define_ontology":
                arguments = [
                    {
                        "roles": [{"natural_name": "employee", "meld_symbol": "employee"}],
                        "actions": [
                            {"natural_name": "report incidents", "meld_symbol": "reportIncidents"},
                            {"natural_name": "delete records", "meld_symbol": "deleteRecords"},
                        ],
                        "codes": ["FixturePolicy"],
                    }
                ]
            else:
                raise ValueError(f"Unsupported fixture tool: {tool}")
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": f"fixture-{index}",
                                    "type": "function",
                                    "function": {"name": tool, "arguments": json.dumps(argument)},
                                }
                                for index, argument in enumerate(arguments)
                            ],
                        }
                    }
                ]
            }

        app.router.routes = (
            app.router.routes[original_routes:] + app.router.routes[:original_routes]
        )
        uvicorn.run(app, host="127.0.0.1", port=18101, log_level="warning", proxy_headers=False)


if __name__ == "__main__":
    main()
