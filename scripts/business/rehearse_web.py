"""Run real browser journey against an empty temporary database, never a live company."""

import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1_service.api import create_app

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as work, socket.socket() as sock:
        tok = secrets.token_urlsafe(24)
        folder = Path(work)
        app = create_app(
            folder / "db", token=tok, firm_id="REHEARSAL", key_dir=folder / "keys"
        )
        sock.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = threading.Thread(
            target=server.run, kwargs={"sockets": [sock]}, daemon=True
        )
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.05)
            env = dict(
                os.environ,
                PILOT_TEST_URL=f"http://127.0.0.1:{sock.getsockname()[1]}",
                PILOT_TEST_TOKEN=tok,
            )
            subprocess.run(
                ["node", str(Path(__file__).with_suffix(".cjs"))],
                cwd=ROOT,
                env=env,
                check=True,
                timeout=120,
            )
        finally:
            server.should_exit = True
            thread.join(10)
