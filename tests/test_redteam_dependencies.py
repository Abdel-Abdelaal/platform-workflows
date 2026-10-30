"""Exercise the actual get-uri client with the security-patched FTP dependency."""

import json
import os
import shutil
import socket
import socketserver
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "redteam"
CLIENT = ROOT / "node_modules/get-uri/dist/index.js"
NODE = shutil.which("node")
PAYLOAD = b"controlled local FTP transfer\n"


class LocalFTP(socketserver.StreamRequestHandler):
    passive: socket.socket | None = None

    def reply(self, text: str) -> None:
        self.wfile.write((text + "\r\n").encode())
        self.wfile.flush()

    def respond(self, command: str, argument: str) -> bool:
        ordinary = {
            "USER": "331 Password required",
            "PASS": "230 Logged in",
            "FEAT": "211 No extensions",
            "PWD": '257 "/"',
            "SIZE": "213 " + str(len(PAYLOAD)),
        }
        if command in ordinary:
            self.reply(ordinary[command])
        elif command == "MDTM":
            self.reply(
                "550 Missing file"
                if argument == "/missing.txt"
                else "213 20261030190000"
            )
        elif command == "EPSV":
            self.passive = socket.socket()
            self.passive.bind(("127.0.0.1", 0))
            self.passive.listen(1)
            self.passive.settimeout(10)
            port = self.passive.getsockname()[1]
            self.reply(f"229 Entering Extended Passive Mode (|||{port}|)")
        elif command == "RETR":
            self.reply("150 Opening binary transfer")
            assert self.passive is not None
            connection, _ = self.passive.accept()
            with connection:
                connection.sendall(PAYLOAD)
            self.passive.close()
            self.passive = None
            self.reply("226 Transfer complete")
        elif command == "QUIT":
            self.reply("221 Goodbye")
            return False
        else:
            self.reply("200 Accepted")
        return True

    def handle(self) -> None:
        self.request.settimeout(10)
        self.reply("220 Local compatibility fixture")
        try:
            for raw in self.rfile:
                command, _, argument = raw.decode().strip().partition(" ")
                if not self.respond(command, argument):
                    break
        finally:
            if self.passive is not None:
                self.passive.close()


@pytest.mark.skipif(
    NODE is None or not CLIENT.is_file(),
    reason="red-team Node dependencies are installed by the dedicated red-team job",
)
def test_patched_basic_ftp_remains_compatible_with_get_uri() -> None:
    assert NODE is not None
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), LocalFTP) as server:
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"ftp://127.0.0.1:{server.server_address[1]}"
        program = f"""
import assert from 'node:assert/strict';
import {{ getUri }} from {json.dumps(CLIENT.as_uri())};
const base = {json.dumps(base)};
const stream = await getUri(base + '/fixture.txt');
let text = ''; for await (const chunk of stream) text += chunk.toString();
assert.equal(text, {json.dumps(PAYLOAD.decode())});
await assert.rejects(
  getUri(base + '/fixture.txt', {{cache:stream}}), {{code:'ENOTMODIFIED'}});
await assert.rejects(getUri(base + '/missing.txt'), {{code:'ENOTFOUND'}});
"""
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP"}
        }
        try:
            result = subprocess.run(  # noqa: S603 - fixed loopback fixture, no provider input
                [NODE, "--input-type=module", "-e", program],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=25,
                check=False,
            )
            assert result.returncode == 0, result.stderr
        finally:
            server.shutdown()
            thread.join()
