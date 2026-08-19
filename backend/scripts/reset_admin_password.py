import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import AdminUser, utc_now
from app.security import password_hash, validate_auth_email, validate_password_strength, verify_password


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Redefine a senha de um administrador existente.")
    parser.add_argument("--email", required=True, help="E-mail do administrador.")
    return parser.parse_args()


def mask_email(email: str) -> str:
    local, separator, domain = email.partition("@")
    if not separator:
        return "***"
    return f"{local[:1]}***@{domain}"


def confirmation_is_positive(value: str) -> bool:
    return value.strip().casefold() in {"s", "sim"}


def get_admin_by_email(db, email: str) -> AdminUser:
    users = db.query(AdminUser).filter(AdminUser.email == email).all()
    if not users:
        raise ValueError("Administrador nao encontrado.")
    if len(users) > 1:
        raise ValueError("Mais de um administrador encontrado para este e-mail.")
    return users[0]


def reset_admin_password(db, *, email: str, password: str, confirmation: str, confirmed: bool) -> AdminUser:
    user = get_admin_by_email(db, email)
    if not confirmed:
        raise ValueError("Redefinicao cancelada.")
    old_hash = user.password_hash
    validate_password_strength(password, confirmation, email=user.email, name=user.name, current_hash=old_hash)
    user.password_hash = password_hash(password)
    user.session_version += 1
    user.updated_at = utc_now()
    db.flush()
    if user.password_hash == old_hash:
        raise ValueError("Hash nao foi atualizado.")
    if user.password_hash == password:
        raise ValueError("Hash invalido.")
    if not verify_password(password, user.password_hash):
        raise ValueError("Nova senha nao foi validada.")
    if verify_password(password + "x", user.password_hash):
        raise ValueError("Senha incorreta foi aceita indevidamente.")
    return user


def main() -> int:
    args = parse_args()
    try:
        email = validate_auth_email(args.email)
        with SessionLocal() as db:
            try:
                user = get_admin_by_email(db, email)
                print("Administrador encontrado:")
                print(f"E-mail: {mask_email(user.email)}")
                print(f"Role: {user.role}")
                print(f"Ativo: {'sim' if user.is_active else 'nao'}")
                password = getpass.getpass("Nova senha: ")
                confirmation = getpass.getpass("Confirme a nova senha: ")
                answer = input("Confirmar redefinicao? [s/N]: ")
                reset_admin_password(
                    db,
                    email=email,
                    password=password,
                    confirmation=confirmation,
                    confirmed=confirmation_is_positive(answer),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("Senha redefinida com sucesso.")
    print("Hash atualizado: sim")
    print("Nova senha validada: sim")
    print("Senha incorreta rejeitada: sim")
    print("Administrador preservado: sim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
