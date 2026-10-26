from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Gemeinsame Felder der Verträge zum Anlegen und Aktualisieren eines Users und für die Response."""

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr


class UserCreate(UserBase):
    """Request-Body zum Anlegen eines Users."""


class UserUpdate(UserBase):
    """Request-Body zum Ersetzen eines Users."""


class UserOut(UserBase):
    """Response-Body, der für gespeicherte User zurückgegeben wird."""

    model_config = ConfigDict(from_attributes=True)

    id: int
