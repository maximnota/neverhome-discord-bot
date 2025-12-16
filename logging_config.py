import asyncio
import logging
from typing import Optional, Iterable, Dict, Any

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

    Messages are queued and delivered by a background task.
    """

    def __init__(self) -> None:
        super().__init__()
        self._queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=1000)
        self._channels: Dict[int, Any] = {} # guild_id -> channel
        self._task: Optional[asyncio.Task] = None

    def add_channel(self, guild_id: int, channel, loop: asyncio.AbstractEventLoop) -> None:
        self._channels[guild_id] = channel
        if self._task is None or self._task.done():
            self._task = loop.create_task(self._runner())

    def remove_channel(self, guild_id: int) -> None:
        if guild_id in self._channels:
            del self._channels[guild_id]

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = f"{record.levelname} {record.name} - {record.getMessage()}"
        
        # Capture guild_id from the record if present
        guild_id = getattr(record, 'guild_id', None)

        payload = {
            'message': message,
            'guild_id': guild_id
        }

        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self._enqueue_nowait, payload)
        except RuntimeError:
            self._enqueue_nowait(payload)

    def _enqueue_nowait(self, payload: Dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                _ = self._queue.get_nowait()
            except Exception:
                pass
            try:
                self._queue.put_nowait(payload)
            except Exception:
                pass

    async def _runner(self) -> None:
        while True:
            item = await self._queue.get()
            message = item['message']
            guild_id = item['guild_id']
            
            targets = []
            
            if guild_id:
                # If specific guild targeted, only send there
                if guild_id in self._channels:
                    targets.append(self._channels[guild_id])
            else:
                # If no guild_id, maybe broadcast? Or just log to all?
                # Probably better to NOT spam all servers with system logs.
                # Just ignore or maybe a specific "system" channel if we had one.
                # For now, we only log guild-specific actions to discord.
                pass

            for channel in targets:
                try:
                    for chunk in _chunk_for_discord(message):
                        # channel must be an async messageable
                        await channel.send(chunk)
                except Exception:
                    # Ignore send errors (permission, missing, etc)
                    pass
            
            # Small throttle if needed, but we rely on queue
            await asyncio.sleep(0.01)

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

def bind_discord_log_channel(guild_id: int, channel, loop: asyncio.AbstractEventLoop) -> None:
    handler = _get_or_create_discord_handler()
    handler.add_channel(guild_id, channel, loop)
