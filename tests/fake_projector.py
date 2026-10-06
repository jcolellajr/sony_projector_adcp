"""A minimal in-process ADCP server for tests.

Speaks just enough of the protocol the integration uses: a challenge line
("NOKEY" or a random number), SHA256(challenge + password) authentication, then
one response line per command line.
"""
import asyncio
import hashlib

CHALLENGE = "12345678"


class FakeProjector:
    """ADCP server on 127.0.0.1 with scriptable responses."""

    def __init__(self, password: str | None = "Projector") -> None:
        # None means authentication disabled on the projector (NOKEY).
        self.password = password
        self.responses: dict[str, str] = {
            "power_status ?": '"standby"',
            "timer ?": '[{"operation":128},{"light_src":123},{"prev_light_src":0}]',
            # Formats as answered by the real VW715ES (2026-10-06).
            "serialnum ?": '"5100123"',
            "mac_address ?": '"94-db-56-7b-0d-9d"',
            "modelname ?": '"VPL-VW715ES"',
        }
        self.received: list[str] = []
        # Command line -> event; the reply waits until the event is set.
        # Lets a test hold a poll mid-flight.
        self.hold: dict[str, asyncio.Event] = {}
        self.holding = asyncio.Event()
        self.port = 0
        self._server: asyncio.base_events.Server | None = None
        self._writers: list[asyncio.StreamWriter] = []

    async def start(self, port: int = 0) -> None:
        """Listen on ``port`` (0 = any free port)."""
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        self.drop_sessions()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    def drop_sessions(self) -> None:
        """Close every open session, as the projector does after ~60s idle."""
        for writer in self._writers:
            writer.close()
        self._writers.clear()

    def set_power(self, status: str) -> None:
        self.responses["power_status ?"] = f'"{status}"'

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._writers.append(writer)
        try:
            if self.password is None:
                writer.write(b"NOKEY\r\n")
            else:
                writer.write(f"{CHALLENGE}\r\n".encode())
                await writer.drain()
                digest = (await reader.readuntil(b"\r\n")).decode().strip()
                expected = hashlib.sha256(
                    f"{CHALLENGE}{self.password}".encode()
                ).hexdigest()
                if digest != expected:
                    writer.write(b"err_auth\r\n")
                    await writer.drain()
                    writer.close()
                    return
                writer.write(b"OK\r\n")
            await writer.drain()

            while True:
                line = (await reader.readuntil(b"\r\n")).decode().strip()
                self.received.append(line)
                if line in self.hold:
                    self.holding.set()
                    await self.hold[line].wait()
                writer.write(f"{self._respond(line)}\r\n".encode())
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    def _respond(self, line: str) -> str:
        if line in self.responses:
            return self.responses[line]
        if line.endswith(" ?"):
            return "err_cmd"
        # Any set-style command is accepted unless scripted otherwise.
        return "ok"
