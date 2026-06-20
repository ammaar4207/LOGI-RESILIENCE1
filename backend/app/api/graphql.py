import json
import logging
from typing import List, Optional
import strawberry
from strawberry.fastapi import GraphQLRouter
from fastapi import Request
from strawberry.types import Info
from app.db.neo4j import db
from app.services.scraper import DISRUPTION_KEYWORDS
from app.core.auth import get_current_user, UserProfile
from fastapi.security import HTTPAuthorizationCredentials
import httpx

logger = logging.getLogger(__name__)


@strawberry.type
class LogisticsNode:
    id: str
    name: str
    type: str
    lat: float
    lon: float
    capacity: int


@strawberry.type
class GlobalNewsEvent:
    url: str
    title: str
    source: str
    tone: float


@strawberry.type
class Query:
    @strawberry.field
    async def get_nodes(self, info: Info, type: Optional[str] = None) -> List[LogisticsNode]:
        """Fetch all logistics nodes, optionally filtered by type (e.g. port, warehouse)."""
        user = info.context.get("user")
        if not user:
            raise Exception("Authentication required to execute this query.")

        nodes = []
        async with db.get_session() as session:
            query = "MATCH (n:Port) RETURN n"  # Use Port since standard seed uses Port labels
            if type:
                query = f"MATCH (n:Port {{type: '{type}'}}) RETURN n"
            
            result = await session.run(query)
            records = await result.data()
            
            for record in records:
                n = record["n"]
                nodes.append(LogisticsNode(
                    id=n.get("id", ""),
                    name=n.get("name", ""),
                    type=n.get("type", "port"),
                    lat=n.get("lat", 0.0),
                    lon=n.get("lon", 0.0),
                    capacity=n.get("capacity_teu", 0)
                ))
        return nodes

    @strawberry.field
    async def get_latest_global_events(self, info: Info) -> List[GlobalNewsEvent]:
        """Fetch real-time global news events via GDELT Project Integration."""
        user = info.context.get("user")
        if not user:
            raise Exception("Authentication required to execute this query.")

        events = []
        query_url = "https://api.gdeltproject.org/api/v2/doc/doc?query=(strike OR hurricane OR blockade OR congestion)&mode=ArtList&maxrecords=10&format=json"
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(query_url)
                response.raise_for_status()
                data = response.json()
                articles = data.get("articles", [])
                
                for article in articles:
                    events.append(GlobalNewsEvent(
                        url=article.get("url", ""),
                        title=article.get("title", ""),
                        source=article.get("domain", ""),
                        tone=float(article.get("tone", 0.0))
                    ))
        except Exception as e:
            logger.error(f"Failed to fetch GDELT data: {e}")
            
        return events


async def get_context(request: Request) -> dict:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return {"user": None}
    try:
        parts = auth_header.split(" ")
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return {"user": None}
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=parts[1])
        user = await get_current_user(creds)
        return {"user": user}
    except Exception as e:
        logger.debug("GraphQL Auth failed: %s", e)
        return {"user": None}


schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema, context_getter=get_context)
