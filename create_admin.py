#!/usr/bin/env python
"""Создать пользователя админки.

Использование:
    python create_admin.py --username admin --password secret --role admin
Без аргументов спросит интерактивно.
"""
import argparse
import asyncio
import getpass

from app.db.session import async_session_maker
from app.models.enums import UserRole
from app.schemas.auth import UserCreate
from app.services import user_service


async def main(username: str, password: str, role: str) -> None:
    async with async_session_maker() as db:
        existing = await user_service.get_by_username(db, username)
        if existing:
            print(f"Пользователь '{username}' уже существует — обновляю пароль/роль.")
            from app.schemas.auth import UserUpdate

            await user_service.update(
                db, existing, UserUpdate(password=password, role=UserRole(role), is_active=True)
            )
        else:
            await user_service.create(
                db, UserCreate(username=username, password=password, role=UserRole(role))
            )
            print(f"Создан пользователь '{username}' с ролью '{role}'.")
        await db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--role", default="admin", choices=[r.value for r in UserRole])
    args = parser.parse_args()

    username = args.username or input("Логин: ").strip()
    password = args.password or getpass.getpass("Пароль: ")
    asyncio.run(main(username, password, args.role))
