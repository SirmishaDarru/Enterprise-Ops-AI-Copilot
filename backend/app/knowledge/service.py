"""Bounded extraction, versioned chunks, and deterministic test embeddings."""
import hashlib
import io
import math
import re
import uuid
from functools import lru_cache

from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.knowledge.models import Chunk, Document, EmbeddingCache

MAX_BYTES = 2 * 1024 * 1024
MAX_TEXT = 100_000
MAX_PAGES = 40
MAX_CHUNKS = 100


def extract(filename: str, raw: bytes) -> list[tuple[int | None, str]]:
    suffix = filename.rsplit('.', 1)[-1].lower()
    if suffix not in ('txt', 'md', 'pdf') or len(raw) > MAX_BYTES or not raw:
        raise ApiError(400, 'INVALID_DOCUMENT', 'Use a nonempty .txt, .md, or .pdf up to 2 MiB')
    if suffix == 'pdf':
        try:
            reader = PdfReader(io.BytesIO(raw), strict=True)
            if reader.is_encrypted or len(reader.pages) > MAX_PAGES:
                raise ApiError(400, 'INVALID_DOCUMENT', 'Encrypted or over 40-page PDF')
            pages = [(i + 1, page.extract_text() or '') for i, page in enumerate(reader.pages)]
        except ApiError:
            raise
        except Exception:
            raise ApiError(400, 'INVALID_DOCUMENT', 'Could not parse PDF') from None
    else:
        try:
            pages = [(None, raw.decode('utf-8-sig'))]
        except UnicodeDecodeError:
            raise ApiError(400, 'INVALID_DOCUMENT', 'Text must be UTF-8') from None
    if not any(content.strip() for _, content in pages):
        raise ApiError(400, 'INVALID_DOCUMENT', 'No extractable text; scanned PDFs need OCR')
    if sum(len(content) for _, content in pages) > MAX_TEXT:
        raise ApiError(400, 'INVALID_DOCUMENT', 'Extracted text exceeds 100,000 characters')
    return pages


def split_pages(pages: list[tuple[int | None, str]]) -> list[tuple[int | None, str]]:
    chunks: list[tuple[int | None, str]] = []
    for page, content in pages:
        words = re.findall(r'\S+', content)
        for start in range(0, len(words), 150):
            # No overlap: lexical matches and citations never duplicate boundary passages.
            part = ' '.join(words[start:start + 150])
            if part:
                chunks.append((page, part))
    if not chunks or len(chunks) > MAX_CHUNKS:
        raise ApiError(400, 'INVALID_DOCUMENT', 'Document exceeds 100 searchable passages')
    return chunks


def model_id() -> str:
    settings = get_settings()
    return 'mock-hash-v1' if settings.embedding_mode == 'mock' else settings.embedding_model


@lru_cache(maxsize=2)
def _local_model(name: str):
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=name)


def embed(text: str, query: bool = False) -> list[float]:
    settings = get_settings()
    if settings.embedding_mode == 'local':
        try:
            vector = next(iter(_local_model(settings.embedding_model).embed(
                [('query: ' if query else 'passage: ') + text])))
            return vector.tolist()
        except Exception:
            raise ApiError(503, 'EMBEDDING_UNAVAILABLE',
                           'Local embedding model unavailable; check model download/cache') from None
    values = [0.0] * 384
    for word in re.findall(r'[a-z0-9]+', text.lower()):
        digest = hashlib.sha256(word.encode()).digest()
        values[int.from_bytes(digest[:4], 'big') % 384] += 1.0
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def index_document(db: Session, doc: Document, pages: list[tuple[int | None, str]]) -> int:
    pieces = split_pages(pages)
    prepared = []
    for ordinal, (page, content) in enumerate(pieces):
        digest = hashlib.sha256(content.encode()).hexdigest()
        cached = db.scalar(select(EmbeddingCache).where(
            EmbeddingCache.model_id == model_id(), EmbeddingCache.content_sha256 == digest))
        vector = cached.embedding if cached else embed(content)
        if cached is None:
            db.execute(insert(EmbeddingCache).values(id=uuid.uuid4(), model_id=model_id(),
                content_sha256=digest, embedding=vector).on_conflict_do_nothing(
                index_elements=['model_id', 'content_sha256']))
        prepared.append(Chunk(id=uuid.uuid5(doc.id, f'{doc.version}:{ordinal}'),
            document_id=doc.id, ordinal=ordinal, page_number=page, content=content,
            content_sha256=digest, embedding=vector))
    db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    db.add_all(prepared)
    doc.embedding_model = model_id()
    return len(prepared)
