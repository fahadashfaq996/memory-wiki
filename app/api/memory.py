from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_memory_fs
from app.schemas.memory import CatResponse, GrepResponse, LsResponse
from app.storage.memory_fs import InvalidPath, MemoryFS, NotAFile

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/ls", response_model=LsResponse)
def ls(
    path: str = Query("/", description="Directory path, e.g. /people"),
    fs: MemoryFS = Depends(get_memory_fs),
) -> LsResponse:
    try:
        return fs.ls(path)
    except InvalidPath as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/cat", response_model=CatResponse)
def cat(
    path: str = Query(..., description="File path, e.g. /people/emily.md"),
    fs: MemoryFS = Depends(get_memory_fs),
) -> CatResponse:
    try:
        return fs.cat(path)
    except InvalidPath as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotAFile as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="memory file not found") from exc


@router.get("/grep", response_model=GrepResponse)
def grep(
    q: str = Query(..., min_length=1, description="Search query (literal or regex)."),
    path: str = Query("/", description="Subtree to search."),
    ignore_case: bool = Query(False),
    regex: bool = Query(False),
    context: int = Query(0, ge=0, le=10, description="Lines of context around each match."),
    fs: MemoryFS = Depends(get_memory_fs),
) -> GrepResponse:
    try:
        matches = fs.grep(q, path, ignore_case=ignore_case, regex=regex, context=context)
    except InvalidPath as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except re.error as exc:
        raise HTTPException(status_code=400, detail=f"invalid regex: {exc}") from exc
    return GrepResponse(query=q, path=path, match_count=len(matches), matches=matches)
