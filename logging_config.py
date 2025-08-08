import asyncio
import logging
from typing import Optional, Iterable


def configure_logging() -> logging.Logger:
    """Configure logging to route records into Discord's #logs channel only.

    We attach a single async handler that buffers until a Discord channel is
    bound via `bind_discord_log_channel`. No file or stdout handlers to avoid
    duplicates.
    """
    logger = logging.getLogger("neverhome-bot")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = _get_or_create_discord_handler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False

    return logger


class DiscordLogHandler(logging.Handler):
    """Async handler that sends log records to a Discord channel.

    Messages are queued and delivered by a background task when a channel is bound.
    """

    def __init__(self) -> None:
        super().__init__()
        self._queue: "asyncio.Queue[str]" = asyncio.Queue(maxsize=1000)
        self._channel = None  # discord.abc.Messageable
        self._task: Optional[asyncio.Task] = None

    def set_channel(self, channel, loop: asyncio.AbstractEventLoop) -> None:
        self._channel = channel
        if self._task is None or self._task.done():
            self._task = loop.create_task(self._runner())

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = f"{record.levelname} {record.name} - {record.getMessage()}"

        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self._enqueue_nowait, message)
        except RuntimeError:
            self._enqueue_nowait(message)

    def _enqueue_nowait(self, message: str) -> None:
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            try:
                _ = self._queue.get_nowait()
            except Exception:
                pass
            try:
                self._queue.put_nowait(message)
            except Exception:
                pass

    async def _runner(self) -> None:
        while True:
            message = await self._queue.get()
            if not self._channel:
                await asyncio.sleep(1)
                self._enqueue_nowait(message)
                continue
            try:
                for chunk in _chunk_for_discord(message):
                    await self._channel.send(chunk)
            except Exception:
                await asyncio.sleep(1)


def _chunk_for_discord(message: str, max_len: int = 1900) -> Iterable[str]:
    if len(message) <= max_len:
        return [message]
    chunks = []
    start = 0
    while start < len(message):
        end = min(start + max_len, len(message))
        chunks.append(message[start:end])
        start = end
    return chunks


_DISCORD_HANDLER: Optional[DiscordLogHandler] = None


def _get_or_create_discord_handler() -> DiscordLogHandler:
    global _DISCORD_HANDLER
    if _DISCORD_HANDLER is None:
        _DISCORD_HANDLER = DiscordLogHandler()
    return _DISCORD_HANDLER


def bind_discord_log_channel(channel, loop: asyncio.AbstractEventLoop) -> None:
    handler = _get_or_create_discord_handler()
    handler.set_channel(channel, loop)
