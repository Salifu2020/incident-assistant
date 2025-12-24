# Document Versioning API Integration Patch

This file contains the exact changes needed to integrate document versioning into `src/api.py`.

## Changes Required

### 1. Add Import Statement (After line 15)

**Location:** After `from .dependencies import processor, assistant`

**Add:**
```python
from .versioning import DocumentVersionManager
```

**Current code:**
```python
from .dependencies import processor, assistant
from .models import (
```

**Should become:**
```python
from .dependencies import processor, assistant
from .versioning import DocumentVersionManager
from .models import (
```

---

### 2. Add Version Models to Imports (Line 35)

**Location:** In the models import list, after `ProfileResponse`

**Current code:**
```python
    UserPreferences, ProfileUpdateRequest, PreferencesUpdateRequest, ProfileResponse
)
```

**Should become:**
```python
    UserPreferences, ProfileUpdateRequest, PreferencesUpdateRequest, ProfileResponse,
    DocumentVersionInfo, DocumentVersion, RestoreVersionRequest
)
```

---

### 3. Add Version Creation in Upload Endpoint (Around line 1705)

**Location:** In the `upload_file` function, after the file write error handling and before `# Schedule background task`

**Find:**
```python
            raise HTTPException(
                status_code=500,
                detail=f"Server error: failed to save file - {str(e)}"
            )
        
        # Schedule background task
        background_tasks.add_task(process_and_move_file, source_path, ext)
```

**Replace with:**
```python
            raise HTTPException(
                status_code=500,
                detail=f"Server error: failed to save file - {str(e)}"
            )
        
        # Create document version after file is written
        try:
            version_entry = DocumentVersionManager.create_version(
                filename=filename,
                file_path=source_path,
                user_id=current_user.id,
                username=current_user.username,
                file_size=file_size
            )
            logger.info(f"📦 Created version {version_entry.get('version')} for {filename}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to create version for {filename}: {e}")
            # Continue with upload even if versioning fails
        
        # Schedule background task
        background_tasks.add_task(process_and_move_file, source_path, ext)
```

---

### 4. Add Version Info to Document Listing (Around line 1175)

**Location:** In the `list_documents` function, after `total_chunks = processor.collection.count()`

**Find:**
```python
        documents = processor.list_documents()
        total_chunks = processor.collection.count()
        
        return {
            "documents": documents,
            "total_documents": len(documents),
            "total_chunks": total_chunks
        }
```

**Replace with:**
```python
        documents = processor.list_documents()
        total_chunks = processor.collection.count()
        
        # Add version information to each document
        for doc in documents:
            try:
                version_info = DocumentVersionManager.get_version_info(doc["filename"])
                if version_info:
                    current_version = DocumentVersionManager.get_current_version(doc["filename"])
                    doc["version"] = current_version.get("version") if current_version else None
                    doc["version_count"] = len(version_info.get("versions", []))
            except Exception as e:
                logger.warning(f"Error getting version info for {doc['filename']}: {e}")
                doc["version"] = None
                doc["version_count"] = None
        
        return {
            "documents": documents,
            "total_documents": len(documents),
            "total_chunks": total_chunks
        }
```

---

### 5. Add Version Management Endpoints (At the end of the file, after line 1884)

**Location:** After the last endpoint (performance stats endpoint)

**Add this entire section:**
```python

# Document Version Management Endpoints
@app.get("/documents/{filename}/versions", response_model=DocumentVersionInfo)
def get_document_versions(
    filename: str,
    current_user: UserInfo = Depends(get_current_user)
):
    """Get version history for a document."""
    try:
        version_info = DocumentVersionManager.get_version_info(filename)
        if not version_info:
            raise HTTPException(status_code=404, detail=f"Document '{filename}' not found or has no versions")
        
        return version_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting versions for {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/{filename}/versions/{version}/restore")
def restore_document_version(
    filename: str,
    version: int,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Restore a specific version of a document."""
    try:
        success = DocumentVersionManager.restore_version(filename, version)
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to restore version {version} of '{filename}'. Version may not exist or is the current version."
            )
        
        # Log audit event
        ip_address = None
        if http_request:
            ip_address = (
                http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                http_request.headers.get("X-Real-IP", "") or
                (http_request.client.host if http_request.client else None)
            )
        log_audit_event(
            event_type="document_version_restored",
            user_id=current_user.id,
            username=current_user.username,
            ip_address=ip_address,
            status="success",
            details={"filename": filename, "version": version}
        )
        
        return {"message": f"Version {version} of '{filename}' has been restored. The document will be reprocessed."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring version {version} of {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/documents/{filename}/versions/{version}")
def delete_document_version(
    filename: str,
    version: int,
    current_user: UserInfo = Depends(get_current_user),
    http_request: FastAPIRequest = None
):
    """Delete a specific version of a document."""
    try:
        success = DocumentVersionManager.delete_version(filename, version)
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to delete version {version} of '{filename}'. Version may not exist, is the current version, or is the only version."
            )
        
        # Log audit event
        ip_address = None
        if http_request:
            ip_address = (
                http_request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                http_request.headers.get("X-Real-IP", "") or
                (http_request.client.host if http_request.client else None)
            )
        log_audit_event(
            event_type="document_version_deleted",
            user_id=current_user.id,
            username=current_user.username,
            ip_address=ip_address,
            status="success",
            details={"filename": filename, "version": version}
        )
        
        return {"message": f"Version {version} of '{filename}' has been deleted."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting version {version} of {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

## Summary

1. **Import** - Add `from .versioning import DocumentVersionManager` after line 15
2. **Models** - Add version models to the import list at line 35
3. **Upload** - Add version creation code around line 1705
4. **List** - Add version info code around line 1175
5. **Endpoints** - Add three new endpoints at the end of the file

After applying these changes, the document versioning system will be fully integrated into the API.




