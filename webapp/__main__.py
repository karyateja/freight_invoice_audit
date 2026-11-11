"""python -m webapp [--host 127.0.0.1] [--port 8000] [--open]"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

from .datasets import list_datasets
from .server import make_server


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m webapp", description="Freight audit web UI (stdlib only).")
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default 127.0.0.1; the API can start jobs, so keep it local)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--open", action="store_true", help="open the browser")
    ap.add_argument("--quiet", action="store_true", help="no request log")
    args = ap.parse_args(argv)

    srv = make_server(args.host, args.port, args.quiet)
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{srv.server_address[1]}/"
    ds = list_datasets()
    print(f"Freight audit web UI on {url}")
    print(f"datasets: {', '.join(d['name'] for d in ds) or 'none yet; generate one from the Run page'}")
    print("Ctrl+C to stop")
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
