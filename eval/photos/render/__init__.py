"""Renderers for the synthetic photo test set (eval/photos/specs.yaml): one registry of device renderers."""
from . import apps, displays, documents, scene, wearables
from .degrade import apply as degrade
from .primitives import place

RENDERERS = {**displays.RENDERERS, **documents.RENDERERS, **scene.RENDERERS, **wearables.RENDERERS,
             **apps.RENDERERS}

__all__ = ["RENDERERS", "degrade", "place"]
