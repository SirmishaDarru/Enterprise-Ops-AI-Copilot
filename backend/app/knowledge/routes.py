"""All corpus reads filter service membership and document grants in SQL."""
import hashlib
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from app.auth.models import ServiceMembership, User
from app.auth.security import current_user, require_roles
from app.core.access import require_service
from app.core.db import get_db
from app.core.errors import ApiError
from app.knowledge.models import Chunk, Document, DocumentGrant
from app.knowledge.service import MAX_BYTES, embed, extract, index_document, model_id, split_pages

router = APIRouter(prefix='/knowledge', tags=['knowledge'])
DB = Annotated[Session, Depends(get_db)]
USER = Annotated[User, Depends(current_user)]
ADMIN = Annotated[User, Depends(require_roles('admin'))]


def visible(user: User):
    if user.role == 'admin':
        return True
    return (
        exists(select(ServiceMembership.id).where(
            ServiceMembership.user_id == user.id,
            ServiceMembership.service_id == Document.service_id))
        & exists(select(DocumentGrant.id).where(
            DocumentGrant.document_id == Document.id, DocumentGrant.role == user.role))
    )


def serialize(doc: Document, roles: list[str] | None = None) -> dict:
    result = dict(id=str(doc.id), service_id=str(doc.service_id), title=doc.title, kind=doc.kind,
                  filename=doc.filename, version=doc.version, embedding_model=doc.embedding_model,
                  updated_at=doc.updated_at.isoformat() if doc.updated_at else None)
    if roles is not None:
        result['allowed_roles'] = roles
    return result


def roles_from(raw: str) -> list[str]:
    roles = sorted(set(role.strip() for role in raw.split(',') if role.strip()))
    if not roles or any(role not in ('viewer', 'responder', 'approver', 'admin') for role in roles):
        raise ApiError(400, 'INVALID_GRANTS', 'Choose one or more valid roles')
    return roles


def allowed_document(db: Session, user: User, document_id: uuid.UUID) -> Document:
    doc = db.scalar(select(Document).where(Document.id == document_id, visible(user)))
    if not doc:
        raise ApiError(404, 'NOT_FOUND', 'Document not found')
    return doc


def grant_roles(db: Session, doc: Document, roles: list[str]):
    db.execute(delete(DocumentGrant).where(DocumentGrant.document_id == doc.id))
    db.add_all(DocumentGrant(document_id=doc.id, role=role) for role in roles)


def doc_roles(db: Session, doc: Document) -> list[str]:
    return list(db.scalars(select(DocumentGrant.role).where(DocumentGrant.document_id == doc.id)))


@router.get('/documents')
def documents(db: DB, user: USER):
    docs = db.scalars(select(Document).where(visible(user)).order_by(Document.updated_at.desc(),
                      Document.id.desc()).limit(100)).all()
    return {'items': [serialize(doc, doc_roles(db, doc)) for doc in docs]}


@router.get('/documents/{document_id}')
def document(document_id: uuid.UUID, db: DB, user: USER):
    doc = allowed_document(db, user, document_id)
    return serialize(doc, doc_roles(db, doc))


@router.post('/documents', status_code=201)
async def upload(db: DB, user: ADMIN, title: Annotated[str, Form(min_length=1, max_length=200)],
                 kind: Annotated[str, Form()], service_id: Annotated[uuid.UUID, Form()],
                 allowed_roles: Annotated[str, Form()], file: Annotated[UploadFile, File()]):
    if kind not in ('runbook', 'service_doc', 'postmortem'):
        raise ApiError(400, 'INVALID_KIND', 'Choose runbook, service_doc, or postmortem')
    require_service(db, user, service_id)
    roles = roles_from(allowed_roles)
    raw = await file.read(MAX_BYTES + 1)
    filename = (file.filename or '').split('/')[-1].split('\\')[-1]
    pages = extract(filename, raw)
    split_pages(pages)
    doc = Document(service_id=service_id, title=title.strip(), kind=kind, filename=filename,
                   extracted_text='\f'.join(page for _, page in pages),
                   sha256=hashlib.sha256(raw).hexdigest(), embedding_model=model_id(), version=1)
    db.add(doc)
    db.flush()
    grant_roles(db, doc, roles)
    count = index_document(db, doc, pages)
    db.commit()
    db.refresh(doc)
    return {**serialize(doc, roles), 'chunk_count': count}


