from fastapi import APIRouter

from app.api.routes import activities, auth, imports, resources, status, products, settings, uploads, users

api_router = APIRouter()
api_router.include_router(status.router, tags=["status"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(resources.brands_router, prefix="/brands", tags=["brands"])
api_router.include_router(resources.categories_router, prefix="/categories", tags=["categories"])
api_router.include_router(resources.collections_router, prefix="/collections", tags=["collections"])
api_router.include_router(resources.sneakers_router, prefix="/sneakers", tags=["sneakers"])
api_router.include_router(resources.accessories_router, prefix="/accessories", tags=["accessories"])
api_router.include_router(imports.router, prefix="/imports", tags=["imports"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(uploads.router, prefix="/products", tags=["uploads"])
api_router.include_router(activities.router, prefix="/activities", tags=["activities"])
