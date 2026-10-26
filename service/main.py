from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from service import models, schemas
from service.database import Base, engine, get_db

app = FastAPI(title="User Directory API", version="1.0.0")

Base.metadata.create_all(bind=engine)

DatabaseSession = Annotated[Session, Depends(get_db)]


def get_user_or_404(db: Session, user_id: int) -> models.User:
    """Gibt einen User zurück oder löst die öffentliche Not-Found-Response aus."""
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def ensure_email_available(
    db: Session, email: str, *, exclude_user_id: int | None = None
) -> None:
    """Löst einen Konfliktfehler aus, wenn ein anderer User die E-Mail-Adresse schon verwendet."""
    statement = select(models.User).where(models.User.email == email)
    if exclude_user_id is not None:
        statement = statement.where(models.User.id != exclude_user_id)
    if db.scalar(statement) is not None:
        raise HTTPException(status_code=409, detail="Email already registered")


def commit_user_change(db: Session) -> None:
    """Behandelt E-Mail-Konflikte, die nach der Verfügbarkeitsprüfung auftreten."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if isinstance(exc.orig, UniqueViolation) and exc.orig.diag.constraint_name in {
            "ix_users_email",
            "users_email_key",
        }:
            raise HTTPException(
                status_code=409, detail="Email already registered"
            ) from exc
        raise


@app.get("/", tags=["health"])
def index() -> dict[str, str]:
    """Gibt eine schlanke Status-Response des Service zurück."""
    return {"status": "ok"}


@app.get("/users", response_model=list[schemas.UserOut])
def get_all_users(db: DatabaseSession) -> list[models.User]:
    """Gibt alle gespeicherten User nach ID sortiert zurück."""
    statement = select(models.User).order_by(models.User.id)
    return list(db.scalars(statement))


@app.get("/users/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: int, db: DatabaseSession) -> models.User:
    """Gibt einen gespeicherten User anhand seiner ID zurück."""
    return get_user_or_404(db, user_id)


@app.post("/users", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def create_user(request: schemas.UserCreate, db: DatabaseSession) -> models.User:
    """Validiert einen neuen User und speichert ihn."""
    email = str(request.email)
    ensure_email_available(db, email)

    new_user = models.User(name=request.name, email=email)
    db.add(new_user)
    commit_user_change(db)
    db.refresh(new_user)
    return new_user


@app.put("/users/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int, request: schemas.UserUpdate, db: DatabaseSession
) -> models.User:
    """Ersetzt die bearbeitbaren Felder eines Users."""
    existing_user = get_user_or_404(db, user_id)

    email = str(request.email)
    ensure_email_available(db, email, exclude_user_id=user_id)

    existing_user.name = request.name
    existing_user.email = email
    commit_user_change(db)
    db.refresh(existing_user)
    return existing_user


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: DatabaseSession) -> Response:
    """Löscht einen User oder gibt 404 zurück, wenn er nicht existiert."""
    user = get_user_or_404(db, user_id)

    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
