from enum import Enum
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from datetime import datetime


class UserRole(str, Enum):
    PATIENT = "patient"
    CLINICIAN = "clinician"
    ADMIN = "admin"


class UserBase(BaseModel):
    email: EmailStr
    displayName: str
    role: UserRole
    phone: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserProfile(UserBase):
    userId: str
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)
