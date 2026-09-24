"""Protocol lookup (P9): the county's own documents, split into citable sections, searched locally, and kept
current by a sync that runs only on a good link. Answers are the county's text with its document, section, page
and effective date; nothing is generated. A new document version flags the county config for human review."""
from .base import KnowledgeBase, Section, document_for_page
from .service import KnowledgeService
from .sync import ProtocolSync

__all__ = ["KnowledgeBase", "KnowledgeService", "ProtocolSync", "Section", "document_for_page"]
