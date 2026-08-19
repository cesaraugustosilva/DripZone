def test_brands_categories_collections_and_permissions(authed):
    client, headers = authed
    brand = client.post("/api/brands", json={"name": "Marca Real"}, headers=headers)
    assert brand.status_code == 201
    duplicate = client.post("/api/brands", json={"name": "Marca Real"}, headers=headers)
    assert duplicate.status_code == 409
    category = client.post("/api/categories", json={"name": "Categoria Real"}, headers=headers)
    assert category.status_code == 201
    cycle = client.put(f"/api/categories/{category.json()['id']}", json={"name": "Categoria Real", "parent_id": category.json()["id"]}, headers=headers)
    assert cycle.status_code == 422
    collection = client.post("/api/collections", json={"name": "Coleção Real"}, headers=headers)
    assert collection.status_code == 201
    product = client.post("/api/products", json={"name": "Produto Relacionado", "price": "5.00", "brand_id": brand.json()["id"], "category_id": category.json()["id"]}, headers=headers)
    assert product.status_code == 201
    blocked_brand_delete = client.delete(f"/api/brands/{brand.json()['id']}", headers=headers)
    assert blocked_brand_delete.status_code == 409
    client.post("/api/auth/logout", headers=headers)
    login = client.post("/api/auth/login", json={"email": "editor@example.com", "password": "password123"})
    assert login.status_code == 200
    editor_headers = {"X-CSRF-Token": client.get("/api/auth/csrf").json()["csrf_token"]}
    forbidden = client.delete(f"/api/products/{product.json()['id']}", headers=editor_headers)
    assert forbidden.status_code == 403
