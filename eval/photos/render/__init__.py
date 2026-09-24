"""Renderers for the synthetic photo test set (eval/photos/specs.yaml): one registry of device renderers."""
from . import displays, documents, scene
from .degrade import apply as degrade
from .primitives import place

RENDERERS = {**displays.RENDERERS, **documents.RENDERERS, **scene.RENDERERS}

__all__ = ["RENDERERS", "degrade", "place"]
