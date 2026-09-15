from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Brand, Product, SneakerModel
from app.services.sneaker_taxonomy import seed_sneaker_menu_taxonomy


EXPECTED_SNEAKER_TAXONOMY = {
    "nike": [
        ("Air Force", "air-force"),
        ("Air Max TN Plus", "air-max-tn-plus"),
        ("Nike Mind", "nike-mind"),
        ("Air Max 95", "air-max-95"),
        ("Air Max DN", "air-max-dn"),
        ("Dunk", "dunk"),
        ("Nike x Kobe Bryant", "nike-x-kobe-bryant"),
        ("Nike Ja Morant", "nike-ja-morant"),
        ("Nike Shox", "nike-shox"),
        ("Uptempo", "uptempo"),
        ("Vomero Premium", "vomero-premium"),
        ("Travis Scott", "travis-scott"),
    ],
    "jordan": [
        ("Jordan 1 Low", "jordan-1-low"),
        ("Jordan 1 High", "jordan-1-high"),
        ("Jordan 3", "jordan-3"),
        ("Jordan 4", "jordan-4"),
        ("Jordan 6", "jordan-6"),
        ("Jordan 11", "jordan-11"),
        ("Travis Scott", "travis-scott-jordan"),
    ],
    "adidas": [
        ("Adistar Jellyfish", "adistar-jellyfish"),
        ("Adizero", "adizero"),
        ("Bad Bunny", "bad-bunny"),
        ("Campus 00", "campus-00"),
        ("Foam Runner", "foam-runner"),
        ("Yeezy 350 V2", "yeezy-350-v2"),
        ("Yeezy 380", "yeezy-380"),
        ("Yeezy 500", "yeezy-500"),
        ("Yeezy 700", "yeezy-700"),
        ("Yeezy Slide", "yeezy-slide"),
    ],
    "new-balance": [
        ("New Balance 9060", "new-balance-9060"),
        ("New Balance 530", "new-balance-530"),
        ("New Balance 550", "new-balance-550"),
        ("New Balance 1000", "new-balance-1000"),
        ("New Balance 1906A", "new-balance-1906a"),
        ("New Balance 740", "new-balance-740"),
    ],
    "golden-goose": [
        ("Super-Star", "super-star"),
        ("Ball Star", "ball-star"),
        ("Stardan", "stardan"),
        ("Purestar", "purestar"),
    ],
}


def test_brands_categories_collections_sneakers_and_permissions(authed):
    client, headers = authed
    brand = client.post("/api/brands", json={"name": "Marca Real"}, headers=headers)
    assert brand.status_code == 201
    duplicate = client.post("/api/brands", json={"name": "Marca Real"}, headers=headers)
    assert duplicate.status_code == 409
    category = client.post("/api/categories", json={"name": "Categoria Real"}, headers=headers)
    assert category.status_code == 201
    cycle = client.put(f"/api/categories/{category.json()['id']}", json={"name": "Categoria Real", "parent_id": category.json()["id"]}, headers=headers)
    assert cycle.status_code == 422
    collection = client.post("/api/collections", json={"name": "Colecao Real"}, headers=headers)
    assert collection.status_code == 201

    sneaker = client.post("/api/sneakers", json={"name": "Air Force 1", "slug": "air-force-1", "brand_id": brand.json()["id"]}, headers=headers)
    assert sneaker.status_code == 201
    assert sneaker.json()["brand_id"] == brand.json()["id"]
    assert client.get(f"/api/sneakers/{sneaker.json()['id']}").json()["slug"] == "air-force-1"

    invalid_sneaker = client.post("/api/sneakers", json={"name": "Modelo Solto", "brand_id": 99999}, headers=headers)
    assert invalid_sneaker.status_code == 422

    free_sneaker = client.post("/api/sneakers", json={"name": "Dunk", "slug": "dunk", "brand_id": brand.json()["id"]}, headers=headers)
    assert free_sneaker.status_code == 201
    assert client.delete(f"/api/sneakers/{free_sneaker.json()['id']}", headers=headers).status_code == 204

    product = client.post(
        "/api/products",
        json={
            "name": "Produto Relacionado",
            "price": "5.00",
            "brand_id": brand.json()["id"],
            "category_id": category.json()["id"],
            "sneaker_model_id": sneaker.json()["id"],
        },
        headers=headers,
    )
    assert product.status_code == 201
    blocked_brand_delete = client.delete(f"/api/brands/{brand.json()['id']}", headers=headers)
    assert blocked_brand_delete.status_code == 409
    blocked_sneaker_delete = client.delete(f"/api/sneakers/{sneaker.json()['id']}", headers=headers)
    assert blocked_sneaker_delete.status_code == 409

    client.post("/api/auth/logout", headers=headers)
    public_sneakers = client.get("/api/sneakers")
    assert public_sneakers.status_code == 200
    public_sneaker = next(item for item in public_sneakers.json() if item["slug"] == "air-force-1")
    assert public_sneaker["brand_slug"] == "marca-real"
    assert public_sneaker["brand_name"] == "Marca Real"

    login = client.post("/api/auth/login", json={"email": "editor@example.com", "password": "password123"})
    assert login.status_code == 200
    editor_headers = {"X-CSRF-Token": client.get("/api/auth/csrf").json()["csrf_token"]}
    forbidden = client.delete(f"/api/products/{product.json()['id']}", headers=editor_headers)
    assert forbidden.status_code == 403


