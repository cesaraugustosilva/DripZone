import argparse
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, event, func, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.sqltypes import Boolean, DateTime, JSON, Numeric

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import engine_options_for_url
from app.models import Base


EXPECTED_REVISION = "20260724_0002"
APPLICATION_TABLES = [
    "admin_users",
    "brands",
    "categories",
    "collections",
    "accessory_types",
    "sneaker_models",
    "products",
    "product_variants",
    "product_images",
    "product_collections",
    "import_records",
    "import_items",
    "store_settings",
    "activities",
]
MIGRATION_ORDER = [
    "admin_users",
    "brands",
    "categories",
    "collections",
    "accessory_types",
    "sneaker_models",
    "products",
    "product_variants",
    "product_images",
    "product_collections",
    "import_records",
    "import_items",
    "store_settings",
    "activities",
]
SENSITIVE_COLUMNS = {"password_hash"}


class MigrationError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migracao controlada do SQLite local para PostgreSQL.")
    parser.add_argument("--source", required=True, help="Caminho do SQLite de origem, relativo ao backend ou absoluto.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Valida e simula sem escrever no PostgreSQL.")
    mode.add_argument("--execute", action="store_true", help="Executa a migracao real em transacao unica.")
    return parser.parse_args()


def safe_label(url_text: str) -> str:
    url = make_url(url_text)
    return f"backend={url.get_backend_name()}; host={url.host or 'local'}; database={url.database or '(sem nome)'}"


def resolve_source(source: str) -> Path:
    path = Path(source)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if not path.exists():
        raise MigrationError(f"SQLite de origem nao encontrado: {path}")
    return path


