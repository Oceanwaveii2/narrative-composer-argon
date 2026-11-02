"""
Unit and Integration Tests for DesignCraft Interactive TCP JSON-RPC Client.
Tests loopback connection, JSON-lines framing, command dispatch, and error handling.
"""

import json
from pathlib import Path
import socket
import threading
import time
import unittest

from narrative_composer.designcraft import DesignCraftRPCClient, DesignCraftRPCError


class MockDesignCraftServer:
    """Mock TCP server implementing DesignCraft's line-delimited control protocol."""

    def __init__(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.bind(("127.0.0.1", 0))
        self.server_sock.listen(1)
        self.port = self.server_sock.getsockname()[1]
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.running:
            try:
                self.server_sock.settimeout(0.5)
                client_sock, _ = self.server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            reader = client_sock.makefile("r", encoding="utf-8")
            writer = client_sock.makefile("w", encoding="utf-8")

            while self.running:
                line = reader.readline()
                if not line:
                    break
                try:
                    req = json.loads(line)
                    req_id = req.get("id")
                    method = req.get("method")
                    params = req.get("params", {})

                    if method == "engine.commands":
                        reply = {
                            "id": req_id,
                            "ok": True,
                            "result": [{"id": "file.open", "enabled": True}],
                        }
                    elif method == "document.inspect":
                        reply = {
                            "id": req_id,
                            "ok": True,
                            "result": {"title": "Mock Screenplay", "pages": 59},
                        }
                    elif method == "ui.inspect":
                        reply = {
                            "id": req_id,
                            "ok": True,
                            "result": {"tool": "selection", "window": [1920, 1080]},
                        }
                    elif method == "app.open":
                        reply = {
                            "id": req_id,
                            "ok": True,
                            "result": {"path": params.get("path"), "pages": 59},
                        }
                    elif method == "app.export":
                        reply = {
                            "id": req_id,
                            "ok": True,
                            "result": {"path": params.get("path"), "bytes": 1024},
                        }
                    elif method == "error.test":
                        reply = {
                            "id": req_id,
                            "ok": False,
                            "error": "Simulated engine error",
                        }
                    else:
                        reply = {
                            "id": req_id,
                            "ok": True,
                            "result": f"Executed {method}",
                        }

                    writer.write(json.dumps(reply) + "\n")
                    writer.flush()
                except Exception as e:
                    writer.write(
                        json.dumps({"ok": False, "error": str(e)}) + "\n"
                    )
                    writer.flush()
                    break

            client_sock.close()

    def close(self):
        self.running = False
        try:
            self.server_sock.close()
        except OSError:
            pass


@unittest.skip("DesignCraft disabled")
class TestDesignCraftRPCClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = MockDesignCraftServer()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def test_connection_refused_error(self):
        """Verify clean error when connecting to an inactive port."""
        client = DesignCraftRPCClient(port=59999, timeout=0.5)
        with self.assertRaises(ConnectionRefusedError):
            client.connect()

    def test_context_manager_and_commands(self):
        """Verify context manager lifecycle and engine.commands query."""
        with DesignCraftRPCClient(port=self.server.port) as client:
            self.assertTrue(client.is_connected())
            cmds = client.get_commands()
            self.assertIsInstance(cmds, list)
            self.assertEqual(cmds[0]["id"], "file.open")

    def test_document_and_ui_inspection(self):
        """Verify inspection methods return structured mock state."""
        with DesignCraftRPCClient(port=self.server.port) as client:
            doc_info = client.inspect_document()
            self.assertEqual(doc_info.get("pages"), 59)
            self.assertEqual(doc_info.get("title"), "Mock Screenplay")

            ui_info = client.inspect_ui()
            self.assertEqual(ui_info.get("tool"), "selection")

    def test_open_and_export_methods(self):
        """Verify file opening and image export dispatch."""
        with DesignCraftRPCClient(port=self.server.port) as client:
            res_open = client.open_document("test.designcraft")
            self.assertEqual(res_open.get("pages"), 59)

            res_export = client.export_image("output.png", page=1, scale=1.5)
            self.assertEqual(res_export.get("bytes"), 1024)

    def test_error_handling(self):
        """Verify DesignCraftRPCError is raised when server returns ok: false."""
        with DesignCraftRPCClient(port=self.server.port) as client:
            with self.assertRaises(DesignCraftRPCError) as cm:
                client.request(method="error.test")
            self.assertIn("Simulated engine error", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
