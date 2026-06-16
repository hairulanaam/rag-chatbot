import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from chainlit.utils import mount_chainlit
from src.dashboard_api import router as dashboard_router
from src.database import init_db, sync_local_to_cloud
from src.config import DATA_DIR

init_db()
sync_local_to_cloud(DATA_DIR)

app = FastAPI(title="Chatbot Layanan Informasi Sekolah")

# Route
app.include_router(dashboard_router, prefix="/dashboard")
app.mount("/dashboard", StaticFiles(directory="dashboard_static", html=True), name="dashboard_static")
app.mount("/public", StaticFiles(directory="public"), name="public_assets")

mount_chainlit(app=app, target="app.py", path="/chat")


if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("Starting Server", flush=True)
    print("=" * 60, flush=True)
    print("Chatbot: http://localhost:8000/chat", flush=True)
    print("Dashboard: http://localhost:8000/dashboard", flush=True)
    print("=" * 60, flush=True)

    uvicorn.run(
        "main_server:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
