"""Redis client for vector search, caching, and user profiles"""

import os
from typing import Optional, List
import redis.asyncio as redis
from redis.commands.search.field import TextField, TagField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType

_redis_client: Optional[redis.Redis] = None
_redis_available: bool = False

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
EMBEDDING_DIM = 768  # Gemini embedding dimension


async def init_redis():
    """Initialize Redis connection and create indexes"""
    global _redis_client, _redis_available
    try:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        # Test connection
        await _redis_client.ping()
        _redis_available = True

        # Create vector index for item embeddings (if not exists)
        try:
            await _redis_client.ft("item_embeddings").create_index(
                fields=[
                    VectorField(
                        "embedding",
                        "HNSW",
                        {
                            "TYPE": "FLOAT32",
                            "DIM": EMBEDDING_DIM,
                            "DISTANCE_METRIC": "COSINE"
                        }
                    ),
                    TagField("topics"),
                    TagField("domain"),
                    TextField("text")
                ],
                definition=IndexDefinition(
                    prefix=["item:"],
                    index_type=IndexType.HASH
                )
            )
        except Exception as e:
            if "Index already exists" not in str(e):
                print(f"Warning: Could not create item_embeddings index: {e}")

        # Create vector index for user embeddings
        try:
            await _redis_client.ft("user_embeddings").create_index(
                fields=[
                    VectorField(
                        "text_vector",
                        "HNSW",
                        {
                            "TYPE": "FLOAT32",
                            "DIM": EMBEDDING_DIM,
                            "DISTANCE_METRIC": "COSINE"
                        }
                    ),
                ],
                definition=IndexDefinition(
                    prefix=["user_vec:"],
                    index_type=IndexType.HASH
                )
            )
        except Exception as e:
            if "Index already exists" not in str(e):
                print(f"Warning: Could not create user_embeddings index: {e}")

    except Exception as e:
        print(f"Redis not available: {e}")
        _redis_available = False


async def get_redis() -> Optional[redis.Redis]:
    """Get Redis client instance (may be None if Redis unavailable)"""
    if not _redis_available:
        return None
    return _redis_client


def is_redis_available() -> bool:
    """Check if Redis is available"""
    return _redis_available


async def cache_embedding(item_id: str, embedding: List[float], text: str, topics: List[str], domain: str):
    """Cache an item embedding in Redis"""
    r = await get_redis()
    if not r:
        return
    key = f"item:{item_id}"

    await r.hset(key, mapping={
        "embedding": bytes(embedding),
        "text": text,
        "topics": ",".join(topics),
        "domain": domain
    })
    await r.expire(key, 3600)  # 1 hour TTL


async def get_cached_embedding(item_id: str) -> Optional[List[float]]:
    """Get a cached embedding from Redis"""
    r = await get_redis()
    if not r:
        return None
    key = f"item:{item_id}"

    data = await r.hget(key, "embedding")
    if data:
        return list(data)
    return None


async def cache_url_preview(url: str, preview: dict):
    """Cache a URL preview"""
    r = await get_redis()
    if not r:
        return
    key = f"preview:{url}"
    await r.json().set(key, "$", preview)
    await r.expire(key, 900)  # 15 min TTL


async def get_cached_preview(url: str) -> Optional[dict]:
    """Get a cached URL preview"""
    r = await get_redis()
    if not r:
        return None
    key = f"preview:{url}"
    return await r.json().get(key)


# Authenticity caching functions

async def cache_authenticity_result(item_id: str, result: dict, ttl: int = 3600):
    """Cache an authenticity check result"""
    r = await get_redis()
    if not r:
        return
    key = f"authenticity:{item_id}"
    await r.json().set(key, "$", result)
    await r.expire(key, ttl)


async def get_cached_authenticity(item_id: str) -> Optional[dict]:
    """Get a cached authenticity result"""
    r = await get_redis()
    if not r:
        return None
    key = f"authenticity:{item_id}"
    try:
        return await r.json().get(key)
    except:
        return None


async def mark_authenticity_pending(item_id: str):
    """Mark an item as having a pending authenticity check"""
    r = await get_redis()
    if not r:
        return
    key = f"authenticity:pending:{item_id}"
    await r.setex(key, 300, "pending")  # 5 min TTL


async def clear_authenticity_pending(item_id: str):
    """Clear the pending marker for an item"""
    r = await get_redis()
    if not r:
        return
    key = f"authenticity:pending:{item_id}"
    await r.delete(key)


async def get_pending_authenticity_checks() -> List[str]:
    """Get list of item IDs with pending authenticity checks"""
    r = await get_redis()
    if not r:
        return []
    keys = await r.keys("authenticity:pending:*")
    return [k.split(":")[-1] for k in keys]
