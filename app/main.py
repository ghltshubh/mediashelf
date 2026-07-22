"""FastAPI app: API + static SPA + nightly availability refresh."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import accounts, api, settings_store
from app.db import Base, get_engine, session_factory
from app.seed import merge_duplicate_services, seed_services
from app.services import backups

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

WEB_DIST = Path(__file__).parent / "web" / "dist"


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Corruption check BEFORE the engine touches the file; restore from the
        # latest good backup if needed and tell the user what happened.
        restore_notice = backups.check_and_restore_on_boot()
        Base.metadata.create_all(get_engine())
        with session_factory()() as db:
            seed_services(db)
            merge_duplicate_services(db)
            if restore_notice:
                settings_store.set_setting(db, "restore_notice", restore_notice)
            has_key = bool(settings_store.get_setting(db, "tmdb_api_key"))
        scheduler = AsyncIOScheduler()
        # Nightly DB backup at 03:45, availability refresh at 04:15 local,
        # library refresh every 12h (runs in the scheduler's thread pool).
        scheduler.add_job(backups.create_backup, CronTrigger(hour=3, minute=45))
        scheduler.add_job(api._sync_job, CronTrigger(hour=4, minute=15))
        scheduler.add_job(accounts.scheduled_sync_all, CronTrigger(hour="5,17", minute=0))

        async def resume_paused_migrations() -> None:
            """Quota-paused jobs auto-resume after the LA-midnight reset (plan §4.6)."""
            import asyncio as _asyncio

            from app.services import migrate as migrate_service
            with session_factory()() as db2:
                for job_id in migrate_service.due_resumes(db2):
                    _asyncio.get_running_loop().create_task(
                        _asyncio.to_thread(migrate_service.run_job, job_id))

        scheduler.add_job(resume_paused_migrations, CronTrigger(minute="*/30"))
        scheduler.start()
        await resume_paused_migrations()  # …and on launch
        if has_key:
            api.schedule_sync()
        yield
        scheduler.shutdown(wait=False)

    app = FastAPI(title="MediaShelf", lifespan=lifespan)
    app.include_router(api.router)
    app.include_router(accounts.router)

    if WEB_DIST.exists():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            file = WEB_DIST / path
            if path and file.is_file():
                return FileResponse(file)
            return FileResponse(WEB_DIST / "index.html")

    return app


app = create_app()
