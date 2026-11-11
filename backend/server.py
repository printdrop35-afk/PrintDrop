import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
from lib.db import client, db, ensure_indexes
from lib.authz import now_utc
from lib.storage import delete_file
from lib.notify import check_agents_offline, process_notification_jobs
from lib.printing import expire_stale_leases
from migrations.runner import run_migrations
from routers.counter import expire_copy_commands
from routers import admin, agent, ai_docs, org_profile, auth, billing, printers, dashboard, devices, public, reports, site, counter

logger = logging.getLogger(__name__)


async def cleanup_orphan_uploads() -> None:
    """Background job: delete uploaded documents never attached to an order within 24h."""
    while True:
        try:
            cutoff = now_utc() - timedelta(hours=24)
            async for doc in db.documents.find({"status": "uploaded", "created_at": {"$lt": cutoff}}, {"_id": 0}):
                await delete_file(doc["storage_key"])
                await db.documents.delete_one({"id": doc["id"]})
        except Exception as exc:  # never let the job die
            logger.error("cleanup_orphan_uploads: %s", exc)
        await asyncio.sleep(1800)


async def job_worker() -> None:
    """Background job processing: notification delivery (with retries) and print-lease expiry."""
    while True:
        try:
            await process_notification_jobs()
            await expire_stale_leases()
            await check_agents_offline()
            await expire_copy_commands()
        except Exception as exc:
            logger.error("job_worker: %s", exc)
        await asyncio.sleep(5)


# Startup runs before the yield, shutdown after it. Add your own setup/teardown here.
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.index_task = asyncio.create_task(ensure_indexes())
    await run_migrations()  # idempotent, versioned (migrations collection)  # background: a big index build must not block boot
    app.state.cleanup_task = asyncio.create_task(cleanup_orphan_uploads())
    app.state.worker_task = asyncio.create_task(job_worker())
    yield
    for task in (app.state.index_task, app.state.cleanup_task, app.state.worker_task):
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    client.close()


# Create the main app without a prefix
app = FastAPI(lifespan=lifespan, title="PrintDrop API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"message": "PrintDrop API", "stage": 1}


api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(public.router)
api_router.include_router(admin.router)
api_router.include_router(devices.router)
api_router.include_router(agent.router)
api_router.include_router(reports.router)
api_router.include_router(billing.router)
api_router.include_router(printers.router)
api_router.include_router(site.router)
api_router.include_router(ai_docs.router)
api_router.include_router(org_profile.router)
api_router.include_router(counter.router)
api_router.include_router(counter.public_router)

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
