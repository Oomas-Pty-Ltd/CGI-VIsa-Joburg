from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import bcrypt
from database import get_database
from auth_utils import verify_super_admin

router = APIRouter(prefix="/super-admin", tags=["super-admin"])

class CompanyCreate(BaseModel):
    name: str
    email: EmailStr
    admin_password: str
    llm_model: str = "gpt-5.2"
    features: dict = {"voice": True, "camera": True}

class Company(BaseModel):
    id: str
    name: str
    email: str
    llm_model: str
    features: dict
    created_at: str
    status: str

class LLMConfig(BaseModel):
    company_id: str
    model: str
    provider: str = "openai"

@router.post("/companies", response_model=Company)
async def create_company(company: CompanyCreate, payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    
    existing = await db.companies.find_one({"email": company.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company with this email already exists"
        )
    
    company_id = str(uuid.uuid4())
    admin_id = str(uuid.uuid4())
    
    company_doc = {
        "id": company_id,
        "name": company.name,
        "email": company.email,
        "llm_model": company.llm_model,
        "features": company.features,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active"
    }
    
    await db.companies.insert_one(company_doc)
    
    hashed_password = bcrypt.hashpw(company.admin_password.encode('utf-8'), bcrypt.gensalt())
    admin_doc = {
        "id": admin_id,
        "company_id": company_id,
        "email": company.email,
        "password": hashed_password.decode('utf-8'),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.local_admins.insert_one(admin_doc)
    
    return Company(**company_doc)

@router.get("/companies", response_model=List[Company])
async def get_companies(limit: int = 100, payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    companies = await db.companies.find({}, {"_id": 0}).limit(limit).to_list(limit)
    return [Company(**company) for company in companies]

@router.get("/companies/{company_id}", response_model=Company)
async def get_company(company_id: str, payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )
    
    return Company(**company)

@router.put("/companies/{company_id}/llm-config")
async def update_llm_config(company_id: str, config: LLMConfig, payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    
    result = await db.companies.update_one(
        {"id": company_id},
        {"$set": {"llm_model": config.model}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )
    
    return {"success": True, "message": "LLM config updated"}

@router.get("/analytics/overview")
async def get_analytics_overview(payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    
    total_companies = await db.companies.count_documents({})
    total_sessions = await db.chat_sessions.count_documents({})
    total_documents = await db.documents.count_documents({})
    
    return {
        "total_companies": total_companies,
        "total_sessions": total_sessions,
        "total_documents": total_documents
    }