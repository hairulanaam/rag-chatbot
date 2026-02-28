"""
Dashboard API routes for managing chatbot documents and indexing.
"""
import os
import secrets
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import DATA_DIR, DASHBOARD_SECRET_KEY
from src.database import verify_user, change_password, init_db, get_query_logs, get_query_stats, clear_query_logs
from src.ingestion import (
    index_single_document,
    reindex_document,
    delete_document_vectors,
    get_index_stats,
    run_ingestion,
    get_markdown_files,
    process_documents,
    upload_to_pinecone,
)

router = APIRouter()

# In-memory session store: {token: {"username": str, "created_at": datetime}}
_sessions = {}


# ============================================================
# Pydantic Models
# ============================================================

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class DocumentContent(BaseModel):
    content: str
    filename: Optional[str] = None


# ============================================================
# Auth Helpers
# ============================================================

def get_current_user(request: Request) -> str:
    """Extract and validate session token from request."""
    token = request.cookies.get("session_token")
    if not token or token not in _sessions:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi. Silakan login.")
    return _sessions[token]["username"]


# ============================================================
# Auth Endpoints
# ============================================================

@router.post("/api/auth/login")
async def login(data: LoginRequest):
    """Login and create session."""
    if not verify_user(data.username, data.password):
        raise HTTPException(status_code=401, detail="Username atau password salah")
    
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "username": data.username,
        "created_at": datetime.now()
    }
    
    response = JSONResponse(content={"success": True, "message": "Login berhasil"})
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="strict",
        max_age=86400  # 24 hours
    )
    return response


@router.post("/api/auth/logout")
async def logout(request: Request):
    """Logout and destroy session."""
    token = request.cookies.get("session_token")
    if token and token in _sessions:
        del _sessions[token]
    
    response = JSONResponse(content={"success": True, "message": "Logout berhasil"})
    response.delete_cookie("session_token")
    return response


@router.get("/api/auth/check")
async def check_auth(username: str = Depends(get_current_user)):
    """Check if user is authenticated."""
    return {"authenticated": True, "username": username}


@router.post("/api/auth/change-password")
async def api_change_password(data: ChangePasswordRequest, username: str = Depends(get_current_user)):
    """Change user password."""
    result = change_password(username, data.old_password, data.new_password)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


# ============================================================
# Document Endpoints
# ============================================================

@router.get("/api/documents")
async def list_documents(username: str = Depends(get_current_user)):
    """List all markdown documents in the data directory."""
    data_path = Path(DATA_DIR)
    
    if not data_path.exists():
        return {"documents": []}
    
    documents = []
    for f in sorted(data_path.glob("*.md")):
        stat = f.stat()
        documents.append({
            "filename": f.name,
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "size_display": _format_size(stat.st_size),
        })
    
    return {"documents": documents}


