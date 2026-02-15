"""
API endpoints para gestion de contenido y citaciones.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from core.citation_service import (
    get_content_index,
    find_relevant_citations,
    index_creator_posts
)

router = APIRouter(prefix="/citations", tags=["citations"])


class PostInput(BaseModel):
    post_id: Optional[str] = None
    caption: str
    post_type: str = "instagram_post"
    url: Optional[str] = None
    published_date: Optional[str] = None
    likes_count: Optional[int] = None
    comments_count: Optional[int] = None


class IndexPostsRequest(BaseModel):
    creator_id: str
    posts: List[PostInput]


class SearchRequest(BaseModel):
    creator_id: str
    query: str
    max_results: int = 3
    min_relevance: float = 0.4


@router.post("/index")
async def index_posts(request: IndexPostsRequest):
    """Indexa posts de un creador para busqueda."""
    posts = [p.model_dump() for p in request.posts]

    result = await index_creator_posts(
        creator_id=request.creator_id,
        posts=posts,
        save=True
    )

    return result


@router.get("/{creator_id}/stats")
async def get_index_stats(creator_id: str):
    """Obtiene estadisticas del indice de un creador."""
    index = get_content_index(creator_id)
    return index.stats


@router.post("/search")
async def search_content(request: SearchRequest):
    """Busca contenido relevante para una query."""
    citation_context = await find_relevant_citations(
        creator_id=request.creator_id,
        query=request.query,
        max_results=request.max_results,
        min_relevance=request.min_relevance
    )

    return {
        "query": request.query,
        "has_relevant_content": citation_context.has_relevant_content(),
        "citations": [
            {
                "content_type": c.content_type.value,
                "source_id": c.source_id,
                "excerpt": c.excerpt[:200] + "..." if len(c.excerpt) > 200 else c.excerpt,
                "relevance_score": c.relevance_score,
                "natural_reference": c.to_natural_reference()
            }
            for c in citation_context.get_top_citations()
        ]
    }


@router.post("/prompt")
async def get_citation_prompt(request: SearchRequest):
    """Obtiene la seccion de prompt con citas relevantes."""
    citation_context = await find_relevant_citations(
        creator_id=request.creator_id,
        query=request.query,
        max_results=request.max_results,
        min_relevance=request.min_relevance
    )

    if not citation_context.has_relevant_content():
        return {
            "has_content": False,
            "prompt_section": ""
        }

    return {
        "has_content": True,
        "prompt_section": citation_context.to_prompt_context()
    }


@router.get("/{creator_id}/posts-preview")
async def get_posts_preview(creator_id: str, limit: int = 5):
    """Endpoint temporal para ver los posts indexados de un creador."""
    import json
    from pathlib import Path

    data_dir = Path("./data/content_index") / creator_id

    # Try chunks.json first (has full content)
    chunks_path = data_dir / "chunks.json"
    posts_path = data_dir / "posts.json"

    result = {
        "creator_id": creator_id,
        "posts": [],
        "source": None
    }

    if chunks_path.exists():
        with open(chunks_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        result["source"] = "chunks.json"
        result["total_chunks"] = len(chunks)
        result["posts"] = chunks[:limit]
    elif posts_path.exists():
        with open(posts_path, 'r', encoding='utf-8') as f:
            posts = json.load(f)
        result["source"] = "posts.json"
        if isinstance(posts, dict):
            result["total_posts"] = len(posts)
            result["posts"] = list(posts.values())[:limit]
        else:
            result["total_posts"] = len(posts)
            result["posts"] = posts[:limit]
    else:
        raise HTTPException(status_code=404, detail=f"No indexed content found for {creator_id}")

    return result
