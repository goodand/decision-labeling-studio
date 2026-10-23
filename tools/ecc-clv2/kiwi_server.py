"""Resident Kiwi analyzer on localhost (one JSON line per request) so hooks skip the ~0.6s model load.

Setup reused from the workspace's fastest measured config (a1-a7 downloaded_model_benchmark: 'cong'
model; analysis_runs/.../run_analysis.py:57 builds Kiwi(model_type='cong') once at module level).
  python kiwi_server.py            # serve (idles forever; exits on {"op":"stop"})
  python kiwi_server.py --stop     # ask a running server to exit (weekly Task Scheduler job)
Protocol: {"op":"tokens","text":...} -> {"tokens":[[form,tag],...]}   {"op":"ping"} -> {"ok":true,"kiwipiepy":ver,"model_type":"cong"}
"""
import json, os, socket, socketserver, sys, threading

HOST, PORT = "127.0.0.1", 48791
KIWI_KW = {"model_type": "cong", "num_workers": 1}


def stop(timeout=2.0) -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=timeout) as s:
            s.sendall(b'{"op":"stop"}\n')
            return True
    except OSError:
        return False


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline()
        try:
            req = json.loads(line.decode("utf-8"))
        except ValueError:
            return
        if req.get("op") == "stop":
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if req.get("op") == "tokens":
            toks = [[t.form, t.tag] for t in self.server.kiwi.tokenize(str(req.get("text", ""))[:2000])]
            self.wfile.write(json.dumps({"tokens": toks}, ensure_ascii=False).encode("utf-8") + b"\n")
        else:
            self.wfile.write(json.dumps({"ok": True, **self.server.identity}).encode("utf-8") + b"\n")


# The Kiwi the correction rules were verified against (STUDIO-ECC-016: 0.24.1 chosen for accuracy).
# Library AND model weights: a model retrain changes tokens even when the library version does not.
PIN = {"kiwipiepy": "0.24.1", "model_type": "cong",
       "cong.mdl_sha256": "5f64105e45f04e5313f41c0ff1db5fe629780c8076c4a6fd3b1b2cf78c2cc934"}


def identity() -> dict:
    """What a rule over Kiwi actually depends on: library version, model type, model weights."""
    import hashlib, os, kiwipiepy, kiwipiepy_model
    mdl = os.path.join(os.path.dirname(kiwipiepy_model.__file__), f"{KIWI_KW['model_type']}.mdl")
    with open(mdl, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    return {"kiwipiepy": kiwipiepy.__version__, "model_type": KIWI_KW["model_type"], "cong.mdl_sha256": digest}


def serve():
    from kiwipiepy import Kiwi
    ident = identity()
    if ident != PIN:  # never serve a Kiwi the rules were not verified against (silent drift is the failure mode)
        sys.exit(f"kiwi_server: installed Kiwi {ident} is not the pinned {PIN}; install the pin or change PIN + golden")
    # On Windows SO_REUSEADDR lets a second server bind the same port (two live servers, stop() only
    # reaches one), so keep the default there and let a duplicate start fail with EADDRINUSE.
    socketserver.TCPServer.allow_reuse_address = os.name != "nt"
    kiwi = Kiwi(**KIWI_KW)
    kiwi.tokenize("준비")  # warm up BEFORE binding, so "port open" means "ready to answer"
    with socketserver.ThreadingTCPServer((HOST, PORT), Handler) as srv:
        srv.kiwi = kiwi
        srv.identity = identity()
        srv.serve_forever()


if __name__ == "__main__":
    sys.exit(0 if ("--stop" not in sys.argv and serve() is None) else (0 if stop() else 1))