@router.get("/api/documents/{filename}")
async def get_document(filename: str, username: str = Depends(get_current_user)):
    """Read content of a specific markdown document."""
    file_path = Path(DATA_DIR) / filename
    
    if not file_path.exists() or not file_path.suffix == ".md":
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    
    # Security: prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nama file tidak valid")
    
    content = file_path.read_text(encoding="utf-8")
    stat = file_path.stat()
    
    return {
        "filename": filename,
        "content": content,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/api/documents")
async def create_document(data: DocumentContent, username: str = Depends(get_current_user)):
    """Create a new markdown document."""
    if not data.filename:
        raise HTTPException(status_code=400, detail="Nama file diperlukan")
    
    # Sanitize filename
    filename = data.filename.strip()
    if not filename.endswith(".md"):
        filename += ".md"
    
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nama file tidak valid")
    
    file_path = Path(DATA_DIR) / filename
    
    if file_path.exists():
        raise HTTPException(status_code=409, detail="File sudah ada. Gunakan PUT untuk mengedit.")
    
    # Create data directory if it doesn't exist
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    
    file_path.write_text(data.content, encoding="utf-8")
    
    return {"success": True, "message": f"Dokumen '{filename}' berhasil dibuat", "filename": filename}


@router.put("/api/documents/{filename}")
async def update_document(filename: str, data: DocumentContent, username: str = Depends(get_current_user)):
    """Update content of an existing document."""
    file_path = Path(DATA_DIR) / filename
    
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nama file tidak valid")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    
    file_path.write_text(data.content, encoding="utf-8")
    
    return {"success": True, "message": f"Dokumen '{filename}' berhasil diperbarui"}


@router.delete("/api/documents/{filename}")
async def delete_document(filename: str, username: str = Depends(get_current_user)):
    """Delete a document and its associated vectors from Pinecone."""
    file_path = Path(DATA_DIR) / filename
    
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nama file tidak valid")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    
    file_prefix = file_path.stem
    
    # Delete vectors from Pinecone
    vector_result = delete_document_vectors(file_prefix)
    
    # Delete file
    file_path.unlink()
    
    return {
        "success": True,
        "message": f"Dokumen '{filename}' dan {vector_result.get('deleted_count', 0)} vectors berhasil dihapus",
        "vectors_deleted": vector_result.get("deleted_count", 0),
    }


# ============================================================
# Indexing Endpoints
# ============================================================

@router.post("/api/documents/{filename}/index")
async def index_document(filename: str, username: str = Depends(get_current_user)):
    """Index or re-index a specific document to Pinecone."""
    file_path = Path(DATA_DIR) / filename
    
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nama file tidak valid")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    
    result = reindex_document(str(file_path))
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Gagal mengindex dokumen"))
    
    return {
        "success": True,
        "message": f"Dokumen '{filename}' berhasil di-index ({result.get('chunks_count', 0)} chunks)",
        "chunks_count": result.get("chunks_count", 0),
        "deleted_count": result.get("deleted_count", 0),
    }


@router.post("/api/index/all")
async def index_all_documents(username: str = Depends(get_current_user)):
    """Re-index all documents in the data directory."""
    try:
        file_paths = get_markdown_files(DATA_DIR)
        
        if not file_paths:
            return {"success": True, "message": "Tidak ada dokumen untuk di-index", "total_chunks": 0}
        
        total_chunks = 0
        results = []
        
        for file_path in file_paths:
            result = reindex_document(file_path)
            results.append({
                "file": Path(file_path).name,
                "success": result.get("success", False),
                "chunks_count": result.get("chunks_count", 0),
            })
            total_chunks += result.get("chunks_count", 0)
        
        return {
            "success": True,
            "message": f"Berhasil mengindex {len(file_paths)} dokumen ({total_chunks} chunks total)",
            "total_chunks": total_chunks,
            "details": results,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/index/status")
async def index_status(username: str = Depends(get_current_user)):
    """Get Pinecone index statistics."""
    stats = get_index_stats()
    
    if not stats.get("success"):
        raise HTTPException(status_code=500, detail=stats.get("error", "Gagal mengambil status index"))
    
    # Also count local documents
    data_path = Path(DATA_DIR)
    local_docs = len(list(data_path.glob("*.md"))) if data_path.exists() else 0
    
    stats["local_document_count"] = local_docs
    return stats


# ============================================================
# Upload Endpoint (for raw files → LlamaParse → markdown)
# ============================================================

@router.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    username: str = Depends(get_current_user),
):
    """
    Upload a raw file (PDF, image, etc.) and convert to markdown using LlamaParse.
    The resulting markdown file is saved to data/ directory.
    """
    from src.document_parser import get_parser, SUPPORTED_EXTENSIONS
    
    # Check file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Format '{file_ext}' tidak didukung. Format yang didukung: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    
    # Save uploaded file temporarily
    temp_dir = Path(DATA_DIR).parent / "temp_uploads"
    temp_dir.mkdir(exist_ok=True)
    temp_path = temp_dir / file.filename
    
    try:
        content = await file.read()
        temp_path.write_bytes(content)
        
        # Parse with LlamaParse
        parser = get_parser()
        documents = parser.load_data(str(temp_path))
        
        if not documents:
            raise HTTPException(status_code=422, detail="Tidak ada konten yang bisa diekstrak dari file")
        
        # Combine and save as markdown
        markdown_content = "\n\n".join(doc.text for doc in documents if doc.text)
        
        output_filename = Path(file.filename).stem + ".md"
        output_path = Path(DATA_DIR) / output_filename
        output_path.write_text(markdown_content, encoding="utf-8")
        
        return {
            "success": True,
            "message": f"File berhasil diupload dan dikonversi ke '{output_filename}'",
            "filename": output_filename,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal memproses file: {str(e)}")
    finally:
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()
        if temp_dir.exists() and not any(temp_dir.iterdir()):
            temp_dir.rmdir()


# ============================================================
# Query Log Endpoints
# ============================================================

@router.get("/api/logs")
async def api_get_logs(
    limit: int = 50,
    offset: int = 0,
    username: str = Depends(get_current_user),
):
    """Get query logs with pagination."""
    return get_query_logs(limit=limit, offset=offset)


@router.get("/api/logs/stats")
async def api_get_log_stats(username: str = Depends(get_current_user)):
    """Get query statistics for chart display."""
    return get_query_stats()


@router.delete("/api/logs/clear")
async def api_clear_logs(username: str = Depends(get_current_user)):
    """Delete all query logs."""
    return clear_query_logs()


# ============================================================
# Helpers
# ============================================================

def _format_size(size_bytes: int) -> str:
    """Format file size to human readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
