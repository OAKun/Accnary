"""Service layer: the facade the UI talks to (never raw KDBX access)."""

from .catalog_service import CatalogService

__all__ = ["CatalogService"]
