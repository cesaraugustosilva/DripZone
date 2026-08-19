import argparse
import getpass
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import AdminUser
from app.security import password_hash, validate_auth_email, validate_password_strength


Role = Literal["owner", "admin", "editor"]
VALID_ROLES = ("owner", "admin", "editor")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cria um administrador local do DripZone.")
    parser.add_argument("--name", required=True, help="Nome do administrador.")
    parser.add_argument("--email", required=True, help="E-mail do administrador.")
    parser.add_argument("--role", choices=VALID_ROLES, default="owner", help="Papel administrativo.")
    return parser.parse_args()


def create_admin(name: str, email: str, role: Role, password: str) -> int:
    with SessionLocal() as db:
        try:
            if db.query(AdminUser).filter(AdminUser.email == email).first():
                raise ValueError("Ja existe um administrador com este e-mail.")
            user = AdminUser(name=name, email=email, password_hash=password_hash(password), role=role, is_active=True)
            db.add(user)
            db.commit()
            db.refresh(user)
            return user.id
        except Exception:
            db.rollback()
            raise


def main() -> int:
    args = parse_args()
    name = args.name.strip()
    role = args.role
    try:
        if not name:
            raise ValueError("Nome e obrigatorio.")
        email = validate_auth_email(args.email)
        password = getpass.getpass("Senha: ")
        confirmation = getpass.getpass("Confirme a senha: ")
        validate_password_strength(password, confirmation, email=email, name=name)
        user_id = create_admin(name, email, role, password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Administrador criado com sucesso. id={user_id}; role={role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
