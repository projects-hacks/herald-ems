"""Serve one medic build and the standalone camera accessory; never substitute a legacy dashboard."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles


def mount_frontend(app: FastAPI, root: Path) -> None:
    @app.get("/capture.html", include_in_schema=False)
    async def capture_page():
        return FileResponse(root / "web" / "capture.html")

    @app.get("/classic/capture.html", include_in_schema=False)
    async def old_capture():
        return RedirectResponse("/capture.html", status_code=308)

    @app.get("/classic/", include_in_schema=False)
    @app.get("/classic", include_in_schema=False)
    async def old_dashboard():
        return RedirectResponse("/", status_code=308)

    # Explicit files prevent the camera accessory route from exposing unrelated assets.
    @app.get("/capture-assets/continuous.js", include_in_schema=False)
    async def capture_script():
        return FileResponse(root / "web" / "continuous.js", media_type="text/javascript")

    @app.get("/capture-assets/continuous.css", include_in_schema=False)
    async def capture_style():
        return FileResponse(root / "web" / "continuous.css", media_type="text/css")

    dist = root / "ui" / "dist"
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="medic")
    else:
        @app.get("/", include_in_schema=False)
        async def missing_build():
            return HTMLResponse(
                "<h1>Herald interface is not built</h1>"
                "<p>In <code>ui/</code>, run <code>npm ci</code> and <code>npm run build</code>, "
                "then restart this application. API and camera routes remain available.</p>",
                status_code=503,
            )
