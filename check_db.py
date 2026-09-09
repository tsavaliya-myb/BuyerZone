import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import sys

# add bz-core to path
sys.path.append('e:\\BuyerZone\\bz-core')

async def main():
    db_url = "postgresql+asyncpg://neondb_owner:npg_tb1HrJF7PyXv@ep-lucky-sea-a13apcep-pooler.ap-southeast-1.aws.neon.tech/buyerzone?ssl=require"
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        result = await session.execute(text("""
            SELECT id, chat_id, chat_name, platform, chat_type, phone
            FROM monitored_chats
            WHERE chat_type = 'wa_group'
            ORDER BY chat_name
        """))
        rows = result.fetchall()
        for r in rows:
            print(f"ID={r.id} | CHAT_ID={r.chat_id} | NAME={r.chat_name} | PLATFORM={r.platform} | PHONE={r.phone}")
            
if __name__ == "__main__":
    asyncio.run(main())
