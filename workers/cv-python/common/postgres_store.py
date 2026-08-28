import asyncpg

from common.config import settings


async def get_mission_bbox(mission_id: str) -> tuple[str, list[float]] | None:
    """Returns (crs, [minx, miny, maxx, maxy]) for a mission's AOI, or None if the
    mission row doesn't exist (e.g. dev runs against a fixture DB)."""
    conn = await asyncpg.connect(settings.postgres_dsn)
    try:
        row = await conn.fetchrow(
            """
            SELECT ST_XMin(aoi::geometry), ST_YMin(aoi::geometry),
                   ST_XMax(aoi::geometry), ST_YMax(aoi::geometry)
            FROM missions WHERE id = $1
            """,
            mission_id,
        )
    finally:
        await conn.close()
    if row is None or row[0] is None:
        return None
    return "EPSG:4326", [row[0], row[1], row[2], row[3]]


async def publish_products(mission_id: str, products: list[dict]) -> None:
    """Inserts one row per product into the `products` table so mission-svc's
    product catalog (and the web viewer) picks up what ActivityProductGen just
    wrote to object storage. `products` items: kind, uri, checksum, provenance_ref.
    """
    bbox_info = await get_mission_bbox(mission_id)
    crs, bbox = bbox_info if bbox_info else ("EPSG:4326", [0.0, 0.0, 0.0, 0.0])

    conn = await asyncpg.connect(settings.postgres_dsn)
    try:
        await conn.executemany(
            """
            INSERT INTO products (mission_id, kind, uri, crs, bbox, checksum, provenance_ref)
            VALUES ($1, $2, $3, $4, ST_MakeEnvelope($5, $6, $7, $8), $9, $10)
            """,
            [
                (
                    mission_id, p["kind"], p["uri"], crs,
                    bbox[0], bbox[1], bbox[2], bbox[3],
                    p["checksum"], p["provenance_ref"],
                )
                for p in products
            ],
        )
    finally:
        await conn.close()
