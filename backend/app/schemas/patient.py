from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


class EmergencyContact(BaseModel):
    name: str
    relationship: str
    phone: str


class PatientProfile(BaseModel):
    patientId: str
    userId: str
    fullName: str
    dateOfBirth: str  # YYYY-MM-DD
    gender: str = Field(..., description="male | female | other | prefer_not_to_say")
    preferredLanguage: str = Field("en", description="en | hi | mr")
    city: str
    state: str
    emergencyContact: Optional[EmergencyContact] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)
