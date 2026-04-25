"""
Usability validation for flask-restful (Scenario C: Web framework / decorator).

HARD CONSTRAINTS:
- Real HTTP server via werkzeug.serving.make_server (NOT app.test_client()).
- Real HTTP client via `requests` over a real socket on 127.0.0.1.
- Three distinct flask_restful submodules exercised (Api, Resource, reqparse).
- Stresses Werkzeug 3.x HTTPException-from-getattr surface (the exact 3.13 bug
  kimi rescue patched in flask_restful/reqparse.py).
- Real assertions on response status + body content.
"""
import sys
import threading
import time

import requests
from flask import Flask
from werkzeug.serving import make_server

# Path 1: top-level Api / Resource (flask_restful.__init__)
from flask_restful import Api, Resource
# Path 2: reqparse (the actual file kimi patched)
from flask_restful.reqparse import RequestParser
# Path 3: inputs (separate submodule - argument coercion)
from flask_restful import inputs


TODOS = {
    "1": {"task": "buy milk", "done": False},
    "2": {"task": "ship paper", "done": True},
}


class TodoList(Resource):
    """Hits reqparse.parse_args -> Argument.source -> getattr(request, 'json').

    On Werkzeug 3.x the request body parser raises a BadRequest (HTTPException
    subclass) when JSON is missing/invalid. The kimi rescue patch
    (reqparse.py L114-138) wraps that getattr in a try/except HTTPException
    so the parser falls back to MultiDict() instead of bubbling a 500.
    """

    def get(self):
        return {"todos": TODOS}, 200

    def post(self):
        parser = RequestParser()
        parser.add_argument("task", type=str, required=True, location="json")
        parser.add_argument("priority", type=inputs.positive, default=1, location="json")
        args = parser.parse_args()
        new_id = str(len(TODOS) + 1)
        TODOS[new_id] = {"task": args["task"], "done": False, "priority": args["priority"]}
        return {"id": new_id, "task": args["task"]}, 201


class Todo(Resource):
    def get(self, todo_id):
        if todo_id not in TODOS:
            return {"error": "not found"}, 404
        return TODOS[todo_id], 200


def build_app():
    app = Flask(__name__)
    api = Api(app)
    api.add_resource(TodoList, "/todos")
    api.add_resource(Todo, "/todos/<string:todo_id>")
    return app


def main():
    log = []

    def step(msg):
        print(msg)
        log.append(msg)

    app = build_app()
    srv = make_server("127.0.0.1", 0, app)
    port = srv.server_port
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)

    base = f"http://127.0.0.1:{port}"
    step(f"[server] real socket on {base}")

    try:
        # Test 1: GET single resource
        r = requests.get(f"{base}/todos/1", timeout=5)
        assert r.status_code == 200, r.status_code
        body = r.json()
        assert body["task"] == "buy milk", body
        assert body["done"] is False
        step(f"[GET /todos/1] 200 -> {body}")

        # Test 2: POST valid JSON via reqparse over real HTTP
        r = requests.post(f"{base}/todos", json={"task": "review PR", "priority": 3}, timeout=5)
        assert r.status_code == 201, (r.status_code, r.text)
        body = r.json()
        assert body["task"] == "review PR", body
        assert "id" in body
        step(f"[POST /todos] 201 -> {body}")

        # Test 3: POST with NO body — Werkzeug 3.x HTTPException surface.
        # Without the kimi patch, getattr(request,'json') raises BadRequest
        # inside Argument.source. With the patch reqparse falls back to
        # MultiDict() and reports the missing required arg as a clean 400.
        r = requests.post(
            f"{base}/todos",
            data="", headers={"Content-Type": "application/json"},
            timeout=5,
        )
        assert r.status_code == 400, (r.status_code, r.text)
        body = r.json()
        assert "message" in body, body
        assert "task" in str(body).lower(), body
        step(f"[POST /todos empty body] 400 (reqparse) -> {body}")

        # Test 4: POST malformed JSON — same surface, harder.
        r = requests.post(
            f"{base}/todos",
            data="not-json{", headers={"Content-Type": "application/json"},
            timeout=5,
        )
        assert r.status_code == 400, (r.status_code, r.text)
        step(f"[POST /todos malformed] 400 -> ok")

        # Test 5: 404 path
        r = requests.get(f"{base}/todos/999", timeout=5)
        assert r.status_code == 404, r.status_code
        step(f"[GET /todos/999] 404")

        step(f"[modules] Api={Api.__module__} Resource={Resource.__module__} "
             f"RequestParser={RequestParser.__module__} inputs={inputs.__name__}")

        print("\nUSABLE")
    finally:
        srv.shutdown()
        with open("/home/zhihao/hdd/RepoRescue_Clean/artifacts/flask-restful/run.log", "a") as f:
            f.write("\n".join(log) + "\n")


if __name__ == "__main__":
    sys.exit(main() or 0)