def sqlite_engine(path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{path.as_posix()}", future=True)

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return engine


def postgres_engine() -> Engine:
    url = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql":
        raise MigrationError("Destino configurado nao e PostgreSQL. Ajuste backend/.env antes de migrar.")
    return create_engine(settings.database_url, **engine_options_for_url(settings.database_url))


def reflect(engine: Engine) -> MetaData:
    metadata = MetaData()
    metadata.reflect(bind=engine)
    return metadata


def table_counts(engine: Engine, table_names: list[str]) -> dict[str, dict[str, int | None]]:
    metadata = reflect(engine)
    with engine.connect() as connection:
        return table_counts_on_connection(connection, metadata, table_names)


def table_counts_on_connection(connection, metadata: MetaData, table_names: list[str]) -> dict[str, dict[str, int | None]]:
    result: dict[str, dict[str, int | None]] = {}
    for table_name in table_names:
        if table_name not in metadata.tables:
            result[table_name] = {"count": None, "min_id": None, "max_id": None}
            continue
        table = metadata.tables[table_name]
        count_value = connection.execute(select(func.count()).select_from(table)).scalar_one()
        min_id = max_id = None
        if "id" in table.c:
            min_id, max_id = connection.execute(select(func.min(table.c.id), func.max(table.c.id))).one()
        result[table_name] = {"count": int(count_value), "min_id": min_id, "max_id": max_id}
    return result


def print_inventory(sqlite_counts: dict[str, dict[str, int | None]], pg_counts: dict[str, dict[str, int | None]]) -> None:
    print("Inventario inicial:")
    print(f"{'Tabela':24} {'SQLite':>8} {'SQLite IDs':>18} {'PostgreSQL':>12} {'PostgreSQL IDs':>18}")
    for table_name in APPLICATION_TABLES:
        source = sqlite_counts[table_name]
        target = pg_counts[table_name]
        source_ids = id_range(source)
        target_ids = id_range(target)
        print(f"{table_name:24} {display_count(source):>8} {source_ids:>18} {display_count(target):>12} {target_ids:>18}")


def display_count(item: dict[str, int | None]) -> str:
    return "ausente" if item["count"] is None else str(item["count"])


def id_range(item: dict[str, int | None]) -> str:
    if item["count"] is None or item["min_id"] is None:
        return "-"
    return f"{item['min_id']}..{item['max_id']}"


def sqlite_foreign_key_check(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("PRAGMA foreign_key_check").mappings().all()
    return [dict(row) for row in rows]


def sqlite_orphan_checks(engine: Engine) -> list[str]:
    checks = [
        ("categories.parent_id", "categories", "parent_id", "categories", "id"),
        ("sneaker_models.brand_id", "sneaker_models", "brand_id", "brands", "id"),
        ("products.brand_id", "products", "brand_id", "brands", "id"),
        ("products.category_id", "products", "category_id", "categories", "id"),
        ("products.sneaker_model_id", "products", "sneaker_model_id", "sneaker_models", "id"),
        ("products.accessory_id", "products", "accessory_id", "accessory_types", "id"),
        ("products.created_by_id", "products", "created_by_id", "admin_users", "id"),
        ("products.updated_by_id", "products", "updated_by_id", "admin_users", "id"),
        ("product_variants.product_id", "product_variants", "product_id", "products", "id"),
        ("product_images.product_id", "product_images", "product_id", "products", "id"),
        ("product_collections.product_id", "product_collections", "product_id", "products", "id"),
        ("product_collections.collection_id", "product_collections", "collection_id", "collections", "id"),
        ("import_records.reviewed_by_id", "import_records", "reviewed_by_id", "admin_users", "id"),
        ("import_records.published_product_id", "import_records", "published_product_id", "products", "id"),
        ("import_items.import_record_id", "import_items", "import_record_id", "import_records", "id"),
        ("import_items.brand_id", "import_items", "brand_id", "brands", "id"),
        ("import_items.suggested_category_id", "import_items", "suggested_category_id", "categories", "id"),
        ("activities.user_id", "activities", "user_id", "admin_users", "id"),
    ]
    metadata = reflect(engine)
    problems: list[str] = []
    with engine.connect() as connection:
        for label, source_table, source_column, target_table, target_column in checks:
            if source_table not in metadata.tables or target_table not in metadata.tables:
                continue
            query = text(
                f"SELECT COUNT(*) FROM {source_table} s "
                f"LEFT JOIN {target_table} t ON s.{source_column}=t.{target_column} "
                f"WHERE s.{source_column} IS NOT NULL AND t.{target_column} IS NULL"
            )
            count_value = connection.execute(query).scalar_one()
            if count_value:
                problems.append(f"{label}: {count_value} registro(s) orfao(s)")
    return problems


def validate_postgres_revision(engine: Engine) -> None:
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if revision != EXPECTED_REVISION:
        raise MigrationError(f"Revision PostgreSQL incorreta: esperado {EXPECTED_REVISION}, encontrado {revision}.")
    print(f"Revision PostgreSQL: {revision}")


def ensure_destination_empty(pg_counts: dict[str, dict[str, int | None]]) -> None:
    non_empty = [name for name, item in pg_counts.items() if item["count"] not in (0, None)]
    if non_empty:
        detail = ", ".join(f"{name}={pg_counts[name]['count']}" for name in non_empty)
        raise MigrationError(f"Destino PostgreSQL contem dados de aplicacao; migracao interrompida: {detail}.")


def compare_schema(sqlite_metadata: MetaData, pg_metadata: MetaData) -> list[str]:
    issues: list[str] = []
    model_tables = Base.metadata.tables
    for table_name in APPLICATION_TABLES:
        if table_name not in sqlite_metadata.tables:
            issues.append(f"SQLite sem tabela esperada: {table_name}")
            continue
        if table_name not in pg_metadata.tables:
            issues.append(f"PostgreSQL sem tabela esperada: {table_name}")
            continue
        model_columns = set(model_tables[table_name].c.keys())
        sqlite_columns = set(sqlite_metadata.tables[table_name].c.keys())
        pg_columns = set(pg_metadata.tables[table_name].c.keys())
        missing_in_sqlite = model_columns - sqlite_columns
        extra_in_sqlite = sqlite_columns - model_columns
        missing_in_pg = model_columns - pg_columns
        extra_in_pg = pg_columns - model_columns
        if missing_in_sqlite:
            issues.append(f"{table_name}: colunas ausentes no SQLite: {sorted(missing_in_sqlite)}")
        if extra_in_sqlite:
            issues.append(f"{table_name}: colunas extras no SQLite: {sorted(extra_in_sqlite)}")
        if missing_in_pg:
            issues.append(f"{table_name}: colunas ausentes no PostgreSQL: {sorted(missing_in_pg)}")
        if extra_in_pg:
            issues.append(f"{table_name}: colunas extras no PostgreSQL: {sorted(extra_in_pg)}")
    return issues


def load_rows(engine: Engine, metadata: MetaData, table_name: str) -> list[dict[str, Any]]:
    table = metadata.tables[table_name]
    order_columns = [table.c.id] if "id" in table.c else list(table.primary_key.columns)
    with engine.connect() as connection:
        rows = connection.execute(select(table).order_by(*order_columns)).mappings().all()
    return [dict(row) for row in rows]


def convert_value(table_name: str, column_name: str, value: Any, target_column) -> tuple[Any, str | None]:
    if value is None:
        return None, None
    column_type = target_column.type
    if isinstance(column_type, JSON):
        if isinstance(value, str):
            try:
                return json.loads(value), f"{table_name}.{column_name}: JSON text desserializado"
            except json.JSONDecodeError as exc:
                raise MigrationError(f"JSON invalido em {table_name}.{column_name}: {exc}") from exc
        return value, None
    if isinstance(column_type, Boolean):
        if value in (0, 1):
            return bool(value), f"{table_name}.{column_name}: boolean {value} convertido"
        if isinstance(value, bool):
            return value, None
        raise MigrationError(f"Boolean invalido em {table_name}.{column_name}: {value!r}")
    if isinstance(column_type, Numeric):
        try:
            return Decimal(str(value)), f"{table_name}.{column_name}: Decimal preservado"
        except (InvalidOperation, ValueError) as exc:
            raise MigrationError(f"Numeric invalido em {table_name}.{column_name}: {value!r}") from exc
    if isinstance(column_type, DateTime) and isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise MigrationError(f"DateTime invalido em {table_name}.{column_name}: {value!r}") from exc
        return parsed, f"{table_name}.{column_name}: DateTime ISO convertido"
    return value, None


def transform_rows(rows: list[dict[str, Any]], target_table: Table) -> tuple[list[dict[str, Any]], list[str]]:
    transformed: list[dict[str, Any]] = []
    changes: set[str] = set()
    for row in rows:
        target_row: dict[str, Any] = {}
        for column in target_table.columns:
            value, change = convert_value(target_table.name, column.name, row.get(column.name), column)
            target_row[column.name] = value
            if change and column.name not in SENSITIVE_COLUMNS:
                changes.add(change)
        transformed.append(target_row)
    return transformed, sorted(changes)


def insert_rows(connection, pg_metadata: MetaData, table_name: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    connection.execute(pg_metadata.tables[table_name].insert(), rows)


def update_sequences(connection, pg_metadata: MetaData) -> list[str]:
    results: list[str] = []
    for table_name in APPLICATION_TABLES:
        table = pg_metadata.tables[table_name]
        if "id" not in table.c:
            continue
        max_id = connection.execute(select(func.max(table.c.id))).scalar_one()
        if max_id is None:
            results.append(f"{table_name}: vazia; sequence mantida")
            continue
        sequence_name = connection.execute(text("SELECT pg_get_serial_sequence(:table_name, 'id')"), {"table_name": table_name}).scalar_one()
        if not sequence_name:
            results.append(f"{table_name}: sem sequence serial detectada")
            continue
        connection.execute(text("SELECT setval(:sequence_name, :max_id, true)"), {"sequence_name": sequence_name, "max_id": max_id})
        next_value = connection.execute(text(f"SELECT nextval('{sequence_name}')")).scalar_one()
        connection.execute(text("SELECT setval(:sequence_name, :max_id, true)"), {"sequence_name": sequence_name, "max_id": max_id})
        results.append(f"{table_name}: max_id={max_id}; proximo={next_value}")
    return results


def validate_counts_match(sqlite_counts: dict[str, dict[str, int | None]], pg_counts: dict[str, dict[str, int | None]]) -> list[str]:
    issues: list[str] = []
    for table_name in APPLICATION_TABLES:
        if sqlite_counts[table_name]["count"] != pg_counts[table_name]["count"]:
            issues.append(
                f"{table_name}: SQLite={sqlite_counts[table_name]['count']} PostgreSQL={pg_counts[table_name]['count']}"
            )
    return issues


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    prefix = local[:1] if local else "*"
    return f"{prefix}***@{domain}"


def admin_summary(engine: Engine) -> list[str]:
    metadata = reflect(engine)
    if "admin_users" not in metadata.tables:
        return []
    table = metadata.tables["admin_users"]
    with engine.connect() as connection:
        rows = connection.execute(select(table.c.email, table.c.role, table.c.is_active).order_by(table.c.id)).all()
    return [f"{mask_email(row.email)}; role={row.role}; active={row.is_active}" for row in rows]


def checksum_summary(engine: Engine, table_names: list[str]) -> dict[str, dict[str, Any]]:
    metadata = reflect(engine)
    summary: dict[str, dict[str, Any]] = {}
    with engine.connect() as connection:
        for table_name in table_names:
            table = metadata.tables[table_name]
            nulls = {}
            for column in table.columns:
                nulls[column.name] = connection.execute(
                    select(func.count()).select_from(table).where(column.is_(None))
                ).scalar_one()
            summary[table_name] = {"nulls": nulls}
    return summary


def main() -> int:
    args = parse_args()
    source_path = resolve_source(args.source)
    sqlite = sqlite_engine(source_path)
    postgres = postgres_engine()

    print(f"Origem SQLite: {source_path}")
    print(f"Destino PostgreSQL: {safe_label(settings.database_url)}")
    validate_postgres_revision(postgres)

    sqlite_metadata = reflect(sqlite)
    pg_metadata = reflect(postgres)
    sqlite_counts = table_counts(sqlite, APPLICATION_TABLES)
    pg_counts = table_counts(postgres, APPLICATION_TABLES)
    print_inventory(sqlite_counts, pg_counts)
    ensure_destination_empty(pg_counts)

    fk_violations = sqlite_foreign_key_check(sqlite)
    if fk_violations:
        raise MigrationError(f"PRAGMA foreign_key_check encontrou violacoes: {fk_violations}")
    print("SQLite PRAGMA foreign_key_check: sem violacoes")

    orphans = sqlite_orphan_checks(sqlite)
    if orphans:
        raise MigrationError("Registros orfaos encontrados: " + "; ".join(orphans))
    print("SQLite orfaos: nenhum encontrado")

    schema_issues = compare_schema(sqlite_metadata, pg_metadata)
    if schema_issues:
        raise MigrationError("Incompatibilidade de schema: " + "; ".join(schema_issues))
    print("Compatibilidade de schema: tabelas e colunas esperadas presentes")

    total_records = sum(item["count"] or 0 for item in sqlite_counts.values())
    print("Ordem de migracao: " + " -> ".join(MIGRATION_ORDER))
    print(f"Total de registros planejados: {total_records}")

    all_rows: dict[str, list[dict[str, Any]]] = {}
    all_transformations: set[str] = set()
    for table_name in MIGRATION_ORDER:
        rows = load_rows(sqlite, sqlite_metadata, table_name)
        transformed, transformations = transform_rows(rows, pg_metadata.tables[table_name])
        all_rows[table_name] = transformed
        all_transformations.update(transformations)

    if all_transformations:
        print("Transformacoes planejadas:")
        for item in sorted(all_transformations):
            print(f"- {item}")
    else:
        print("Transformacoes planejadas: nenhuma")

    if args.dry_run:
        print("Dry run concluido sem escrita no PostgreSQL.")
        return 0

    print("Executando migracao real em transacao unica...")
    try:
        with postgres.begin() as connection:
            for table_name in MIGRATION_ORDER:
                insert_rows(connection, pg_metadata, table_name, all_rows[table_name])
                print(f"Inserido: {table_name} ({len(all_rows[table_name])})")
            sequence_results = update_sequences(connection, pg_metadata)
            print("Sequences:")
            for item in sequence_results:
                print(f"- {item}")
            final_pg_counts = table_counts_on_connection(connection, pg_metadata, APPLICATION_TABLES)
            count_issues = validate_counts_match(sqlite_counts, final_pg_counts)
            if count_issues:
                raise MigrationError("Divergencia antes do commit: " + "; ".join(count_issues))
            print("Contagens antes do commit: compativeis com SQLite")
    except SQLAlchemyError as exc:
        raise MigrationError(f"Migracao revertida por erro SQLAlchemy: {exc.__class__.__name__}") from exc

    final_pg_counts = table_counts(postgres, APPLICATION_TABLES)
    count_issues = validate_counts_match(sqlite_counts, final_pg_counts)
    if count_issues:
        raise MigrationError("Divergencia apos commit: " + "; ".join(count_issues))
    print("Contagens apos migracao: compativeis com SQLite")
    print("Administradores migrados:")
    admins = admin_summary(postgres)
    print(f"Quantidade: {len(admins)}")
    for item in admins:
        print(f"- {item}")
    checksum_summary(postgres, APPLICATION_TABLES)
    print("Migracao concluida com sucesso.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        raise SystemExit(1)
