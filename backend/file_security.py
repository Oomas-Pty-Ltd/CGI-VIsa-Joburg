import os
import magic
from fastapi import HTTPException, UploadFile
from typing import List

ALLOWED_IMAGE_FORMATS = [
    'image/jpeg',
    'image/jpg', 
    'image/png',
    'image/webp'
]

ALLOWED_DOCUMENT_FORMATS = [
    'application/pdf',
    'image/jpeg',
    'image/jpg',
    'image/png'
]

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

async def validate_image_upload(file: UploadFile) -> bool:
    """Validate image file for security"""
    
    # Check file size
    contents = await file.read()
    await file.seek(0)
    
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE/1024/1024}MB"
        )
    
    # Check file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp']
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File format not allowed. Allowed formats: {', '.join(allowed_extensions)}"
        )
    
    # Check actual MIME type (prevents extension spoofing)
    try:
        mime = magic.from_buffer(contents, mime=True)
        if mime not in ALLOWED_IMAGE_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Expected image, got {mime}"
            )
    except Exception as e:
        # Fallback if python-magic not available
        pass
    
    return True

async def validate_document_upload(file: UploadFile) -> bool:
    """Validate document file for security"""
    
    # Check file size
    contents = await file.read()
    await file.seek(0)
    
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE/1024/1024}MB"
        )
    
    # Check file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File format not allowed. Allowed formats: {', '.join(allowed_extensions)}"
        )
    
    # Check actual MIME type
    try:
        mime = magic.from_buffer(contents, mime=True)
        if mime not in ALLOWED_DOCUMENT_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid document type. Expected PDF or image, got {mime}"
            )
    except Exception:
        # Fallback validation
        pass
    
    return True

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks"""
    # Remove any path components
    filename = os.path.basename(filename)
    
    # Remove potentially dangerous characters
    dangerous_chars = ['..', '/', '\\', '<', '>', '|', ':', '*', '?', '"']
    for char in dangerous_chars:
        filename = filename.replace(char, '_')
    
    return filename
