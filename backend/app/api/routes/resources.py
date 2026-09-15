from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.dependencies import current_user, require_csrf
from app.exceptions import ApiError
from app.models import AccessoryType, Brand, Category, Collection, Product, SneakerModel
from app.schemas.resources import AccessoryCreate, AccessoryRead, BrandCreate, BrandRead, CategoryCreate, CategoryRead, CollectionCreate, CollectionRead, SneakerCreate, SneakerRead
from app.services.activities import record_activity
from app.utils.slug import unique_slug

brands_router = APIRouter(dependencies=[Depends(current_user)])
categories_router = APIRouter(dependencies=[Depends(current_user)])
collections_router = APIRouter(dependencies=[Depends(current_user)])
sneakers_router = APIRouter()
accessories_router = APIRouter(dependencies=[Depends(current_user)])


def create_resource(db: Session, model, payload):
    data = payload.model_dump()
    data["slug"] = data.get("slug") or unique_slug(db, model, data["name"])
    item = model(**data)
    db.add(item)
    db.flush()
    return item


def update_resource(db: Session, model, item_id: int, payload):
    item = db.get(model, item_id)
    if not item:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Registro não encontrado.")
    data = payload.model_dump()
    data["slug"] = data.get("slug") or unique_slug(db, model, data["name"], item.id)
    for key, value in data.items():
        setattr(item, key, value)
    return item


def delete_resource(db: Session, model, item_id: int, usage_model=None, usage_field: str | None = None):
    item = db.get(model, item_id)
    if not item:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Registro não encontrado.")
    if usage_model and usage_field and db.query(usage_model).filter(getattr(usage_model, usage_field) == item_id).first():
        raise ApiError(409, "RESOURCE_IN_USE", "Registro em uso por produtos.")
    db.delete(item)


def validate_sneaker_brand(db: Session, payload: SneakerCreate) -> None:
    if payload.brand_id and not db.get(Brand, payload.brand_id):
        raise ApiError(422, "BRAND_NOT_FOUND", "Marca informada não existe.")


@brands_router.get("", response_model=list[BrandRead])
def list_brands(db: Session = Depends(get_db)):
    return db.query(Brand).order_by(Brand.position.asc(), Brand.name.asc()).all()


@brands_router.get("/{item_id}", response_model=BrandRead)
def get_brand(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Brand, item_id)
    if not item:
        raise ApiError(404, "BRAND_NOT_FOUND", "Marca não encontrada.")
    return item


@brands_router.post("", response_model=BrandRead, status_code=201, dependencies=[Depends(require_csrf)])
def post_brand(payload: BrandCreate, db: Session = Depends(get_db), user=Depends(current_user)):
    item = create_resource(db, Brand, payload)
    record_activity(db, user_id=user.id, action="create", entity_type="brand", entity_id=item.id, summary=f"Marca criada: {item.name}")
    return item


@brands_router.put("/{item_id}", response_model=BrandRead, dependencies=[Depends(require_csrf)])
@brands_router.patch("/{item_id}", response_model=BrandRead, dependencies=[Depends(require_csrf)])
def put_brand(item_id: int, payload: BrandCreate, db: Session = Depends(get_db)):
    return update_resource(db, Brand, item_id, payload)


@brands_router.delete("/{item_id}", status_code=204, dependencies=[Depends(require_csrf)])
def del_brand(item_id: int, db: Session = Depends(get_db)):
    delete_resource(db, Brand, item_id, Product, "brand_id")


@categories_router.get("", response_model=list[CategoryRead])
def list_categories(db: Session = Depends(get_db)):
    return db.query(Category).order_by(Category.position.asc(), Category.name.asc()).all()


@categories_router.get("/{item_id}", response_model=CategoryRead)
def get_category(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Category, item_id)
    if not item:
        raise ApiError(404, "CATEGORY_NOT_FOUND", "Categoria não encontrada.")
    return item


@categories_router.post("", response_model=CategoryRead, status_code=201, dependencies=[Depends(require_csrf)])
def post_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    if payload.parent_id and not db.get(Category, payload.parent_id):
        raise ApiError(422, "PARENT_CATEGORY_NOT_FOUND", "Categoria mãe não encontrada.")
    return create_resource(db, Category, payload)


@categories_router.put("/{item_id}", response_model=CategoryRead, dependencies=[Depends(require_csrf)])
@categories_router.patch("/{item_id}", response_model=CategoryRead, dependencies=[Depends(require_csrf)])
def put_category(item_id: int, payload: CategoryCreate, db: Session = Depends(get_db)):
    if payload.parent_id == item_id:
        raise ApiError(422, "CATEGORY_CYCLE", "Categoria não pode ser sua própria mãe.")
    parent = db.get(Category, payload.parent_id) if payload.parent_id else None
    while parent:
        if parent.parent_id == item_id:
            raise ApiError(422, "CATEGORY_CYCLE", "Hierarquia de categorias inválida.")
        parent = db.get(Category, parent.parent_id) if parent.parent_id else None
    return update_resource(db, Category, item_id, payload)


@categories_router.delete("/{item_id}", status_code=204, dependencies=[Depends(require_csrf)])
def del_category(item_id: int, db: Session = Depends(get_db)):
    delete_resource(db, Category, item_id, Product, "category_id")


