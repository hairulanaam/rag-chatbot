"""
Dashboard API routes for managing chatbot documents and indexing.
"""
import os
import jwt
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import DASHBOARD_SECRET_KEY
from src.database import (
    verify_user, change_password,
    get_query_logs, get_query_stats, clear_query_logs, get_daily_stats, get_topic_stats, resolve_query_log,
    save_document, delete_document_record, list_documents_db, get_document_db,
    document_exists, get_all_documents_content, get_document_count,
)
from src.ingestion import (
    reindex_document,
    delete_document_vectors,
    get_index_stats,
    check_documents_indexed,
)

router = APIRouter()

# JWT Configuration
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 3


# ============================================================
# Pydantic Models
# ============================================================

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    new_password: str

class DocumentContent(BaseModel):
    content: str
    filename: Optional[str] = None


# ============================================================
# Auth Helpers (JWT)
# ============================================================

def _create_token(username: str) -> str:
    """Create a JWT token for the given username."""
    payload = {
        "sub": username,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
    }
    return jwt.encode(payload, DASHBOARD_SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_current_user(request: Request) -> str:
    """Extract and validate JWT token from request cookie."""
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi. Silakan login.")
    
    try:
        payload = jwt.decode(token, DASHBOARD_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session kedaluwarsa. Silakan login kembali.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token tidak valid. Silakan login kembali.")


# ============================================================
# Auth Endpoints
# ============================================================

@router.post("/api/auth/login")
async def login(data: LoginRequest):
    """Login and create JWT token."""
    if not verify_user(data.username, data.password):
        raise HTTPException(status_code=401, detail="Username atau password salah")
    
    token = _create_token(data.username)
    
    response = JSONResponse(content={"success": True, "message": "Login berhasil"})
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="strict",
        max_age=JWT_EXPIRATION_HOURS * 3600
    )
    return response


@router.post("/api/auth/logout")
async def logout():
    """Logout by clearing the JWT cookie."""
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
    result = change_password(username, data.new_password)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


# ============================================================
# Document Helpers
# ============================================================

def _validate_filename(filename: str):
    """Validate filename format."""
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nama file tidak valid")
    if not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Hanya file .md yang diperbolehkan")


# ============================================================
# Document Endpoints
# ============================================================

@router.get("/api/documents")
async def list_documents(username: str = Depends(get_current_user)):
    """List all markdown documents from Turso."""
    docs = list_documents_db()
    for doc in docs:
        doc["size_display"] = _format_size(doc["size_bytes"])
        doc["modified_at"] = doc.pop("updated_at", "")
    return {"documents": docs}


@router.get("/api/documents/indexed")
async def get_indexed_status(username: str = Depends(get_current_user)):
    """Check which documents are indexed in Pinecone."""
    docs = list_documents_db()
    if not docs:
        return {"indexed": {}}
    file_stems = [Path(d["filename"]).stem for d in docs]
    return check_documents_indexed(file_stems)


@router.get("/api/documents/{filename}")
async def get_document(filename: str, username: str = Depends(get_current_user)):
    """Read content of a specific markdown document from Turso."""
    _validate_filename(filename)
    doc = get_document_db(filename)
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    
    return {
        "filename": doc["filename"],
        "content": doc["content"],
        "size_bytes": doc["size_bytes"],
        "modified_at": doc["updated_at"],
    }


@router.post("/api/documents")
async def create_document(data: DocumentContent, username: str = Depends(get_current_user)):
    """Create a new markdown document in Turso."""
    if not data.filename:
        raise HTTPException(status_code=400, detail="Nama file diperlukan")
    
    filename = data.filename.strip()
    if not filename.endswith(".md"):
        filename += ".md"
    
    _validate_filename(filename)
    
    if document_exists(filename):
        raise HTTPException(status_code=409, detail="File sudah ada. Gunakan PUT untuk mengedit.")
    
    save_document(filename, data.content)
    
    return {"success": True, "message": f"Dokumen '{filename}' berhasil dibuat", "filename": filename}


@router.put("/api/documents/{filename}")
async def update_document(filename: str, data: DocumentContent, username: str = Depends(get_current_user)):
    """Update content of an existing document in Turso."""
    _validate_filename(filename)
    
    if not document_exists(filename):
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    
    save_document(filename, data.content)
    
    return {"success": True, "message": f"Dokumen '{filename}' berhasil diperbarui"}


@router.delete("/api/documents/{filename}")
async def delete_document(filename: str, username: str = Depends(get_current_user)):
    """Delete a document and its associated vectors from Pinecone."""
    _validate_filename(filename)
    
    if not document_exists(filename):
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    
    file_prefix = Path(filename).stem
    
    # Delete vectors from Pinecone
    vector_result = delete_document_vectors(file_prefix)
    
    # Delete from Turso
    delete_document_record(filename)
    
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
    _validate_filename(filename)
    doc = get_document_db(filename)
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    
    # Write temp file for indexing (ingestion reads from file)
    import tempfile
    temp_dir = Path(tempfile.mkdtemp())
    temp_file = temp_dir / filename
    temp_file.write_text(doc["content"], encoding="utf-8")
    
    try:
        result = reindex_document(str(temp_file))
    finally:
        temp_file.unlink(missing_ok=True)
        temp_dir.rmdir()
    
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
    """Re-index all documents from Turso."""
    try:
        all_docs = get_all_documents_content()
        
        if not all_docs:
            return {"success": True, "message": "Tidak ada dokumen untuk di-index", "total_chunks": 0}
        
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        total_chunks = 0
        results = []
        
        try:
            for doc in all_docs:
                temp_file = temp_dir / doc["filename"]
                temp_file.write_text(doc["content"], encoding="utf-8")
                
                result = reindex_document(str(temp_file))
                results.append({
                    "file": doc["filename"],
                    "success": result.get("success", False),
                    "chunks_count": result.get("chunks_count", 0),
                })
                total_chunks += result.get("chunks_count", 0)
                
                temp_file.unlink(missing_ok=True)
        finally:
            # Clean up remaining temp files
            for f in temp_dir.glob("*"):
                f.unlink(missing_ok=True)
            temp_dir.rmdir()
        
        return {
            "success": True,
            "message": f"Berhasil mengindex {len(all_docs)} dokumen ({total_chunks} chunks total)",
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
    
    stats["local_document_count"] = get_document_count()
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
    import tempfile
    temp_dir = Path(tempfile.mkdtemp())
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
        # Save to Turso (single source of truth)
        save_document(output_filename, markdown_content)
        
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


@router.get("/api/logs/daily")
async def api_get_daily_stats(username: str = Depends(get_current_user)):
    """Get query count per day for the last 7 days."""
    return get_daily_stats(days=7)


@router.get("/api/logs/topics")
async def api_get_topic_stats(username: str = Depends(get_current_user)):
    """Get query frequency grouped by top_source document."""
    return get_topic_stats()


@router.delete("/api/logs/clear")
async def api_clear_logs(username: str = Depends(get_current_user)):
    """Delete all query logs."""
    return clear_query_logs()


@router.patch("/api/logs/{log_id}/resolve")
async def api_resolve_log(log_id: int, username: str = Depends(get_current_user)):
    """Mark a query log as resolved (knowledge added)."""
    result = resolve_query_log(log_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return result


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
