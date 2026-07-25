"""Sony ADCP Protocol Handler."""
import asyncio
import hashlib
import logging
from typing import Optional

_LOGGER = logging.getLogger(__name__)

NEWLINE = "\r\n"
ENCODING = "ascii"
TIMEOUT = 10


class SonyProjectorADCP:
    """Handle ADCP protocol communication with Sony projector."""

    def __init__(self, host: str, port: int, password: str = "", use_auth: bool = True):
        """Initialize the ADCP connection."""
        self.host = host
        self.port = port
        self.password = password
        self.use_auth = use_auth
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        """Connect to the projector and authenticate if needed."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=TIMEOUT
            )
            
            # Read authentication challenge
            auth_response = await self._read_line()
            
            if auth_response.startswith("PJLINK") or not self.use_auth:
                # If we get PJLINK or auth is disabled, we might need different handling
                # For now, just continue
                if auth_response == "NOKEY":
                    _LOGGER.debug("Authentication disabled on projector")
                    return True
            
            # Authentication enabled - handle random number
            if self.use_auth and auth_response:
                # Response format: random_number\r\n
                random_num = auth_response.strip()
                
                if random_num and random_num != "NOKEY":
                    # Create hash: SHA256(random_number + password)
                    hash_input = f"{random_num}{self.password}"
                    hash_result = hashlib.sha256(hash_input.encode()).hexdigest()
                    
                    # Send hash
                    await self._write_line(hash_result)
                    
                    # Read authentication result
                    auth_result = await self._read_line()
                    
                    if auth_result != "OK":
                        _LOGGER.error("Authentication failed: %s", auth_result)
                        await self.disconnect()
                        return False
            
            _LOGGER.info("Connected to Sony projector at %s:%s", self.host, self.port)
            return True
            
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout connecting to projector")
            return False
        except Exception as e:
            _LOGGER.error("Error connecting to projector: %s", e)
            return False

    async def disconnect(self):
        """Disconnect from the projector."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception as e:
                _LOGGER.debug("Error closing connection: %s", e)
            finally:
                self._writer = None
                self._reader = None

    def _connection_usable(self) -> bool:
        """Whether the cached streams can still carry another command.

        The projector closes an idle ADCP session after ~60s. A peer-side close
        leaves ``_reader``/``_writer`` non-None, so a plain None-check reports a
        dead socket as connected and the next command is written into the void.
        This is best-effort only -- a close we have not observed yet is not
        detectable here, which is why send_command() also retries once.
        """
        if self._reader is None or self._writer is None:
            return False
        if self._reader.at_eof():
            return False
        if self._writer.is_closing():
            return False
        transport = self._writer.transport
        return transport is not None and not transport.is_closing()

    async def _read_line(self) -> str:
        """Read a line from the projector."""
        if not self._reader:
            raise ConnectionError("Not connected")

        try:
            data = await asyncio.wait_for(
                self._reader.readuntil(NEWLINE.encode(ENCODING)),
                timeout=TIMEOUT
            )
            return data.decode(ENCODING).strip()
        except asyncio.TimeoutError:
            # Logged by the caller, which knows whether a retry remains.
            _LOGGER.debug("Timeout reading from projector")
            raise
        except Exception as e:
            _LOGGER.debug("Error reading from projector: %s", e)
            raise

    async def _write_line(self, data: str):
        """Write a line to the projector."""
        if not self._writer:
            raise ConnectionError("Not connected")

        try:
            self._writer.write(f"{data}{NEWLINE}".encode(ENCODING))
            await self._writer.drain()
        except Exception as e:
            _LOGGER.debug("Error writing to projector: %s", e)
            raise

    async def send_command(self, command: str) -> Optional[str]:
        """Send a command and return the response.

        Tries at most twice. The first attempt may reuse a cached session that
        the projector has already closed on us; that failure is expected and
        recoverable, so it is logged at debug and retried on a fresh connection.
        Only a failure on the fresh connection is a real error.
        """
        async with self._lock:
            last_error: Optional[Exception] = None

            for attempt in (1, 2):
                if not self._connection_usable():
                    await self.disconnect()
                    if not await self.connect():
                        return None

                try:
                    await self._write_line(command)
                    _LOGGER.debug("Sent command: %s", command)

                    response = await self._read_line()
                    _LOGGER.debug("Received response: %s", response)

                    # A protocol-level rejection is a real answer, not a
                    # transport failure -- retrying would not change it.
                    if response.startswith("err_"):
                        _LOGGER.error(
                            "Command error: %s for command: %s", response, command
                        )
                        return None

                    return response

                except Exception as e:
                    last_error = e
                    await self.disconnect()
                    if attempt == 1:
                        _LOGGER.debug(
                            "Command %s failed on a reused session (%s); "
                            "reconnecting and retrying",
                            command,
                            e,
                        )

            _LOGGER.error(
                "Error sending command %s after reconnect: %s", command, last_error
            )
            return None

    async def get_power_status(self) -> Optional[str]:
        """Get the current power status."""
        response = await self.send_command("power_status ?")
        if response and response.startswith('"') and response.endswith('"'):
            return response.strip('"')
        return None

    async def set_power(self, state: bool) -> bool:
        """Set power on or off."""
        command = 'power "on"' if state else 'power "off"'
        response = await self.send_command(command)
        return response == "ok"

    async def get_input(self) -> Optional[str]:
        """Get current input source."""
        response = await self.send_command("input ?")
        if response and response.startswith('"') and response.endswith('"'):
            return response.strip('"')
        return None

    async def set_input(self, source: str) -> bool:
        """Set input source."""
        command = f'input "{source}"'
        response = await self.send_command(command)
        return response == "ok"

    async def get_blank_status(self) -> Optional[bool]:
        """Get video muting status."""
        response = await self.send_command("blank ?")
        if response and response.startswith('"') and response.endswith('"'):
            return response.strip('"') == "on"
        return None

    async def set_blank(self, state: bool) -> bool:
        """Set video muting."""
        command = 'blank "on"' if state else 'blank "off"'
        response = await self.send_command(command)
        return response == "ok"

    async def get_picture_mode(self) -> Optional[str]:
        """Get current picture mode."""
        response = await self.send_command("picture_mode ?")
        if response and response.startswith('"') and response.endswith('"'):
            return response.strip('"')
        return None

    async def set_picture_mode(self, mode: str) -> bool:
        """Set picture mode."""
        command = f'picture_mode "{mode}"'
        response = await self.send_command(command)
        return response == "ok"

    async def get_numeric_value(self, parameter: str) -> Optional[int]:
        """Get a numeric parameter value."""
        response = await self.send_command(f"{parameter} ?")
        if response and response.isdigit():
            return int(response)
        # Handle negative numbers
        if response and response.lstrip('-').isdigit():
            return int(response)
        return None

    async def set_numeric_value(self, parameter: str, value: int) -> bool:
        """Set a numeric parameter value."""
        command = f"{parameter} {value}"
        response = await self.send_command(command)
        return response == "ok"

    async def send_key(self, key: str) -> bool:
        """Send a remote control key command."""
        command = f'key "{key}"'
        response = await self.send_command(command)
        return response == "ok"

    async def get_reality_creation(self) -> Optional[str]:
        """Get Reality Creation status."""
        response = await self.send_command("real_cre ?")
        if response and response.startswith('"') and response.endswith('"'):
            return response.strip('"')
        return None

    async def set_reality_creation(self, state: str) -> bool:
        """Set Reality Creation on/off."""
        command = f'real_cre "{state}"'
        response = await self.send_command(command)
        return response == "ok"