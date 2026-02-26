import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from chainlit.utils import mount_chainlit
from src.dashboard_api import router as dashboard_router
from src.database import init_db

# Initialize database
init_db()

app = FastAPI(title="Chatbot Layanan Informasi Sekolah")

# Route dashboard
app.include_router(dashboard_router, prefix="/admin")

# 2. Dashboard static files (/admin/...)
app.mount("/admin", StaticFiles(directory="dashboard_static", html=True), name="dashboard_static")

# 3. Chainlit chatbot (/chat/...)
mount_chainlit(app=app, target="app.py", path="/chat")


if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("🚀 Starting Server", flush=True)
    print("=" * 60, flush=True)
    print("  📱 Chatbot  : http://localhost:8000/chat", flush=True)
    print("  🔧 Dashboard: http://localhost:8000/admin", flush=True)
    print("=" * 60, flush=True)

    uvicorn.run(
        "main_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
