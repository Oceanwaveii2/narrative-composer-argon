"""
DesignCraft Interactive TCP JSON-RPC Client.
Provides real-time programmatic control over the live DesignCraft desktop application
via its loopback JSON-lines control server on port 7979 (or custom port).
"""

from __future__ import annotations
import json
from pathlib import Path
import socket
from typing import Any, Dict, List, Optional, Union


class DesignCraftRPCError(RuntimeError):
    """Raised when an RPC request returns an error from the DesignCraft control server."""
    pass


class DesignCraftRPCClient:
    """
    Client for DesignCraft JSON-lines control server (default port 7979).
    Enables live agent editing, document inspection, layout adjustment, and proofing.
    """

    DEFAULT_PORT = 7979

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
        timeout: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._reader = None
        self._next_id = 1

    def connect(self) -> DesignCraftRPCClient:
        """Establishes connection to the DesignCraft control server."""
        if self.sock is not None:
            return self
        try:
            self.sock = socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            )
            self._reader = self.sock.makefile("r", encoding="utf-8")
        except OSError as e:
            self.sock = None
            self._reader = None
            raise ConnectionRefusedError(
                f"Failed to connect to DesignCraft control server at {self.host}:{self.port}. "
                f"Ensure DesignCraft desktop application is running with control server enabled. ({e})"
            ) from e
        return self

    def disconnect(self) -> None:
        """Closes the active TCP connection."""
        if self._reader:
            try:
                self._reader.close()
            except Exception:
                pass
            self._reader = None
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def is_connected(self) -> bool:
        return self.sock is not None

    def __enter__(self) -> DesignCraftRPCClient:
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()

    def request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Sends a single-line JSON request and returns the parsed result.
        Enforces DesignCraft line framing: exactly one JSON object per line.
        """
        if not self.is_connected():
            self.connect()

        req_id = self._next_id
        self._next_id += 1

        payload = {
            "id": req_id,
            "method": method,
            "params": params if params is not None else {},
        }

        wire_line = json.dumps(payload, separators=(",", ":")) + "\n"
        assert self.sock is not None
        assert self._reader is not None

        try:
            self.sock.sendall(wire_line.encode("utf-8"))
            raw_reply = self._reader.readline()
        except OSError as e:
            self.disconnect()
            raise DesignCraftRPCError(f"Network error communicating with control server: {e}") from e

        if not raw_reply:
            self.disconnect()
            raise DesignCraftRPCError("Control server closed connection unexpectedly.")

        try:
            reply = json.loads(raw_reply)
        except json.JSONDecodeError as e:
            raise DesignCraftRPCError(f"Invalid JSON received from control server: {raw_reply.strip()}") from e

        if not reply.get("ok", True):
            err_msg = reply.get("error", "Unknown control server error")
            raise DesignCraftRPCError(f"RPC request '{method}' failed: {err_msg}")

        return reply.get("result", reply)

    # High-level engine commands
    def execute_command(
        self, command: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Executes any internal engine command (e.g. file.open, font.replace)."""
        return self.request(
            method="engine.execute",
            params={"command": command, "params": params or {}},
        )

    def get_commands(self) -> List[Dict[str, Any]]:
        """Retrieves list of all available engine and UI commands with their enablement state."""
        return self.request(method="engine.commands")

    def inspect_document(self) -> Dict[str, Any]:
        """Returns structured metadata summary of the active document."""
        return self.request(method="document.inspect")

    def inspect_ui(self) -> Dict[str, Any]:
        """Returns UI state including open panels, selected tool, and window dimensions."""
        return self.request(method="ui.inspect")

    def open_document(self, path: Union[str, Path]) -> Any:
        """Opens a .designcraft or .idml file in the running application."""
        abs_p = str(Path(path).resolve())
        return self.request(method="app.open", params={"path": abs_p})

    def save_document(self, path: Optional[Union[str, Path]] = None) -> Any:
        """Saves the current document, optionally to a new path."""
        params = {"path": str(Path(path).resolve())} if path else {}
        return self.request(method="app.save", params=params)

    def export_image(
        self,
        path: Union[str, Path],
        page: int = 1,
        scale: float = 1.5,
    ) -> Any:
        """Exports the specified page (1-indexed) to a PNG file."""
        abs_p = str(Path(path).resolve())
        return self.request(
            method="app.export",
            params={"path": abs_p, "page": page, "scale": scale},
        )

    def take_screenshot(
        self, path: Optional[Union[str, Path]] = None
    ) -> Any:
        """Captures a screenshot of the entire application window."""
        params = {"path": str(Path(path).resolve())} if path else {}
        return self.request(method="ui.screenshot", params=params)

    def quit_app(self) -> Any:
        """Requests graceful application shutdown."""
        return self.request(method="app.quit")
