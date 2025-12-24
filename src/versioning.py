"""
Document versioning management.
"""
import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
import threading
import shutil

# Get project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSIONS_FILE = os.path.join(PROJECT_ROOT, "data", "document_versions.json")
VERSIONS_DIR = os.path.join(PROJECT_ROOT, "document_versions")

# Thread lock for file operations
_file_lock = threading.Lock()


def ensure_data_dir():
    """Ensure the data directory exists."""
    data_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(VERSIONS_DIR, exist_ok=True)


def load_versions() -> Dict:
    """Load document versions from file."""
    ensure_data_dir()
    if not os.path.exists(VERSIONS_FILE):
        return {}
    
    try:
        with _file_lock:
            with open(VERSIONS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠️ Error loading versions: {e}")
        return {}


def save_versions(versions: Dict):
    """Save document versions to file."""
    ensure_data_dir()
    try:
        with _file_lock:
            with open(VERSIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(versions, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"⚠️ Error saving versions: {e}")


def calculate_file_hash(file_path: str) -> Optional[str]:
    """Calculate SHA256 hash of a file."""
    try:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        print(f"⚠️ Error calculating file hash: {e}")
        return None


class DocumentVersionManager:
    """Manage document versions."""
    
    @staticmethod
    def create_version(
        filename: str,
        file_path: str,
        user_id: str,
        username: str,
        file_size: int
    ) -> Dict:
        """Create a new version of a document."""
        ensure_data_dir()
        
        # Calculate file hash
        file_hash = calculate_file_hash(file_path)
        if not file_hash:
            raise ValueError("Failed to calculate file hash")
        
        # Load existing versions
        versions = load_versions()
        
        # Get or create document entry
        if filename not in versions:
            versions[filename] = {
                "filename": filename,
                "versions": [],
                "current_version": 1,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        
        doc_versions = versions[filename]["versions"]
        
        # Check if this is a duplicate (same hash)
        for version in doc_versions:
            if version.get("file_hash") == file_hash:
                # Same file, don't create new version
                return version
        
        # Determine new version number
        if doc_versions:
            new_version = max(v.get("version", 0) for v in doc_versions) + 1
        else:
            new_version = 1
        
        # Create version directory
        version_dir = os.path.join(VERSIONS_DIR, filename)
        os.makedirs(version_dir, exist_ok=True)
        
        # Copy file to version directory
        version_filename = f"v{new_version}_{filename}"
        version_path = os.path.join(version_dir, version_filename)
        
        try:
            shutil.copy2(file_path, version_path)
        except Exception as e:
            raise ValueError(f"Failed to copy file for versioning: {e}")
        
        # Create version entry
        version_entry = {
            "version": new_version,
            "file_path": version_path,
            "file_hash": file_hash,
            "file_size": file_size,
            "uploaded_by": {
                "user_id": user_id,
                "username": username
            },
            "uploaded_at": datetime.now().isoformat(),
            "is_current": False
        }
        
        # Mark all previous versions as not current
        for v in doc_versions:
            v["is_current"] = False
        
        # Mark this version as current
        version_entry["is_current"] = True
        versions[filename]["current_version"] = new_version
        versions[filename]["updated_at"] = datetime.now().isoformat()
        
        # Add new version
        doc_versions.append(version_entry)
        
        # Save versions
        save_versions(versions)
        
        return version_entry
    
    @staticmethod
    def get_versions(filename: str) -> List[Dict]:
        """Get all versions of a document."""
        versions = load_versions()
        if filename not in versions:
            return []
        
        return versions[filename].get("versions", [])
    
    @staticmethod
    def get_current_version(filename: str) -> Optional[Dict]:
        """Get the current version of a document."""
        versions = load_versions()
        if filename not in versions:
            return None
        
        doc_versions = versions[filename].get("versions", [])
        for version in doc_versions:
            if version.get("is_current", False):
                return version
        
        # If no current version marked, return latest
        if doc_versions:
            return max(doc_versions, key=lambda v: v.get("version", 0))
        
        return None
    
    @staticmethod
    def get_version_info(filename: str) -> Optional[Dict]:
        """Get version information for a document."""
        versions = load_versions()
        if filename not in versions:
            return None
        
        return versions[filename]
    
    @staticmethod
    def restore_version(filename: str, version_number: int) -> bool:
        """Restore a specific version of a document."""
        versions = load_versions()
        if filename not in versions:
            return False
        
        doc_versions = versions[filename].get("versions", [])
        target_version = None
        
        for version in doc_versions:
            if version.get("version") == version_number:
                target_version = version
                break
        
        if not target_version:
            return False
        
        # Check if version file exists
        version_path = target_version.get("file_path")
        if not version_path or not os.path.exists(version_path):
            return False
        
        # Copy version file to source directory
        source_files_dir = os.path.join(PROJECT_ROOT, "source_files")
        os.makedirs(source_files_dir, exist_ok=True)
        target_path = os.path.join(source_files_dir, filename)
        
        try:
            shutil.copy2(version_path, target_path)
            
            # Update current version
            for v in doc_versions:
                v["is_current"] = (v.get("version") == version_number)
            
            versions[filename]["current_version"] = version_number
            versions[filename]["updated_at"] = datetime.now().isoformat()
            save_versions(versions)
            
            return True
        except Exception as e:
            print(f"⚠️ Error restoring version: {e}")
            return False
    
    @staticmethod
    def delete_version(filename: str, version_number: int) -> bool:
        """Delete a specific version of a document."""
        versions = load_versions()
        if filename not in versions:
            return False
        
        doc_versions = versions[filename].get("versions", [])
        
        # Find and remove version
        version_to_delete = None
        for i, version in enumerate(doc_versions):
            if version.get("version") == version_number:
                version_to_delete = version
                # Don't allow deleting the only version
                if len(doc_versions) == 1:
                    return False
                # Don't allow deleting current version
                if version.get("is_current", False):
                    return False
                doc_versions.pop(i)
                break
        
        if not version_to_delete:
            return False
        
        # Delete version file
        version_path = version_to_delete.get("file_path")
        if version_path and os.path.exists(version_path):
            try:
                os.remove(version_path)
            except Exception as e:
                print(f"⚠️ Error deleting version file: {e}")
        
        # Update document info
        versions[filename]["updated_at"] = datetime.now().isoformat()
        save_versions(versions)
        
        return True
    
    @staticmethod
    def list_all_documents() -> List[Dict]:
        """List all documents with version information."""
        versions = load_versions()
        result = []
        
        for filename, doc_info in versions.items():
            doc_versions = doc_info.get("versions", [])
            result.append({
                "filename": filename,
                "version_count": len(doc_versions),
                "current_version": doc_info.get("current_version"),
                "created_at": doc_info.get("created_at"),
                "updated_at": doc_info.get("updated_at")
            })
        
        return result




