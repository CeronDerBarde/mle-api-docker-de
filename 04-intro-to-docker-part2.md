# FastAPI mit Docker verpacken

In Lektion 2 lief die Datenbank in Docker, während die API auf dem Host blieb. Diese Lektion verpackt den Python-3.13-Service in ein eigenes Image und verbindet dann die Container von API und PostgreSQL über ein [benutzerdefiniertes Bridge-Netzwerk](https://docs.docker.com/engine/network/drivers/bridge/).

Der manuelle Workflow macht jede Entscheidung zu Build, Netzwerk, Umgebung und Ports sichtbar, bevor Docker Compose sie in Lektion 5 automatisiert.

## Zielarchitektur

```mermaid
flowchart LR
    Client["Browser oder curl"] -->|"localhost:8000"| API["fastapi_cont"]
    API -->|"postgres_cont:5432"| DB["postgres_cont"]
    API --- Network["api-network"]
    DB --- Network
    DB --> Volume["postgres-data"]
```

In einem Container verweist `localhost` auf genau diesen Container. Die API verwendet deshalb `postgres_cont` als Hostnamen der Datenbank im gemeinsamen Netzwerk.

## Das Dockerfile der API

[`service/Dockerfile`](service/Dockerfile) wird vom Stammverzeichnis des Repositorys aus gebaut, damit sowohl die Lock-Datei als auch das Service-Paket verfügbar sind:

```Dockerfile
FROM ghcr.io/astral-sh/uv:0.12.6 AS uv
FROM python:3.13-slim-bookworm

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY service ./service

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

| Anweisung | Zweck |
| --- | --- |
| `FROM ... uv` | Das versionierte uv-Binary aus seinem offiziellen Image bereitstellen |
| `FROM python:3.13-slim-bookworm` | Die benötigte Python-Laufzeitumgebung auf einer kleinen Debian-Basis verwenden |
| `COPY pyproject.toml uv.lock` | Die Metadaten der Abhängigkeiten vor dem Anwendungscode kopieren, damit Docker die Schichten aus dem Cache wiederverwenden kann |
| `uv sync --locked --no-dev` | Genau die in der Lock-Datei festgelegten Laufzeitabhängigkeiten installieren |
| `COPY service ./service` | Nach den Abhängigkeiten nur das Anwendungspaket hinzufügen |
| `uv run --no-sync` | Uvicorn starten, ohne die installierte Umgebung zu verändern |

Die [`.dockerignore`](.dockerignore) im Stammverzeichnis verwendet eine kurze Allowlist: Nur `pyproject.toml`, `uv.lock` und Python-Dateien unter `service/` gelangen in den Build-Kontext. Lokale Umgebungen, Git-Metadaten, Lektionen, Tests, generierte Daten und Secrets erreichen den Builder nie.

## Image der API bauen

Führe diesen Befehl im Stammverzeichnis des Repositorys aus:

```bash
docker build -f service/Dockerfile -t user-directory-api .
```

Der `.` am Ende ist wichtig. Er macht das Stammverzeichnis des Repositorys zum Build-Kontext, sodass Docker `pyproject.toml`, `uv.lock` und `service/` kopieren kann.

Sieh dir das Ergebnis an:

```bash
docker image ls user-directory-api
```

## Gemeinsames Netzwerk erstellen

Entferne den Container aus Lektion 2, falls er noch existiert, und erstelle dann das Netzwerk:

```bash
docker rm -f postgres_cont 2>/dev/null || true
docker network create api-network
```

## PostgreSQL im Netzwerk starten

```bash
docker run -d --name postgres_cont \
    --network api-network \
    --env-file .env \
    -v postgres-data:/var/lib/postgresql/data \
    postgres:17
```

Für den Datenverkehr zwischen Containern muss der Port der Datenbank nicht freigegeben werden. Beide Services kommunizieren über `api-network`.

Prüfe, ob die Datenbank bereit ist, bevor du die API startest:

```bash
docker exec postgres_cont pg_isready -U postgres -d fastapi_db
```

## API-Container starten

Beende den Uvicorn-Prozess auf dem Host aus Lektion 3 mit `Ctrl+C` in seinem Terminal, bevor du den Container startest. So wird Port `8000` für die API im Container frei.

```bash
docker run -d --name fastapi_cont \
    --network api-network \
    -e DB_CONN='postgresql+psycopg://postgres:postgres@postgres_cont:5432/fastapi_db' \
    -p 8000:8000 \
    user-directory-api
```

Der Port der API wird freigegeben, weil der Browser auf dem Host und `curl` ihn erreichen müssen. Die Verbindung zu PostgreSQL bleibt privat im Docker-Netzwerk.

## Laufende Container prüfen

```bash
docker ps
docker logs fastapi_cont
curl http://localhost:8000/
curl http://localhost:8000/users
```

Öffne <http://localhost:8000/docs>, um denselben typisierten Vertrag über die Swagger UI auszuprobieren.

Untersuche, welche Container zum Netzwerk gehören und wie der Container konfiguriert ist:

```bash
docker network inspect api-network
docker inspect fastapi_cont
```

## Aufräumen

```bash
docker rm -f fastapi_cont postgres_cont
docker network rm api-network
```

Das benannte Volume `postgres-data` bleibt erhalten, damit du es im manuellen Docker-Workflow wiederverwenden kannst. Lektion 5 erstellt ein separates Compose-Volume mit dem Projektnamen als Präfix. Deshalb startet die Datenbank dort ohne die Einträge, die du hier angelegt hast.

## Checkpoint

**Warum werden `pyproject.toml` und `uv.lock` vor `service/` kopiert?**

**Antwort:** Docker kann die Schicht mit den Abhängigkeiten wiederverwenden, auch wenn sich der Anwendungscode ändert. Die Abhängigkeiten werden nur neu installiert, wenn sich ihre Metadaten ändern. Dadurch werden wiederholte Builds schneller und besser vorhersagbar.

## Zusammenfassung

Du hast aus der Lock-Datei ein Image mit Python 3.13 gebaut, Secrets aus dem Image herausgehalten, zwei Container in einem privaten Netzwerk über ihre Hostnamen verbunden und nach außen nur die API freigegeben, die Clients brauchen.
