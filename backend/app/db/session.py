"""数据库引擎与异步 Session 生命周期管理。

API 请求通过 ``get_session`` 获得独立 Session；后台 Mock Runner 则直接使用
``async_session_factory`` 创建自己的 Session，避免复用已经随请求结束的连接。
"""

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import Pool

from app.core.config import get_settings


settings = get_settings()
# pool_pre_ping 会在复用连接前检查其有效性，适合本地 Docker 数据库重启场景。
engine = create_async_engine(settings.database_url, pool_pre_ping=True)

# SQLite 默认不启用外键约束；测试使用 SQLite 时需要显式开启。
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    # 提交后仍允许读取对象属性，便于 Repository 返回刚写入的实体。
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """为单个 FastAPI 请求提供一个异步数据库 Session。"""

    async with async_session_factory() as session:
        yield session
