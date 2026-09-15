from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Brand, Product, SneakerModel


@dataclass(frozen=True)
class SneakerTaxonomyItem:
    brand_name: str
    brand_slug: str
    name: str
    slug: str
    position: int
    legacy_slugs: tuple[str, ...] = ()


SNEAKER_MENU_TAXONOMY: tuple[SneakerTaxonomyItem, ...] = (
    SneakerTaxonomyItem("Nike", "nike", "Air Force", "air-force", 10, ("air-force-1",)),
    SneakerTaxonomyItem("Nike", "nike", "Air Max TN Plus", "air-max-tn-plus", 20, ("air-max-plus",)),
    SneakerTaxonomyItem("Nike", "nike", "Nike Mind", "nike-mind", 30),
    SneakerTaxonomyItem("Nike", "nike", "Air Max 95", "air-max-95", 40),
    SneakerTaxonomyItem("Nike", "nike", "Air Max DN", "air-max-dn", 50),
    SneakerTaxonomyItem("Nike", "nike", "Dunk", "dunk", 60),
    SneakerTaxonomyItem("Nike", "nike", "Nike x Kobe Bryant", "nike-x-kobe-bryant", 70),
    SneakerTaxonomyItem("Nike", "nike", "Nike Ja Morant", "nike-ja-morant", 80),
    SneakerTaxonomyItem("Nike", "nike", "Nike Shox", "nike-shox", 90),
    SneakerTaxonomyItem("Nike", "nike", "Uptempo", "uptempo", 100),
    SneakerTaxonomyItem("Nike", "nike", "Vomero Premium", "vomero-premium", 110),
    SneakerTaxonomyItem("Nike", "nike", "Travis Scott", "travis-scott", 120),
    SneakerTaxonomyItem("Jordan", "jordan", "Jordan 1 Low", "jordan-1-low", 10),
    SneakerTaxonomyItem("Jordan", "jordan", "Jordan 1 High", "jordan-1-high", 20),
    SneakerTaxonomyItem("Jordan", "jordan", "Jordan 3", "jordan-3", 30),
    SneakerTaxonomyItem("Jordan", "jordan", "Jordan 4", "jordan-4", 40),
    SneakerTaxonomyItem("Jordan", "jordan", "Jordan 6", "jordan-6", 50),
    SneakerTaxonomyItem("Jordan", "jordan", "Jordan 11", "jordan-11", 60),
    SneakerTaxonomyItem("Jordan", "jordan", "Travis Scott", "travis-scott-jordan", 70),
    SneakerTaxonomyItem("Adidas", "adidas", "Adistar Jellyfish", "adistar-jellyfish", 10),
    SneakerTaxonomyItem("Adidas", "adidas", "Adizero", "adizero", 20),
    SneakerTaxonomyItem("Adidas", "adidas", "Bad Bunny", "bad-bunny", 30),
    SneakerTaxonomyItem("Adidas", "adidas", "Campus 00", "campus-00", 40, ("adidas-campus",)),
    SneakerTaxonomyItem("Adidas", "adidas", "Foam Runner", "foam-runner", 50),
    SneakerTaxonomyItem("Adidas", "adidas", "Yeezy 350 V2", "yeezy-350-v2", 60),
    SneakerTaxonomyItem("Adidas", "adidas", "Yeezy 380", "yeezy-380", 70),
    SneakerTaxonomyItem("Adidas", "adidas", "Yeezy 500", "yeezy-500", 80),
    SneakerTaxonomyItem("Adidas", "adidas", "Yeezy 700", "yeezy-700", 90),
    SneakerTaxonomyItem("Adidas", "adidas", "Yeezy Slide", "yeezy-slide", 100),
    SneakerTaxonomyItem("New Balance", "new-balance", "New Balance 9060", "new-balance-9060", 10),
    SneakerTaxonomyItem("New Balance", "new-balance", "New Balance 530", "new-balance-530", 20),
    SneakerTaxonomyItem("New Balance", "new-balance", "New Balance 550", "new-balance-550", 30),
    SneakerTaxonomyItem("New Balance", "new-balance", "New Balance 1000", "new-balance-1000", 40),
    SneakerTaxonomyItem("New Balance", "new-balance", "New Balance 1906A", "new-balance-1906a", 50),
    SneakerTaxonomyItem("New Balance", "new-balance", "New Balance 740", "new-balance-740", 60),
    SneakerTaxonomyItem("Golden Goose", "golden-goose", "Super-Star", "super-star", 10, ("golden-goose-superstar",)),
    SneakerTaxonomyItem("Golden Goose", "golden-goose", "Ball Star", "ball-star", 20, ("golden-goose-ball-star",)),
    SneakerTaxonomyItem("Golden Goose", "golden-goose", "Stardan", "stardan", 30),
    SneakerTaxonomyItem("Golden Goose", "golden-goose", "Purestar", "purestar", 40),
)