def test_sneaker_menu_taxonomy_seed_is_idempotent_without_products(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'taxonomy.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        first = seed_sneaker_menu_taxonomy(db)
        db.commit()
        second = seed_sneaker_menu_taxonomy(db)
        db.commit()

        assert first["created_models"] == 39
        assert first["duplicates"] == 0
        assert second["created_models"] == 0
        assert second["duplicates"] == 0
        assert db.query(Product).count() == 0

        active_total = 0
        for brand_slug, expected_models in EXPECTED_SNEAKER_TAXONOMY.items():
            brand = db.query(Brand).filter_by(slug=brand_slug).one()
            models = (
                db.query(SneakerModel)
                .filter_by(brand_id=brand.id, is_active=True)
                .order_by(SneakerModel.position.asc())
                .all()
            )
            assert [(model.name, model.slug) for model in models] == expected_models
            active_total += len(models)

        assert active_total == 39


def test_sneaker_menu_taxonomy_deactivates_legacy_models_without_deleting_product_references(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'taxonomy-legacy.db'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        nike = Brand(name="Nike", slug="nike", is_active=True)
        jordan = Brand(name="Jordan", slug="jordan", is_active=True)
        db.add_all([nike, jordan])
        db.flush()
        air_force_1 = SneakerModel(brand_id=nike.id, name="Air Force 1", slug="air-force-1", is_active=True, position=10)
        air_max = SneakerModel(brand_id=nike.id, name="Air Max", slug="air-max", is_active=True, position=30)
        jordan_5 = SneakerModel(brand_id=jordan.id, name="Jordan 5", slug="jordan-5", is_active=True, position=40)
        db.add_all([air_force_1, air_max, jordan_5])
        db.flush()
        db.add(Product(public_id="legacy-1", name="Nike Air Max Legado", slug="nike-air-max-legado", price="100.00", sneaker_model_id=air_max.id))
        db.commit()

        result = seed_sneaker_menu_taxonomy(db)
        db.commit()

        migrated_air_force = db.query(SneakerModel).filter_by(slug="air-force").one()
        legacy_air_max = db.query(SneakerModel).filter_by(slug="air-max").one()
        legacy_jordan_5 = db.query(SneakerModel).filter_by(slug="jordan-5").one()

        assert migrated_air_force.id == air_force_1.id
        assert migrated_air_force.name == "Air Force"
        assert migrated_air_force.is_active is True
        assert legacy_air_max.is_active is False
        assert legacy_jordan_5.is_active is False
        assert db.query(Product).filter_by(sneaker_model_id=legacy_air_max.id).count() == 1
        assert result["legacy_models_with_products"] == 1
