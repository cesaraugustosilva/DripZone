from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user, require_csrf, require_roles
from app.exceptions import ApiError
from app.models import AdminUser
from app.schemas.user import UserCreate, UserRead
from app.security import normalize_email, password_hash
from app.services.activities import record_activity

router = APIRouter(dependencies=[Depends(require_roles("owner"))])


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    return db.query(AdminUser).order_by(AdminUser.created_at.desc()).all()


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(AdminUser, user_id)
    if not user:
        raise ApiError(404, "USER_NOT_FOUND", "Administrador não encontrado.")
    return user


@router.post("", response_model=UserRead, status_code=201, dependencies=[Depends(require_csrf)])
def create_user(payload: UserCreate, db: Session = Depends(get_db), actor: AdminUser = Depends(current_user)):
    email = normalize_email(payload.email)
    if db.query(AdminUser).filter(AdminUser.email == email).first():
        raise ApiError(409, "USER_EMAIL_CONFLICT", "E-mail já está em uso.")
    user = AdminUser(name=payload.name, email=email, password_hash=password_hash(payload.password), role=payload.role, is_active=payload.is_active)
    db.add(user)
    db.flush()
    record_activity(db, user_id=actor.id, action="create", entity_type="user", entity_id=user.id, summary=f"Administrador criado: {user.email}")
    return user


@router.put("/{user_id}", response_model=UserRead, dependencies=[Depends(require_csrf)])
def update_user(user_id: int, payload: UserCreate, db: Session = Depends(get_db), actor: AdminUser = Depends(current_user)):
    user = db.get(AdminUser, user_id)
    if not user:
        raise ApiError(404, "USER_NOT_FOUND", "Administrador não encontrado.")
    user.name = payload.name
    user.email = normalize_email(payload.email)
    user.role = payload.role
    user.is_active = payload.is_active
    if payload.password:
        user.password_hash = password_hash(payload.password)
        user.session_version += 1
    record_activity(db, user_id=actor.id, action="update", entity_type="user", entity_id=user.id, summary=f"Administrador editado: {user.email}")
    return user


@router.delete("/{user_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_user(user_id: int, db: Session = Depends(get_db), actor: AdminUser = Depends(current_user)):
    if actor.id == user_id:
        raise ApiError(409, "USER_SELF_DELETE", "Não é possível excluir o próprio usuário.")
    user = db.get(AdminUser, user_id)
    if user:
        db.delete(user)
        record_activity(db, user_id=actor.id, action="delete", entity_type="user", entity_id=user_id, summary="Administrador excluído.")
