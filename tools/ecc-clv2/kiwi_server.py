"""Resident Kiwi analyzer on localhost (one JSON line per request) so hooks skip the ~0.6s model load.

Setup reused from the workspace's fastest measured config (a1-a7 downloaded_model_benchmark: 'cong'
model; analysis_runs/.../run_analysis.py:57 builds Kiwi(model_type='cong') once at module level).
  python kiwi_server.py            # serve (idles forever; exits on {"op":"stop"})
  python kiwi_server.py --stop     # ask a running server to exit (weekly Task Scheduler job)
Protocol: {"op":"tokens","text":...} -> {"tokens":[[form,tag],...]}   {"op":"ping"} -> {"ok":true}
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
            self.wfile.write(b'{"ok":true}\n')


def serve():
    from kiwipiepy import Kiwi
    # On Windows SO_REUSEADDR lets a second server bind the same port (two live servers, stop() only
    # reaches one), so keep the default there and let a duplicate start fail with EADDRINUSE.
    socketserver.TCPServer.allow_reuse_address = os.name != "nt"
    kiwi = Kiwi(**KIWI_KW)
    kiwi.tokenize("준비")  # warm up BEFORE binding, so "port open" means "ready to answer"
    with socketserver.ThreadingTCPServer((HOST, PORT), Handler) as srv:
        srv.kiwi = kiwi
        srv.serve_forever()


if __name__ == "__main__":
    sys.exit(0 if ("--stop" not in sys.argv and serve() is None) else (0 if stop() else 1))