@router.put('/documents/{document_id}')
async def replace(document_id: uuid.UUID, db: DB, user: ADMIN,
                  title: Annotated[str, Form(min_length=1, max_length=200)],
                  kind: Annotated[str, Form()], allowed_roles: Annotated[str, Form()],
                  file: Annotated[UploadFile, File()]):
    doc = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if doc is None:
        raise ApiError(404, 'NOT_FOUND', 'Document not found')
    if kind not in ('runbook', 'service_doc', 'postmortem'):
        raise ApiError(400, 'INVALID_KIND', 'Invalid document kind')
    roles = roles_from(allowed_roles)
    raw = await file.read(MAX_BYTES + 1)
    filename = (file.filename or '').split('/')[-1].split('\\')[-1]
    pages = extract(filename, raw)
    split_pages(pages)
    changed = doc.sha256 != hashlib.sha256(raw).hexdigest() or doc.embedding_model != model_id()
    doc.title = title.strip()
    doc.kind = kind
    doc.filename = filename
    grant_roles(db, doc, roles)
    if changed:
        doc.version += 1
        doc.sha256 = hashlib.sha256(raw).hexdigest()
        doc.extracted_text = '\f'.join(page for _, page in pages)
        index_document(db, doc, pages)
    db.commit()
    db.refresh(doc)
    return serialize(doc, roles)


@router.post('/documents/{document_id}/reindex')
def reindex(document_id: uuid.UUID, db: DB, user: ADMIN):
    doc = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if doc is None:
        raise ApiError(404, 'NOT_FOUND', 'Document not found')
    pages = [(i + 1 if doc.filename.lower().endswith('.pdf') else None, page)
             for i, page in enumerate(doc.extracted_text.split('\f'))]
    doc.version += 1
    count = index_document(db, doc, pages)
    db.commit()
    db.refresh(doc)
    return {**serialize(doc, doc_roles(db, doc)), 'chunk_count': count}


@router.delete('/documents/{document_id}')
def remove(document_id: uuid.UUID, db: DB, user: ADMIN):
    doc = db.get(Document, document_id)
    if doc is None:
        raise ApiError(404, 'NOT_FOUND', 'Document not found')
    db.delete(doc)
    db.commit()
    return {'deleted': True}


@router.get('/sources/{chunk_id}')
def source(chunk_id: uuid.UUID, db: DB, user: USER):
    row = db.execute(select(Chunk, Document).join(Document, Chunk.document_id == Document.id)
                     .where(Chunk.id == chunk_id, visible(user))).first()
    if row is None:
        raise ApiError(404, 'NOT_FOUND', 'Source not found')
    chunk, doc = row
    return {'id': str(chunk.id), 'document_id': str(doc.id), 'title': doc.title,
            'filename': doc.filename, 'page_number': chunk.page_number,
            'ordinal': chunk.ordinal, 'version': doc.version, 'content': chunk.content}


@router.get('/search')
def search(db: DB, user: USER, q: Annotated[str, Query(min_length=2, max_length=300)],
           service_id: uuid.UUID | None = None):
    if not re.search(r'[a-zA-Z0-9]', q):
        raise ApiError(400, 'INVALID_QUERY', 'Enter searchable words')
    if service_id is not None:
        require_service(db, user, service_id)
    base = select(Chunk.id).join(Document, Chunk.document_id == Document.id).where(
        visible(user), Document.embedding_model == model_id())
    if service_id:
        base = base.where(Document.service_id == service_id)
    vector = embed(q, query=True)
    distance = Chunk.embedding.cosine_distance(vector)
    lex_query = func.websearch_to_tsquery('english', q)
    rank = func.ts_rank_cd(func.to_tsvector('english', Chunk.content), lex_query)
    vector_ids = list(db.scalars(base.order_by(distance, Chunk.id).limit(30)))
    lexical_ids = list(db.scalars(base.where(func.to_tsvector('english', Chunk.content).op('@@')(lex_query))
                          .order_by(rank.desc(), Chunk.id).limit(30)))
    scores: dict[uuid.UUID, float] = {}
    for ids in (vector_ids, lexical_ids):
        for position, identifier in enumerate(ids):
            scores[identifier] = scores.get(identifier, 0) + 1 / (60 + position + 1)
    top = sorted(scores, key=lambda identifier: (-scores[identifier], str(identifier)))[:10]
    if not top:
        return {'items': [], 'embedding_model': model_id()}
    # Repeat ACL on final fetch to keep source material scoped even if candidate logic changes.
    rows = db.execute(select(Chunk, Document).join(Document, Chunk.document_id == Document.id)
                      .where(Chunk.id.in_(top), visible(user))).all()
    by_id = {chunk.id: (chunk, doc) for chunk, doc in rows}
    return {'embedding_model': model_id(), 'items': [
        {'source_id': str(identifier), 'document_id': str(by_id[identifier][1].id),
         'title': by_id[identifier][1].title, 'kind': by_id[identifier][1].kind,
         'service_id': str(by_id[identifier][1].service_id),
         'filename': by_id[identifier][1].filename,
         'page_number': by_id[identifier][0].page_number,
         'ordinal': by_id[identifier][0].ordinal,
         'version': by_id[identifier][1].version,
         'snippet': by_id[identifier][0].content[:600],
         'score': round(scores[identifier], 5)} for identifier in top if identifier in by_id]}


