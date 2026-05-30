from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from app.config import get_settings

settings = get_settings()

_client: AsyncQdrantClient | None = None

VECTOR_SIZE = 768  # SigLIP output dimension


def get_qdrant_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        cloud_url = settings.qdrant_url or settings.qdrant_cluster_endpoint
        if cloud_url:
            _client = AsyncQdrantClient(
                url=cloud_url,
                api_key=settings.qdrant_api_key,
            )
        else:
            _client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
            )
    return _client


async def ensure_collection() -> None:
    client = get_qdrant_client()
    existing = await client.get_collections()
    names = [c.name for c in existing.collections]
    if settings.qdrant_collection not in names:
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    # Payload indexes required for range/match filters in query_points
    await client.create_payload_index(
        collection_name=settings.qdrant_collection,
        field_name="received_at",
        field_schema=PayloadSchemaType.FLOAT,
    )
    await client.create_payload_index(
        collection_name=settings.qdrant_collection,
        field_name="status",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    await client.create_payload_index(
        collection_name=settings.qdrant_collection,
        field_name="wholesaler_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    await client.create_payload_index(
        collection_name=settings.qdrant_collection,
        field_name="source_platform",
        field_schema=PayloadSchemaType.KEYWORD,
    )


async def close_qdrant_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
