"""
Downstream cascade: flask-restful-swagger-3 (a real PyPI package that builds
on flask-restful by subclassing Api and reusing reqparse / Resource).

If our flask-restful rescue tree is loaded as the editable install, the
downstream's Api subclass picks up our patched reqparse implicitly. We exercise
its swagger.json endpoint plus a Resource and verify the OpenAPI doc is real.
"""
import threading
import time

import requests
from flask import Flask
from werkzeug.serving import make_server

from flask_restful_swagger_3 import Api, swagger, Resource, Schema


class TodoSchema(Schema):
    type = "object"
    properties = {
        "id": {"type": "integer"},
        "task": {"type": "string"},
    }


class TodoResource(Resource):
    @swagger.response(response_code=200, description="ok", schema=TodoSchema)
    def get(self, todo_id):
        return {"id": int(todo_id), "task": f"task-{todo_id}"}, 200


def main():
    app = Flask(__name__)
    api = Api(
        app,
        version="1.0",
        title="downstream-test",
        description="exercise flask-restful via flask-restful-swagger-3",
        swagger_prefix_url="/api",
        swagger_url="swagger.json",
    )
    api.add_resource(TodoResource, "/todo/<int:todo_id>")

    srv = make_server("127.0.0.1", 0, app)
    port = srv.server_port
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.3)
    base = f"http://127.0.0.1:{port}"

    try:
        # 1. Swagger doc (downstream feature)
        r = requests.get(f"{base}/api/swagger.json", timeout=5)
        # url shape from swagger-3: {swagger_prefix_url}/{swagger_url}
        assert r.status_code == 200, r.status_code
        spec = r.json()
        assert spec["info"]["title"] == "downstream-test", spec["info"]
        assert "/todo/{todo_id}" in spec["paths"], list(spec["paths"].keys())
        print(f"[swagger.json] paths={list(spec['paths'].keys())}")

        # 2. Underlying flask-restful Resource still serves real HTTP
        r = requests.get(f"{base}/todo/42", timeout=5)
        assert r.status_code == 200, r.status_code
        body = r.json()
        assert body == {"id": 42, "task": "task-42"}, body
        print(f"[GET /todo/42] -> {body}")

        # 3. Confirm we are on the rescue tree, not PyPI flask-restful
        import flask_restful
        assert "rescue_kimi" in flask_restful.__file__, flask_restful.__file__
        print(f"[provenance] flask_restful.__file__={flask_restful.__file__}")

        print("DOWNSTREAM_OK")
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
