# Typisierte CRUD-API mit FastAPI erstellen

Eine Programmierschnittstelle legt fest, wie Softwarekomponenten Requests und Responses austauschen. Diese Lektion verwendet [FastAPI](https://fastapi.tiangolo.com/tutorial/), um eine HTTP-API bereitzustellen, [Pydantic](https://docs.pydantic.dev/latest/concepts/models/), um ihre JSON-Verträge zu validieren, und [SQLAlchemy](https://docs.sqlalchemy.org/en/20/tutorial/), um User dauerhaft in PostgreSQL zu speichern.

Der Service implementiert CRUD-Operationen:

- **Create**: einen User mit `POST` anlegen
- **Read**: User mit `GET` lesen
- **Update**: einen User mit `PUT` aktualisieren
- **Delete**: einen User mit `DELETE` löschen

## Lebenszyklus eines Requests

![Typisierter FastAPI-Request auf dem Weg durch Pydantic, eine Route, SQLAlchemy und PostgreSQL](assets/02-fastapi-request-lifecycle.png)

*Diagramm auf Grundlage der offiziellen Anleitungen zu [Request-Bodys in FastAPI](https://fastapi.tiangolo.com/tutorial/body/), [Pydantic-Modellen](https://docs.pydantic.dev/latest/concepts/models/) und [Sessions in SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/session_basics.html).*

Jede Systemgrenze hat genau eine Zuständigkeit. FastAPI kümmert sich um HTTP, Pydantic ist für den externen Datenvertrag zuständig und SQLAlchemy für den Datenbankzugriff.

## Bevor du anfängst

Verwende die Datei `.env` aus Lektion 2 wieder und starte den PostgreSQL-Container aus Lektion 2:

```bash
docker start postgres_cont
docker exec postgres_cont pg_isready -U postgres -d fastapi_db
```

Der Service auf dem Host verwendet diesen Connection-String:

```dotenv
DB_CONN=postgresql+psycopg://postgres:postgres@localhost:5432/fastapi_db
```

`localhost` ist hier richtig, weil Uvicorn auf dem Host laufen wird. Lektion 4 ändert den Hostnamen, wenn die API in einen Container umzieht.

## Aufbau des Service

```text
service/
├── __init__.py
├── database.py
├── models.py
├── schemas.py
└── main.py
```

| Datei | Zuständigkeit |
| --- | --- |
| `database.py` | `DB_CONN` laden, die Engine erstellen und Sessions pro Request bereitstellen |
| `models.py` | Python-Klassen auf Datenbanktabellen abbilden |
| `schemas.py` | Validierte Request- und Response-Bodys definieren |
| `main.py` | FastAPI konfigurieren und Routen implementieren |

## Datenbankverbindung und Session

Die zentralen Teile von `service/database.py` sind:

```python
DATABASE_URL = os.getenv("DB_CONN")

if DATABASE_URL is None:
    raise ValueError("DB_CONN environment variable is required")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    """Basisklasse, die sich die SQLAlchemy-Modelle des Service teilen."""


def get_db() -> Generator[Session]:
    """Liefert eine Datenbank-Session für einen Request und schließt sie danach."""
    with SessionLocal() as session:
        yield session
```

`get_db()` ist eine Abhängigkeit in FastAPI. Der Kontextmanager schließt die Session, nachdem der Request erfolgreich war oder fehlgeschlagen ist. So muss eine Route das Aufräumen der Verbindung nicht selbst noch einmal erledigen.

In dieser in sich geschlossenen Lektion erstellt `Base.metadata.create_all()` fehlende Tabellen, wenn der Service startet. Produktivsysteme verwalten geprüfte, umkehrbare Schemaänderungen normalerweise mit einem Migrationstool wie [Alembic](https://alembic.sqlalchemy.org/en/latest/), statt sich darauf zu verlassen, dass Tabellen automatisch erstellt werden.

## SQLAlchemy-Modell

`service/models.py` verwendet die typisierten Mappings von SQLAlchemy 2:

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
```

Die Python-Annotationen beschreiben die Attribute des Modells, während `mapped_column()` das Verhalten in der Datenbank beschreibt, etwa Primärschlüssel, maximale Länge, Eindeutigkeit und Index.

Diese API für ein User-Verzeichnis speichert absichtlich nur Profildaten. Authentifizierung und das Speichern von Passwörtern brauchen ein eigenes Sicherheitskonzept und sollten nicht in einem CRUD-Beispiel mit Passwörtern im Klartext nachgebildet werden.

## Pydantic-Verträge

`service/schemas.py` trennt eingehende Payloads von ausgehenden Darstellungen:

```python
class UserBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr


class UserCreate(UserBase):
    pass


class UserUpdate(UserBase):
    pass


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
```

`EmailStr` lehnt fehlerhafte Adressen ab, bevor eine Route die Datenbank erreicht. Mit `from_attributes=True` kann Pydantic ein SQLAlchemy-Modell in die Form der öffentlichen Response serialisieren.

Durch getrennte Klassennamen bleibt der API-Vertrag explizit, auch wenn zwei Request-Bodys derzeit dieselben Felder haben. Später können sie sich unabhängig voneinander weiterentwickeln.

## Abhängigkeit pro Request

FastAPI kann eine Typannotation mit einer Abhängigkeit kombinieren:

```python
DatabaseSession = Annotated[Session, Depends(get_db)]
```

Routen, die `db: DatabaseSession` deklarieren, erhalten eine offene SQLAlchemy-Session. FastAPI ruft die Abhängigkeit auf und kümmert sich automatisch um ihr Aufräumen.

## CRUD-Routen

Die Route zum Anlegen validiert den Request, schreibt eine Zeile und gibt das gespeicherte Modell mit dem Status `201 Created` zurück:

```python
@app.post("/users", response_model=schemas.UserOut, status_code=201)
def create_user(request: schemas.UserCreate, db: DatabaseSession) -> models.User:
    new_user = models.User(name=request.name, email=str(request.email))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
```

Die Route für die Liste verwendet die Schnittstelle `select()` von SQLAlchemy und eine deterministische Reihenfolge:

```python
@app.get("/users", response_model=list[schemas.UserOut])
def get_all_users(db: DatabaseSession) -> list[models.User]:
    statement = select(models.User).order_by(models.User.id)
    return list(db.scalars(statement))
```

Aktualisieren und Löschen holen zuerst die Zielzeile mit `db.get()`. Fehlende IDs liefern `404 Not Found`, statt stillschweigend Erfolg zu melden.

| Methode | Pfad | Response bei Erfolg |
| --- | --- | --- |
| `GET` | `/` | Status des Service |
| `GET` | `/users` | Sortierte Liste der User |
| `GET` | `/users/{user_id}` | Ein User oder `404 Not Found` |
| `POST` | `/users` | `201` und der angelegte User |
| `PUT` | `/users/{user_id}` | Aktualisierter User |
| `DELETE` | `/users/{user_id}` | `204 No Content` |

Fehlerhafte Request-Bodys liefern `422 Unprocessable Content`, fehlende IDs `404 Not Found` und doppelte E-Mail-Adressen `409 Conflict`. Mit diesen Responses bleiben Validierungsfehler und fachliche Fehler an der HTTP-Grenze, statt dass eine Exception der Datenbank nach außen dringt.

## API auf dem Host starten

Im Stammverzeichnis des Repositorys:

```bash
uv run uvicorn service.main:app --reload --port 8000
```

Öffne die generierte [Swagger UI](http://localhost:8000/docs) oder sieh dir das [OpenAPI-Schema](http://localhost:8000/openapi.json) an.

## API-Vertrag ausprobieren

Prüfe den Service und die Collection im Ausgangszustand:

```bash
curl http://localhost:8000/
curl http://localhost:8000/users
```

Lege einen User an:

```bash
curl -X POST http://localhost:8000/users \
    -H "Content-Type: application/json" \
    -d '{"name":"Jane Doe","email":"jane.doe@example.com"}'
```

Lies User `1` direkt aus:

```bash
curl http://localhost:8000/users/1
```

Aktualisiere User `1`:

```bash
curl -X PUT http://localhost:8000/users/1 \
    -H "Content-Type: application/json" \
    -d '{"name":"Jane Smith","email":"jane.smith@example.com"}'
```

Lösche denselben User:

```bash
curl -i -X DELETE http://localhost:8000/users/1
```

Die Response auf das Löschen hat den Status `204` und keinen JSON-Body. Wenn du den Request wiederholst, kommt `404` zurück, weil die Zeile nicht mehr existiert.

## Checkpoint

**Warum gibt es für einen User sowohl ein SQLAlchemy-Modell als auch ein Pydantic-Modell?**

**Antwort:** Das SQLAlchemy-Modell beschreibt die dauerhafte Speicherung in der Datenbank. Die Pydantic-Modelle beschreiben die öffentlichen Verträge für Request und Response. Wenn beide getrennt bleiben, werden Implementierungsdetails der Datenbank nicht versehentlich zu API-Feldern, und beide Seiten können sich unabhängig weiterentwickeln.

## Zusammenfassung

Der Service validiert jetzt typisierte JSON-Payloads, öffnet eine SQLAlchemy-Session pro Request, implementiert alle vier CRUD-Operationen, gibt aussagekräftige HTTP-Statuscodes zurück und stellt einen automatisch generierten OpenAPI-Vertrag bereit.
