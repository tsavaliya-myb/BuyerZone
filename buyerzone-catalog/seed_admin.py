import asyncio
from passlib.context import CryptContext
from app.core.database import AsyncSessionLocal
from app.models.admin_user import AdminUser

pwd_context = CryptContext(schemes=["sha256_crypt"])


async def seed():
    pwd = pwd_context.hash("admin")
    async with AsyncSessionLocal() as s:
        s.add(AdminUser(username="admin", email="admin@bz.com", hashed_password=pwd))
        await s.commit()
    print("Admin user created — username: admin / password: admin")


asyncio.run(seed())
