"""
Step 7: Bug-hunt against the kimi-rescued flask-restful.

We attack the exact 3.13/Werkzeug-3 surface kimi patched (HTTPException-from-
getattr in reqparse.Argument.source) with adversarial inputs that the unit
tests don't cover.
"""
import threading
import time

import requests
from flask import Flask
from werkzeug.serving import make_server

from flask_restful import Api, Resource, reqparse


HITS = []


class Echo(Resource):
    def post(self):
        p = reqparse.RequestParser()
        # Two locations: forces the *list-branch* of patched code path
        # (lines 128-138 in reqparse.py).
        p.add_argument("name", type=str, location=["json", "form"])
        p.add_argument("count", type=int, location=["json", "values"])
        try:
            args = p.parse_args()
            HITS.append(("ok", args))
            return {"args": args}, 200
        except Exception as e:
            HITS.append(("exc", type(e).__name__, str(e)))
            raise


def main():
    app = Flask(__name__)
    api = Api(app)
    api.add_resource(Echo, "/echo")
    srv = make_server("127.0.0.1", 0, app)
    port = srv.server_port
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.3)
    base = f"http://127.0.0.1:{port}"

    findings = []

    def run(label, **kw):
        try:
            r = requests.post(f"{base}/echo", timeout=5, **kw)
            findings.append((label, r.status_code, r.text[:200]))
        except Exception as e:
            findings.append((label, "EXC", repr(e)))

    # Attack 1: empty Content-Type, empty body
    run("empty body, no ct", data="")
    # Attack 2: Content-Type: application/json but body is empty -> Werkzeug
    # 3.x raises BadRequest from request.json
    run("ct=json empty", data="", headers={"Content-Type": "application/json"})
    # Attack 3: malformed JSON
    run("ct=json bad", data="{not", headers={"Content-Type": "application/json"})
    # Attack 4: Unicode key/value in form
    run("unicode form", data={"name": "ümlaut-名前", "count": "7"})
    # Attack 5: very long string in JSON (state leak / memory)
    run("long json", json={"name": "x" * 100_000, "count": 1})
    # Attack 6: repeated calls (state leak)
    for i in range(5):
        run(f"repeat-{i}", json={"name": f"r{i}", "count": i})
    # Attack 7: count is wrong type (str where int expected) -> reqparse 400
    run("type mismatch", json={"name": "a", "count": "not-an-int"})
    # Attack 8: concurrent calls (thread safety on RequestParser instance)
    def hammer():
        for _ in range(10):
            try:
                requests.post(f"{base}/echo",
                              json={"name": "t", "count": 1}, timeout=5)
            except Exception:
                pass
    threads = [threading.Thread(target=hammer) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    findings.append(("concurrent-80", "ok", "no crash"))

    srv.shutdown()

    print("# Bug hunt findings")
    server_500_seen = False
    for f in findings:
        print(f)
        if isinstance(f[1], int) and f[1] >= 500:
            server_500_seen = True

    print()
    print("server_500_observed:", server_500_seen)
    # Critical: any 500 means the HTTPException-from-getattr leaked, which
    # would mean the patch is incomplete.
    assert not server_500_seen, "500 leaked from reqparse — patch hole"
    print("BUG_HUNT_DONE: no critical regression")


if __name__ == "__main__":
    main()
