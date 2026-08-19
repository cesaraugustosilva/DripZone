import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import engine_options_for_url


def safe_database_label(url_text: str) -> str:
    url = make_url(url_text)
    backend = url.get_backend_name()
    host = url.host or "local"
    database = url.database or "(sem nome)"
    return f"backend={backend}; host={host}; database={database}"


def main() -> int:
    try:
        engine = create_engine(settings.database_url, **engine_options_for_url(settings.database_url))
        with engine.connect() as connection:
            value = connection.execute(text("SELECT 1")).scalar_one()
        if value != 1:
            print("Conexao falhou: SELECT 1 retornou valor inesperado.")
            return 1
    except SQLAlchemyError as exc:
        print(f"Conexao falhou: {exc.__class__.__name__}.")
        return 1

    print(f"Conexao OK: {safe_database_label(settings.database_url)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