def seed_sneaker_menu_taxonomy(db: Session) -> dict:
    created_brands = 0
    created_models = 0
    updated_models = 0
    deactivated_models = 0
    legacy_models_with_products = 0
    skipped_models = 0
    brands_by_slug = {brand.slug: brand for brand in db.query(Brand).all()}
    target_brand_slugs = {item.brand_slug for item in SNEAKER_MENU_TAXONOMY}
    target_slugs_by_brand = {
        brand_slug: {item.slug for item in SNEAKER_MENU_TAXONOMY if item.brand_slug == brand_slug}
        for brand_slug in target_brand_slugs
    }

    for item in SNEAKER_MENU_TAXONOMY:
        brand = brands_by_slug.get(item.brand_slug)
        if not brand:
            brand = Brand(name=item.brand_name, slug=item.brand_slug, is_active=True, position=0)
            db.add(brand)
            db.flush()
            brands_by_slug[item.brand_slug] = brand
            created_brands += 1

        model = db.query(SneakerModel).filter(SneakerModel.slug == item.slug).first()
        if not model and item.legacy_slugs:
            model = (
                db.query(SneakerModel)
                .filter(SneakerModel.brand_id == brand.id, SneakerModel.slug.in_(item.legacy_slugs))
                .order_by(SneakerModel.id.asc())
                .first()
            )

        if model:
            changed = False
            if model.brand_id != brand.id:
                model.brand_id = brand.id
                changed = True
            if model.name != item.name:
                model.name = item.name
                changed = True
            if model.slug != item.slug:
                if db.query(SneakerModel).filter(SneakerModel.slug == item.slug, SneakerModel.id != model.id).first():
                    skipped_models += 1
                    continue
                model.slug = item.slug
                changed = True
            if model.is_active is not True:
                model.is_active = True
                changed = True
            if model.position != item.position:
                model.position = item.position
                changed = True
            updated_models += 1 if changed else 0
            skipped_models += 1
            continue

        db.add(
            SneakerModel(
                brand_id=brand.id,
                name=item.name,
                slug=item.slug,
                is_active=True,
                position=item.position,
            )
        )
        created_models += 1

    db.flush()

    for brand_slug in target_brand_slugs:
        brand = brands_by_slug.get(brand_slug)
        if not brand:
            continue
        active_slugs = target_slugs_by_brand[brand_slug]
        legacy_models = (
            db.query(SneakerModel)
            .filter(SneakerModel.brand_id == brand.id, SneakerModel.is_active.is_(True), SneakerModel.slug.notin_(active_slugs))
            .all()
        )
        for model in legacy_models:
            product_count = db.query(Product).filter(Product.sneaker_model_id == model.id).count()
            if product_count:
                legacy_models_with_products += 1
            model.is_active = False
            deactivated_models += 1

    return {
        "created_brands": created_brands,
        "created_models": created_models,
        "updated_models": updated_models,
        "deactivated_models": deactivated_models,
        "legacy_models_with_products": legacy_models_with_products,
        "skipped_models": skipped_models,
        "duplicates": 0,
    }
