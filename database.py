import os
import logging
import asyncpg
from typing import Optional, Tuple

logger = logging.getLogger("neverhome-bot")

class Database:
    _pool: Optional[asyncpg.Pool] = None

    @classmethod
    async def get_pool(cls) -> asyncpg.Pool:
        if cls._pool is None:
            dsn = os.getenv("DATABASE_URL")
            try:
                if dsn:
                    cls._pool = await asyncpg.create_pool(dsn)
                else:
                    # Try connecting using standard environment variables (PGHOST, PGUSER, etc.)
                    # Railway often provides these or DATABASE_URL.
                    logger.info("DATABASE_URL not found, attempting to connect using default env variables...")
                    cls._pool = await asyncpg.create_pool()
                logger.info("Database connection pool created.")
            except Exception as e:
                # Capture the specific error for debugging
                raise RuntimeError(f"Failed to create database pool: {e}")
        return cls._pool

    @classmethod
    async def close(cls):
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            logger.info("Database connection pool closed.")

async def get_guild_credentials(guild_id: str) -> Optional[Tuple[str, str, str, str]]:
    """
    Retrieves the universe_id, api_key, owner_id, and universe_id(from key) for a given guild.
    
    Returns:
        Tuple(owner_id, api_key, universe_id)
        Note: The schema has universe_id in both 'api_key' and 'bans' (implicitly needed).
        We need to match the guild -> owner -> api_key -> universe_id.
        
    Flow:
    1. server_configs: guild_id -> ownerId
    2. api_key: ownerId -> encrypted_key (as api_key), universe_id
    
    Returns None if not found or inactive.
    """
    pool = await Database.get_pool()
    query = """
        SELECT 
            sc."ownerId"::text, 
            ak.encrypted_key, 
            ak.universe_id
        FROM server_configs sc
        JOIN api_key ak ON sc."ownerId" = ak."userId"
        WHERE sc.discord_guild_id = $1 AND sc.is_active = true
        LIMIT 1;
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, str(guild_id))
        if row:
            return row['ownerId'], row['encrypted_key'], row['universe_id']
        return None

async def log_ban(owner_id: str, universe_id: str, roblox_user_id: str, reason: str, moderator_id: str = None):
    """
    Logs a ban to the bans table.
    """
    pool = await Database.get_pool()
    # Note: 'userId' in bans table refers to the owner of the config (foreign key to user), 
    # NOT the moderator who performed the ban, based on the schema and relationships provided.
    # The prompt says "log the bans in the db properly".
    # The 'bans' table has: id, userId (FK to user), universe_id, roblox_user_id, reason, banned_at, unbanned_at.
    # It likely tracks bans FOR a specific user's universe. So userId should be the owner's ID.
    
    query = """
        INSERT INTO bans ("userId", "universe_id", "roblox_user_id", "reason")
        VALUES ($1::uuid, $2, $3, $4)
    """
    async with pool.acquire() as conn:
        try:
            await conn.execute(query, owner_id, universe_id, str(roblox_user_id), reason)
        except Exception as e:
            logger.error(f"Failed to log ban to DB: {e}")
