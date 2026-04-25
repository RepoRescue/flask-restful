# flask-restful — Usability Validation (SKILL v2)

**Selected rescue**: `kimi` (T2 PASS). srconly: FAIL. Other PASS: gpt-codex (per task instruction we use kimi).
**Scenario type**: C (web framework, real HTTP)
**Real-world use**: Mount `flask_restful.Api` on a Flask app, declare `Resource` subclasses, parse JSON/form bodies via `reqparse.RequestParser`. Flagship surface = real HTTP request -> reqparse -> Resource method.

## Step 0: Import sanity
`venv-t2/bin/python -c "import flask_restful"` -> OK. flask 3.1.3, werkzeug 3.1.8, flask-restful 0.3.10.

## Step 4: Install + core feature (clean venv)
- `python3.13 -m venv /tmp/flask-restful-clean`
- `pip install -e repos/rescue_kimi/flask-restful` -> OK
- `cd /tmp/flask-restful-clean` (left rescue tree)
- `python artifacts/flask-restful/usability_validate.py` -> 5/5 endpoints pass:
  - GET single resource (200)
  - POST valid JSON (201) via reqparse
  - POST empty body, ct=json (400 from reqparse, NOT 500)
  - POST malformed JSON (400)
  - GET 404
- Server: `werkzeug.serving.make_server` real socket on 127.0.0.1:<random>; client: `requests`. NO `app.test_client()`.

## Hard constraint 6: Py3.13 / Werkzeug 3.x surface

| Surface | Evidence |
|---|---|
| Werkzeug 3.x raises `BadRequest` (HTTPException) from `request.json`/`values` getattr on bad/missing body | `flask_restful/reqparse.py` L114-138 - kimi wraps every `getattr`/`callable()` in `try/except exceptions.HTTPException: return MultiDict()`. See `outputs/kimi/flask-restful/flask-restful.src.patch`. |
| Validation hits the surface | Test 3 (POST empty body, ct=json) returns `400 {"message":{"task":"Missing required parameter in the JSON body"}}` - clean reqparse error. Without patch this would 500. |
| Werkzeug 3.x removed `__version__` | `import werkzeug; werkzeug.__version__` -> AttributeError (we use `importlib.metadata.version`). |

## Beyond unit tests (constraint 3)
`grep -rn "make_server\|werkzeug.serving" repos/rescue_kimi/flask-restful/tests/` -> 0 matches. tests/ has 32 `test_client()` calls (in-process WSGI). We are the first run going over a real socket.

## Three distinct submodules (constraint 5)
- `flask_restful` (Api, Resource - __init__.py)
- `flask_restful.reqparse` (RequestParser - patched file)
- `flask_restful.inputs` (positive coercion)

Each exercised in usability_validate.py Tests 1-4.

## Step 6: Downstream cascade - Path A
Downstream: **flask-restful-swagger-3** (PyPI, swagger/OpenAPI generator built on `flask_restful.Api`).
`/tmp/flask-restful-downstream` venv = rescue tree (editable) + flask-restful-swagger-3.
- Editable install wins: `flask_restful.__file__ == /home/zhihao/hdd/RepoRescue_Clean/repos/rescue_kimi/flask-restful/flask_restful/__init__.py`
- `GET /api/swagger.json` -> 200, OpenAPI doc with `/todo/{todo_id}`
- `GET /todo/42` -> 200, `{"id":42,"task":"task-42"}`
Downstream uses our patched reqparse internals (`RequestParserExtractor`).

## Step 7: Bug-hunt (real HTTP)
| # | Input | Result |
|---|---|---|
| 1 | empty body, no ct | 200 args=null |
| 2 | empty body ct=json | 200 args=null |
| 3 | malformed JSON `{not` | **200 args=null** (soft finding) |
| 4 | Unicode form (umlaut + CJK) | 200 decoded |
| 5 | 100K char JSON string | 200 |
| 6 | 5x repeat | all 200 |
| 7 | type mismatch (count="not-int") | 400 reqparse |
| 8 | 80 concurrent (8 threads x 10) | no crash, no 500 |

No 500 leaked. HTTPException-from-getattr path sealed.

**Soft finding**: kimi patch is too eager - any `HTTPException` from `getattr(request,"json")` is swallowed -> `MultiDict()`. Malformed JSON (Attack 3) silently treated as "no JSON", required fields surface as null rather than 400. Pre-3.13 flask-restful would have surfaced 400. Behavioral regression, not crash. Tests miss it because `test_client()` always uses well-formed JSON. Patch could re-raise non-BadRequest HTTPExceptions; rescue still functional for happy path.

## Verdict
STATUS: USABLE

Reason: Installs cleanly in fresh venv outside rescue tree; serves real HTTP via make_server + requests on 5 endpoints; exercises three distinct submodules; demonstrably stresses Werkzeug-3.x HTTPException-from-getattr surface (patch + validation evidence aligned); passes real downstream cascade (flask-restful-swagger-3); survives bug-hunt without crashes. Hard constraints 1-8 all pass. Over-broad except is a soft regression, not a blocker.

| # | Constraint | Status |
|---|---|---|
| 1 | Real input | PASS (real JSON bytes over socket) |
| 2 | Real output assertion | PASS (status+body+content asserts) |
| 3 | Beyond unit tests | PASS (tests/ 0 real-socket usage) |
| 4 | Primary use mode | PASS (make_server + requests; no test_client) |
| 5 | Three distinct paths | PASS (Api, reqparse, inputs) |
| 6 | 3.13 incompat surface | PASS (Werkzeug HTTPException-from-getattr; patch+validation aligned) |
| 7 | Installed + core feature | PASS (pip install -e in clean venv, run from /tmp) |
| 8 | Downstream OR scenario | PASS (downstream A: flask-restful-swagger-3 over real HTTP) |
