from slugify import slugify


def make_slug(value: str, fallback: str = "item") -> str:
    slug = slugify(value or "")
    return slug or fallback


def unique_slug(session, model, base: str, current_id: int | None = None) -> str:
    slug = make_slug(base)
    candidate = slug
    suffix = 2
    while True:
        query = session.query(model).filter(model.slug == candidate)
        if current_id is not None:
            query = query.filter(model.id != current_id)
        if not session.query(query.exists()).scalar():
            return candidate
        candidate = f"{slug}-{suffix}"
        suffix += 1
