"""Fábrica genérica de recursos REST — equivalente à função `$1(caminho)` do front do Digisac.

Para cada recurso gera:
    GET    /recurso            lista paginada  (?page=&perPage=&q=&archived=)
    GET    /recurso/count
    GET    /recurso/{id}
    POST   /recurso            criar
    PUT    /recurso/{id}       editar
    DELETE /recurso/{id}
    POST   /recurso/{id}/archive   (quando o modelo tem archived_at)
e emite os eventos socket `<evento>.created|updated|destroyed`.
"""

from typing import Callable

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .db import get_db
from .deps import current_user, paginate
from .models import User, now
from .realtime import emit

Hook = Callable[[Session, object, dict, User, bool], None]


def make_crud_router(
    path: str,
    model,
    event: str,
    fields: dict[str, str],
    search: str | None = None,
    required: tuple[str, ...] = (),
    admin_write: bool = True,
    before_save: Hook | None = None,
    order_by=None,
) -> APIRouter:
    router = APIRouter(prefix=path, tags=[path.strip("/")])
    archivable = hasattr(model, "archived_at")

    def _base(db: Session, user: User):
        return db.query(model).filter(model.account_id == user.account_id)

    def _get(db: Session, user: User, item_id: str):
        obj = _base(db, user).filter(model.id == item_id).first()
        if not obj:
            raise HTTPException(404, detail={"message": "Não encontrado"})
        return obj

    def _check_write(user: User):
        if admin_write and not user.is_admin:
            raise HTTPException(403, detail={"message": "Apenas administradores"})

    def _apply(db, obj, body: dict, user: User, creating: bool):
        for key, attr in fields.items():
            if key in body:
                setattr(obj, attr, body[key])
        if before_save:
            before_save(db, obj, body, user, creating)

    @router.get("")
    def list_items(
        page: int = 1,
        perPage: int = Query(40),
        q: str | None = None,
        archived: bool = False,
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        query = _base(db, user)
        if archivable and not archived:
            query = query.filter(model.archived_at.is_(None))
        if q and search:
            query = query.filter(getattr(model, search).ilike(f"%{q}%"))
        query = query.order_by(order_by if order_by is not None else model.created_at.desc())
        return paginate(query, page, perPage)

    @router.get("/count")
    def count_items(db: Session = Depends(get_db), user: User = Depends(current_user)):
        query = _base(db, user)
        if archivable:
            query = query.filter(model.archived_at.is_(None))
        return {"count": query.count()}

    @router.get("/{item_id}")
    def get_item(item_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
        return _get(db, user, item_id).to_dict()

    @router.post("", status_code=201)
    async def create_item(
        body: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(current_user)
    ):
        _check_write(user)
        missing = [k for k in required if not body.get(k)]
        if missing:
            raise HTTPException(422, detail={"message": f"Campos obrigatórios: {', '.join(missing)}"})
        obj = model(account_id=user.account_id)
        _apply(db, obj, body, user, True)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        data = obj.to_dict()
        await emit(user.account_id, f"{event}.created", data)
        return data

    @router.put("/{item_id}")
    async def update_item(
        item_id: str,
        body: dict = Body(...),
        db: Session = Depends(get_db),
        user: User = Depends(current_user),
    ):
        _check_write(user)
        obj = _get(db, user, item_id)
        _apply(db, obj, body, user, False)
        db.commit()
        db.refresh(obj)
        data = obj.to_dict()
        await emit(user.account_id, f"{event}.updated", data)
        return data

    @router.delete("/{item_id}")
    async def delete_item(item_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
        _check_write(user)
        obj = _get(db, user, item_id)
        data = obj.to_dict()
        db.delete(obj)
        db.commit()
        await emit(user.account_id, f"{event}.destroyed", data)
        return True

    if archivable:

        @router.post("/{item_id}/archive")
        async def archive_item(
            item_id: str,
            body: dict = Body(default={}),
            db: Session = Depends(get_db),
            user: User = Depends(current_user),
        ):
            _check_write(user)
            obj = _get(db, user, item_id)
            obj.archived_at = None if body.get("archive") is False else now()
            db.commit()
            data = obj.to_dict()
            await emit(user.account_id, f"{event}.updated", data)
            return data

    return router
