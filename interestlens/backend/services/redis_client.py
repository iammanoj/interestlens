"""Redis client for vector search, caching, and user profiles"""

import os
import json
from typing import Optional, List, Any
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


# JSON-like helpers using regular Redis strings (no RedisJSON module required)

async def json_get(key: str, path: str = "$") -> Optional[Any]:
    """Get a JSON object from Redis (stored as string)"""
    r = await get_redis()
    if not r:
        return None
    try:
        data = await r.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception:
        return None


async def json_set(key: str, path: str, value: Any) -> bool:
    """Set a JSON object in Redis (stored as string). Path is ignored (always replaces full value)."""
    r = await get_redis()
    if not r:
        return False
    try:
        await r.set(key, json.dumps(value))
        return True
    except Exception:
        return False


async def json_set_field(key: str, field: str, value: Any) -> bool:
    """Update a single field in a JSON object stored in Redis"""
    r = await get_redis()
    if not r:
        return False
    try:
        data = await r.get(key)
        if data:
            obj = json.loads(data)
            obj[field] = value
            await r.set(key, json.dumps(obj))
            return True
        return False
    except Exception:
        return False


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
    await r.setex(key, 900, json.dumps(preview))  # 15 min TTL


async def get_cached_preview(url: str) -> Optional[dict]:
    """Get a cached URL preview"""
    r = await get_redis()
    if not r:
        return None
    key = f"preview:{url}"
    data = await r.get(key)
    if data:
        return json.loads(data)
    return None


# Authenticity caching functions

async def cache_authenticity_result(item_id: str, result: dict, ttl: int = 3600):
    """Cache an authenticity check result"""
    r = await get_redis()
    if not r:
        return
    key = f"authenticity:{item_id}"
    await r.setex(key, ttl, json.dumps(result))


async def get_cached_authenticity(item_id: str) -> Optional[dict]:
    """Get a cached authenticity result"""
    r = await get_redis()
    if not r:
        return None
    key = f"authenticity:{item_id}"
    try:
        data = await r.get(key)
        if data:
            return json.loads(data)
        return None
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


# Article content caching functions

async def cache_article_content(url: str, content: dict, ttl: int = 3600):
    """
    Cache article content extracted from a URL.

    Args:
        url: The article URL (used as cache key)
        content: Article content dict (title, full_text, author, etc.)
        ttl: Time to live in seconds (default 1 hour)
    """
    r = await get_redis()
    if not r:
        return
    # Use hash of URL to handle long URLs
    import hashlib
    url_hash = hashlib.md5(url.encode()).hexdigest()
    key = f"article:{url_hash}"

    # Store with original URL for debugging
    content["_cached_url"] = url
    await r.setex(key, ttl, json.dumps(content))
    print(f"[CACHE] Stored article content for: {url[:50]}...")


async def get_cached_article_content(url: str) -> Optional[dict]:
    """
    Get cached article content for a URL.

    Args:
        url: The article URL

    Returns:
        Cached article content dict or None if not cached
    """
    r = await get_redis()
    if not r:
        return None

    import hashlib
    url_hash = hashlib.md5(url.encode()).hexdigest()
    key = f"article:{url_hash}"

    try:
        data = await r.get(key)
        if data:
            print(f"[CACHE HIT] Found cached article for: {url[:50]}...")
            return json.loads(data)
        return None
    except Exception:
        return None


async def get_article_cache_stats() -> dict:
    """Get statistics about the article cache."""
    r = await get_redis()
    if not r:
        return {"available": False}

    try:
        keys = await r.keys("article:*")
        return {
            "available": True,
            "cached_articles": len(keys)
        }
    except Exception:
        return {"available": True, "cached_articles": 0}
