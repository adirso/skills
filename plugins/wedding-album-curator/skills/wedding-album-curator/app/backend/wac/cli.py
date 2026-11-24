"""Command-line entry point: `wac serve | doctor | hardware | models | benchmark`."""
from __future__ import annotations

import argparse
import json
import socket
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

from . import config


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) != 0


def cmd_serve(args) -> int:
    import uvicorn

    from .api import app, mount_frontend

    if args.host not in ("127.0.0.1", "localhost") and not args.i_understand_network_exposure:
        print("Refusing to bind to a non-localhost address. Your photos would be reachable from the network.")
        return 2
    if not _port_free(args.host, args.port):
        print(f"Port {args.port} is in use. Is Wedding Album Curator already running? Try http://127.0.0.1:{args.port}")
        return 1
    app.state.port = args.port
    mount_frontend()
    url = f"http://127.0.0.1:{args.port}"
    print(f"Wedding Album Curator {config.VERSION} running at {url}")
    print(f"Data folder: {config.data_dir()}")
    if args.open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_doctor(args) -> int:
    from . import embeddings, models_registry as mr
    from .imaging import HEIF_SUPPORTED
    from .providers import claude_code, ollama

    checks = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})

    check("Python version", sys.version_info >= (3, 11), sys.version.split()[0])
    for mod in ("fastapi", "cv2", "PIL", "numpy", "sklearn"):
        try:
            __import__(mod)
            check(f"package {mod}", True)
        except Exception as e:
            check(f"package {mod}", False, str(e))
    check("HEIC/HEIF support", HEIF_SUPPORTED, "pillow-heif")
    for mid in mr.MODELS:
        check(f"model {mid}", mr.is_installed(mid), "installed" if mr.is_installed(mid) else "not downloaded (approve in the app or `wac models --download`)")
    try:
        import torch  # noqa: F401
        import open_clip  # noqa: F401
        check("ML extras (torch, open_clip)", True, f"device: {embeddings.device_name()}")
    except Exception as e:
        check("ML extras (torch, open_clip)", False, str(e))
    try:
        import mediapipe  # noqa: F401
        check("MediaPipe (eye state)", True)
    except Exception as e:
        check("MediaPipe (eye state)", False, str(e))
    st = ollama.server_status()
    check("Ollama server (optional)", st["running"], st.get("version") or "not running")
    check("Claude Code CLI (optional)", bool(claude_code.cli_path()), claude_code.cli_version() or "not found")
    dist = config.frontend_dist()
    check("Frontend build", (dist / "index.html").exists(), str(dist))
    check("Data directory writable", _writable(config.data_dir()), str(config.data_dir()))
    if args.json:
        print(json.dumps(checks, indent=2))
    else:
        for c in checks:
            print(f"[{'OK' if c['ok'] else '--'}] {c['check']}" + (f" — {c['detail']}" if c["detail"] else ""))
    essential = [c for c in checks if c["check"].startswith("package") or c["check"] == "Python version"]
    return 0 if all(c["ok"] for c in essential) else 1


def _writable(p: Path) -> bool:
    try:
        with tempfile.NamedTemporaryFile(dir=p):
            return True
    except OSError:
        return False


def cmd_hardware(args) -> int:
    from . import hardware

    info = hardware.detect()
    print(json.dumps({"info": info, "recommendation": hardware.recommend(info)}, indent=2))
    return 0


def cmd_models(args) -> int:
    from . import models_registry as mr

    if args.download:
        ids = list(mr.MODELS) if args.download == ["all"] else args.download
        total = sum(mr.MODELS[i].size_bytes for i in ids if not mr.is_installed(i))
        print(f"About to download {len(ids)} model(s), {total / 1e6:.0f} MB:")
        for i in ids:
            m = mr.MODELS[i]
            print(f"  - {m.name} ({m.size_bytes / 1e6:.1f} MB, {m.license}) from {m.url}")
        if not args.yes:
            if input("Proceed? [y/N] ").strip().lower() != "y":
                print("Cancelled.")
                return 1
        mr.downloads.start(ids)
        while any((mr.downloads.progress.get(i) or {}).get("state") == "downloading" for i in ids):
            time.sleep(1)
        for i in ids:
            print(i, mr.downloads.progress.get(i) or ("installed" if mr.is_installed(i) else "?"))
        return 0 if all(mr.is_installed(i) for i in ids) else 1
    for s in mr.downloads.status():
        print(f"[{'installed' if s['installed'] else 'missing  '}] {s['id']:16} {s['size_bytes'] / 1e6:8.1f} MB  {s['license']:10} {s['name']}")
    return 0


def cmd_benchmark(args) -> int:
    """Run the full local analysis on a folder in a throwaway data dir and report measured timings."""
    import os

    from .jobs import JobContext
    from .pipeline import Project, run_analysis
    from . import selection

    src = Path(args.folder).expanduser().resolve()
    with tempfile.TemporaryDirectory() as tmp:
        proj = Project("bench", "bench", src, Path(tmp) / "bench")
        with proj.db.tx() as con:
            cur = con.execute("INSERT INTO jobs(kind, state) VALUES ('bench','running')")
            jid = cur.lastrowid
        ctx = JobContext(job_id=jid, db=proj.db, params={})
        res = run_analysis(proj, ctx)
        t = time.time()
        sel = selection.generate(proj.db, {"target": args.target})
        res["timings"]["selection_s"] = round(time.time() - t, 3)
        res["selection"] = {k: sel[k] for k in ("selected", "shortfall", "couple_share")}
        res["machine"] = {"cpu_count": os.cpu_count()}
        print(json.dumps(res, indent=2, default=str))
    return 0


def cmd_sample(args) -> int:
    from .sample import generate

    faces = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    m = generate(Path(args.folder).expanduser(), n_scenes=args.scenes, faces_dir=faces if faces.is_dir() else None)
    print(f"Created a synthetic sample folder at {args.folder} ({len(m['files'])} scenes, "
          f"{sum(len(b) for b in m['bursts'])} burst photos, {len(m['faces'])} face photos).")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="wac", description="Wedding Album Curator")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="start the local app")
    s.add_argument("--host", default=config.DEFAULT_HOST)
    s.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    s.add_argument("--open", action="store_true", help="open the browser")
    s.add_argument("--i-understand-network-exposure", action="store_true", help=argparse.SUPPRESS)
    d = sub.add_parser("doctor", help="diagnose the installation")
    d.add_argument("--json", action="store_true")
    sub.add_parser("hardware", help="show hardware and model recommendations")
    m = sub.add_parser("models", help="list or download local models")
    m.add_argument("--download", nargs="+", metavar="ID", help="model ids or 'all'")
    m.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    b = sub.add_parser("benchmark", help="measure analysis speed on a folder (nothing is modified)")
    b.add_argument("folder")
    b.add_argument("--target", type=int, default=500)
    sd = sub.add_parser("sample-dataset", help="create a small synthetic demo folder")
    sd.add_argument("folder")
    sd.add_argument("--scenes", type=int, default=30)
    args = p.parse_args(argv)
    fn = {"serve": cmd_serve, "doctor": cmd_doctor, "hardware": cmd_hardware, "models": cmd_models,
          "benchmark": cmd_benchmark, "sample-dataset": cmd_sample}.get(args.cmd)
    if not fn:
        p.print_help()
        return 0
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