@collections_router.get("", response_model=list[CollectionRead])
def list_collections(db: Session = Depends(get_db)):
    return db.query(Collection).order_by(Collection.position.asc(), Collection.name.asc()).all()


@collections_router.get("/{item_id}", response_model=CollectionRead)
def get_collection(item_id: int, db: Session = Depends(get_db)):
    item = db.get(Collection, item_id)
    if not item:
        raise ApiError(404, "COLLECTION_NOT_FOUND", "Coleção não encontrada.")
    return item


@collections_router.post("", response_model=CollectionRead, status_code=201, dependencies=[Depends(require_csrf)])
def post_collection(payload: CollectionCreate, db: Session = Depends(get_db)):
    return create_resource(db, Collection, payload)


@collections_router.put("/{item_id}", response_model=CollectionRead, dependencies=[Depends(require_csrf)])
@collections_router.patch("/{item_id}", response_model=CollectionRead, dependencies=[Depends(require_csrf)])
def put_collection(item_id: int, payload: CollectionCreate, db: Session = Depends(get_db)):
    return update_resource(db, Collection, item_id, payload)


@collections_router.delete("/{item_id}", status_code=204, dependencies=[Depends(require_csrf)])
def del_collection(item_id: int, db: Session = Depends(get_db)):
    delete_resource(db, Collection, item_id)


@collections_router.post("/{item_id}/products", dependencies=[Depends(require_csrf)])
def add_product_to_collection(item_id: int, product_id: int, db: Session = Depends(get_db)):
    collection = db.get(Collection, item_id)
    product = db.get(Product, product_id)
    if not collection or not product:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Coleção ou produto não encontrado.")
    if product not in collection.products:
        collection.products.append(product)
    return {"message": "Produto associado."}


@collections_router.delete("/{item_id}/products/{product_id}", dependencies=[Depends(require_csrf)])
def remove_product_from_collection(item_id: int, product_id: int, db: Session = Depends(get_db)):
    collection = db.get(Collection, item_id)
    product = db.get(Product, product_id)
    if collection and product and product in collection.products:
        collection.products.remove(product)
    return {"message": "Produto removido da coleção."}


@sneakers_router.get("", response_model=list[SneakerRead])
def list_sneakers(db: Session = Depends(get_db)):
    return db.query(SneakerModel).options(selectinload(SneakerModel.brand)).order_by(SneakerModel.position.asc(), SneakerModel.name.asc()).all()


@sneakers_router.get("/{item_id}", response_model=SneakerRead, dependencies=[Depends(current_user)])
def get_sneaker(item_id: int, db: Session = Depends(get_db)):
    item = db.get(SneakerModel, item_id)
    if not item:
        raise ApiError(404, "SNEAKER_NOT_FOUND", "Modelo não encontrado.")
    return item


@sneakers_router.post("", response_model=SneakerRead, status_code=201, dependencies=[Depends(current_user), Depends(require_csrf)])
def post_sneaker(payload: SneakerCreate, db: Session = Depends(get_db)):
    validate_sneaker_brand(db, payload)
    return create_resource(db, SneakerModel, payload)


@sneakers_router.put("/{item_id}", response_model=SneakerRead, dependencies=[Depends(current_user), Depends(require_csrf)])
def put_sneaker(item_id: int, payload: SneakerCreate, db: Session = Depends(get_db)):
    validate_sneaker_brand(db, payload)
    return update_resource(db, SneakerModel, item_id, payload)


@sneakers_router.delete("/{item_id}", status_code=204, dependencies=[Depends(current_user), Depends(require_csrf)])
def del_sneaker(item_id: int, db: Session = Depends(get_db)):
    delete_resource(db, SneakerModel, item_id, Product, "sneaker_model_id")


@accessories_router.get("", response_model=list[AccessoryRead])
def list_accessories(db: Session = Depends(get_db)):
    return db.query(AccessoryType).order_by(AccessoryType.position.asc(), AccessoryType.name.asc()).all()


@accessories_router.get("/{item_id}", response_model=AccessoryRead)
def get_accessory(item_id: int, db: Session = Depends(get_db)):
    item = db.get(AccessoryType, item_id)
    if not item:
        raise ApiError(404, "ACCESSORY_NOT_FOUND", "Acessório não encontrado.")
    return item


@accessories_router.post("", response_model=AccessoryRead, status_code=201, dependencies=[Depends(require_csrf)])
def post_accessory(payload: AccessoryCreate, db: Session = Depends(get_db)):
    return create_resource(db, AccessoryType, payload)


@accessories_router.put("/{item_id}", response_model=AccessoryRead, dependencies=[Depends(require_csrf)])
def put_accessory(item_id: int, payload: AccessoryCreate, db: Session = Depends(get_db)):
    return update_resource(db, AccessoryType, item_id, payload)


@accessories_router.delete("/{item_id}", status_code=204, dependencies=[Depends(require_csrf)])
def del_accessory(item_id: int, db: Session = Depends(get_db)):
    delete_resource(db, AccessoryType, item_id, Product, "accessory_id")
