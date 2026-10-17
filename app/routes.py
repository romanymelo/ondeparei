from fastapi import APIRouter, Request

from app.catalog import Catalog

router = APIRouter()


def get_catalog(request: Request) -> Catalog:
    return request.app.state.catalog
