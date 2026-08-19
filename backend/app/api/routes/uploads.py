from io import BytesIO
from pathlib import Path
import warnings

from fastapi import APIRouter, Depends, File, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config import settings
from app.api.routes.products import commit_public_catalog_if_product_public
from app.database import get_db
from app.dependencies import current_user, require_csrf
from app.exceptions import ApiError
from app.models import ProductImage
from app.schemas.product import ImageRead
from app.services.products import ensure_publication_ready, get_product, readiness_issue
from app.services.upload_storage import ensure_canonical_upload_write_allowed, remove_upload_storage_file
from app.utils.files import ensure_child_path, safe_image_name

router = APIRouter(dependencies=[Depends(current_user)])

EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
FORMAT_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


@router.post("/{product_id}/images", response_model=ImageRead, status_code=201, dependencies=[Depends(require_csrf)])
async def upload_image(product_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    ensure_canonical_upload_write_allowed()
    product = get_product(db, product_id)
    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise ApiError(413, "UPLOAD_TOO_LARGE", "Arquivo excede o tamanho máximo.")
    declared_mime = (file.content_type or "").split(";")[0].strip().lower()
    if declared_mime not in settings.allowed_image_type_list:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Formato de imagem não permitido.")
    try:
        Image.MAX_IMAGE_PIXELS = settings.import_image_max_pixels
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                image.verify()
            image = Image.open(BytesIO(content))
            image_format = image.format or ""
            image = ImageOps.exif_transpose(image)
            detected_mime = FORMAT_MIME.get(image_format)
            if detected_mime not in settings.allowed_image_type_list:
                raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Formato de imagem nao permitido.")
            if detected_mime != declared_mime:
                raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "O MIME informado nao corresponde ao conteudo da imagem.")
            image.load()
            width, height = image.size
        if width <= 0 or height <= 0 or width > settings.import_image_max_width or height > settings.import_image_max_height or width * height > settings.import_image_max_pixels:
            raise ApiError(422, "IMAGE_TOO_LARGE", "Dimensões da imagem são grandes demais.")
    except Image.DecompressionBombWarning:
        raise ApiError(422, "IMAGE_TOO_LARGE", "Dimensoes da imagem sao grandes demais.")
    except UnidentifiedImageError:
        raise ApiError(415, "INVALID_IMAGE", "Arquivo não é uma imagem válida.")
    ext = EXTENSIONS[declared_mime]
    filename = safe_image_name(ext)
    upload_root = Path(settings.upload_directory)
    folder = ensure_child_path(upload_root, upload_root / "products" / product.public_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = ensure_child_path(folder, folder / filename)
    image.save(path, format={"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}[ext])
    db_committed = False
    try:
        record = ProductImage(
            product_id=product.id,
            filename=filename,
            storage_path=str(path),
            public_url=f"/uploads/products/{product.public_id}/{filename}",
            mime_type=declared_mime,
            size_bytes=path.stat().st_size,
            width=width,
            height=height,
            alt_text=None,
            is_primary=not product.images,
            position=len(product.images),
        )
        db.add(record)
        db.flush()
        if product.status == "published":
            commit_public_catalog_if_product_public(db, product, ("images",))
        else:
            db.commit()
        db_committed = True
        db.refresh(record)
        return record
    except ApiError as exc:
        if not (exc.code == "PUBLIC_CATALOG_PUBLISH_FAILED" and isinstance(exc.details, dict) and exc.details.get("db_committed")):
            db.rollback()
            remove_upload_storage_file(path, context={"operation": "upload_image", "product_id": product.id})
        raise
    except Exception:
        if not db_committed:
            db.rollback()
            remove_upload_storage_file(path, context={"operation": "upload_image", "product_id": product.id})
        raise


@router.put("/{product_id}/images/{image_id}", response_model=ImageRead, dependencies=[Depends(require_csrf)])
def update_image(product_id: int, image_id: int, alt_text: str | None = None, position: int = 0, db: Session = Depends(get_db)):
    image = db.get(ProductImage, image_id)
    if not image or image.product_id != product_id:
        raise ApiError(404, "IMAGE_NOT_FOUND", "Imagem não encontrada.")
    product = get_product(db, product_id)
    image.alt_text = alt_text
    image.position = max(position, 0)
    commit_public_catalog_if_product_public(db, product, ("images",))
    return image


@router.delete("/{product_id}/images/{image_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_image(product_id: int, image_id: int, db: Session = Depends(get_db)):
    image = db.get(ProductImage, image_id)
    if image and image.product_id == product_id:
        product = get_product(db, product_id)
        if product.status == "published" and image.is_primary:
            raise ApiError(
                422,
                "PRODUCT_NOT_READY_FOR_PUBLICATION",
                "O produto ainda não está pronto para publicação.",
                {"eligible": False, "blockers": [readiness_issue("PRIMARY_IMAGE_REQUIRED", "images", "Selecione uma imagem principal pública válida.")], "warnings": []},
            )
        storage_path = image.storage_path
        db.delete(image)
        commit_public_catalog_if_product_public(db, product, ("images",))
        if product.status != "published":
            db.commit()
        remove_upload_storage_file(storage_path, context={"operation": "delete_image", "product_id": product_id, "image_id": image_id})


@router.post("/{product_id}/images/{image_id}/primary", response_model=ImageRead, dependencies=[Depends(require_csrf)])
def set_primary(product_id: int, image_id: int, db: Session = Depends(get_db)):
    image = db.get(ProductImage, image_id)
    if not image or image.product_id != product_id:
        raise ApiError(404, "IMAGE_NOT_FOUND", "Imagem não encontrada.")
    for item in db.query(ProductImage).filter(ProductImage.product_id == product_id).all():
        item.is_primary = item.id == image_id
    product = get_product(db, product_id)
    if product.status == "published":
        ensure_publication_ready(db, product)
    commit_public_catalog_if_product_public(db, product, ("images",))
    return image