@router.post('/demo', status_code=201)
def demo_documents(db: DB, user: ADMIN):
    """Idempotent synthetic corpus
    operational fixture must have been replayed first."""
    from app.telemetry.demo import stable
    from app.telemetry.models import Service

    fixtures = [
        ('checkout-pool', 'checkout-api', 'Checkout connection pool runbook', 'runbook',
         'When checkout-api logs Database connection pool exhausted and HTTP 500, inspect active connections, waiting queries, and pool occupancy in payments-db. Reduce concurrency if safe and verify checkout error rate returns below the alert threshold. A deployment marker near the spike is only a correlation. Escalate to the on-call responder before changing pool limits.',
         ['viewer', 'responder', 'approver', 'admin']),
        ('checkout-postmortem', 'checkout-api', 'Checkout deployment review', 'postmortem',
         'A synthetic v2 deployment marker appeared before elevated checkout latency. The evidence does not establish that deployment as root cause. The contemporaneous logs report connection pool exhaustion. Compare request volume and datastore connection saturation before deciding whether to roll back.',
         ['viewer', 'responder', 'approver', 'admin']),
        ('payments-restricted', 'payments-db', 'Payments datastore private runbook', 'runbook',
         'For payments-db connection saturation, the approver may review restricted rotation procedures and protected datastore access. This fixture contains no real credentials. Coordinate any production access change through an approved workflow.',
         ['approver', 'admin']),
    ]
    created = 0
    for key, name, title, kind, content, roles in fixtures:
        service_id = stable('service', name)
        if db.get(Service, service_id) is None:
            raise ApiError(409, 'DEMO_NOT_READY', 'Replay the Stage 2 synthetic fixture first')
        identifier = uuid.uuid5(uuid.NAMESPACE_DNS, f'ops-copilot-stage3:{key}')
        if db.get(Document, identifier):
            continue
        raw = content.encode()
        doc = Document(id=identifier, service_id=service_id, title=title, kind=kind,
                       filename=f'{key}.txt', extracted_text=content,
                       sha256=hashlib.sha256(raw).hexdigest(), version=1,
                       embedding_model=model_id())
        db.add(doc)
        db.flush()
        grant_roles(db, doc, roles)
        index_document(db, doc, [(None, content)])
        created += 1
    db.commit()
    return {'created': created, 'total': len(fixtures), 'synthetic': True}


@router.post('/live-demo/runbook', status_code=201)
def live_runbook(db: DB, user: ADMIN):
    """A static guide for the observed local service; no synthetic fixture prerequisite."""
    from app.telemetry.live import SERVICE_ID
    from app.telemetry.models import Service

    if db.get(Service, SERVICE_ID) is None:
        raise ApiError(503, 'LIVE_DEMO_NOT_READY', 'Wait for the live collector to register its service')
    identifier = uuid.uuid5(uuid.NAMESPACE_DNS, 'ops-copilot:live-checkout-runbook')
    existing = db.scalar(select(Document).where(Document.id == identifier).with_for_update())
    if existing:
        if existing.embedding_model != model_id():
            existing.version += 1
            index_document(db, existing, [(None, existing.extracted_text)])
            db.commit()
            return {'created': False, 'reindexed': True, 'document_id': str(identifier)}
        return {'created': False, 'reindexed': False, 'document_id': str(identifier)}
    content = ('When live-checkout-demo returns HTTP 503 and reports Database connection pool '
        'exhausted, inspect current error rate, active connections and waiting queries. '
        'Compare observed traffic before and after the controlled failure. Restoring local '
        'demo traffic stops new 503 responses; it does not establish the root cause of a real outage.')
    doc = Document(id=identifier, service_id=SERVICE_ID, title='Live checkout pool runbook',
        kind='runbook', filename='live-checkout-runbook.txt', extracted_text=content,
        sha256=hashlib.sha256(content.encode()).hexdigest(), version=1,
        embedding_model=model_id())
    db.add(doc)
    db.flush()
    grant_roles(db, doc, ['viewer', 'responder', 'approver', 'admin'])
    index_document(db, doc, [(None, content)])
    db.commit()
    return {'created': True, 'document_id': str(identifier)}
