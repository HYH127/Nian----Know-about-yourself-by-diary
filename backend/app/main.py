import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, close_db
from app.routers import diary as diary_router
from app.routers import chat as chat_router
from app.routers import timeline as timeline_router
from app.routers import profile as profile_router
from app.routers import import_data as import_router
from app.routers import knowledge as knowledge_router
from app.routers import monitor as monitor_router
from app.routers import insight as insight_router
from app.routers import quicknote as quicknote_router


def _configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


_configure_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("应用启动，初始化数据库")
    await init_db()
    logger.info("数据库初始化完成")
    import asyncio
    from app.services.compiler import start_compile_scheduler
    asyncio.create_task(start_compile_scheduler())
    logger.info("编译调度器已启动")

    # 预加载 reranker 模型，避免首次 both 模式对话时 5-10s 加载延迟
    from app.services.reranker import _load_model
    asyncio.create_task(asyncio.to_thread(_load_model))
    logger.info("reranker 模型预加载已启动（后台）")

    yield
    logger.info("应用关闭，清理数据库连接")
    await close_db()
    logger.info("数据库连接已关闭")


app = FastAPI(
    title="念念 - 个人数字镜像 Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router.router)
app.include_router(diary_router.router)
app.include_router(timeline_router.router)
app.include_router(profile_router.router)
app.include_router(import_router.router)
app.include_router(knowledge_router.router)
app.include_router(monitor_router.router)
app.include_router(insight_router.router)
app.include_router(quicknote_router.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

