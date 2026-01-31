"""Redis client for vector search, caching, and user profiles"""

import os
from typing import Optional, List
import redis.asyncio as redis
from redis.commands.search.field import TextField, TagField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType

_redis_client: Optional[redis.Redis] = None

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
EMBEDDING_DIM = 768  # Gemini embedding dimension


async def init_redis():
    """Initialize Redis connection and create indexes"""
    global _redis_client
    _redis_client = redis.from_url(REDIS_URL, decode_responses=True)

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
    except redis.ResponseError as e:
        if "Index already exists" not in str(e):
            raise

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
    except redis.ResponseError as e:
        if "Index already exists" not in str(e):
            raise


async def get_redis() -> redis.Redis:
    """Get Redis client instance"""
    if _redis_client is None:
        await init_redis()
    return _redis_client


async def cache_embedding(item_id: str, embedding: List[float], text: str, topics: List[str], domain: str):
    """Cache an item embedding in Redis"""
    r = await get_redis()
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
    key = f"item:{item_id}"

    data = await r.hget(key, "embedding")
    if data:
        return list(data)
    return None


async def cache_url_preview(url: str, preview: dict):
    """Cache a URL preview"""
    r = await get_redis()
    key = f"preview:{url}"
    await r.json().set(key, "$", preview)
    await r.expire(key, 900)  # 15 min TTL


async def get_cached_preview(url: str) -> Optional[dict]:
    """Get a cached URL preview"""
    r = await get_redis()
    key = f"preview:{url}"
    return await r.json().get(key)
