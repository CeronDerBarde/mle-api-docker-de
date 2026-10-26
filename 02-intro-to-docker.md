# PostgreSQL mit Docker starten

[Docker](https://docs.docker.com/get-started/docker-overview/) verpackt Software in isolierte Container. In dieser Lektion läuft die Anwendung noch auf deinem Rechner, während [PostgreSQL](https://hub.docker.com/_/postgres) in einem Container aus seinem offiziellen Image läuft.

So bleiben die Version der Datenbank und die Startkonfiguration reproduzierbar, ohne dass auf dem Computer jeder teilnehmenden Person direkt ein PostgreSQL-Server installiert werden muss.

## Grundbegriffe

| Begriff | Bedeutung in dieser Lektion |
| --- | --- |
| **Image** | Schreibgeschütztes Template mit PostgreSQL und seiner Laufzeitumgebung |
| **Container** | Laufende Instanz, die aus dem Image erstellt wird |
| **Port-Mapping** | Verbindung vom Host-Port `5432` zum Container-Port `5432` |
| **Umgebungsvariable** | Startkonfiguration wie Datenbankname und Zugangsdaten |
| **Volume** | Von Docker verwalteter Speicher, der das Ersetzen eines Containers übersteht |
| **Dockerfile** | Rezept zum Bauen eines eigenen Images, später für die API verwendet |

Wir brauchen kein eigenes Dockerfile für PostgreSQL. Das offizielle Image stellt den Entrypoint des Servers schon bereit und akzeptiert die Konfiguration, die diese Lektion braucht.

## Architektur für die Entwicklung

![Offizielles PostgreSQL-Image, konfiguriert und als dauerhafter lokaler Container gestartet](assets/01-docker-image-container-lifecycle.png)

*Diagramm auf Grundlage der offiziellen Erklärungen von Docker zu [Images und Containern](https://docs.docker.com/get-started/docker-concepts/the-basics/what-is-an-image/) und [dauerhaften Volumes](https://docs.docker.com/engine/storage/volumes/).*

## Umgebungsdatei vorbereiten

Erstelle im Stammverzeichnis des Repositorys die lokale Datei `.env`, falls es sie noch nicht gibt:

```bash
cp .env.example .env
```

Die Datei enthält Werte, die nur für die Entwicklung gedacht sind:

```dotenv
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=fastapi_db
DB_CONN=postgresql+psycopg://postgres:postgres@localhost:5432/fastapi_db
```

Echte Secrets müssen außerhalb der Versionsverwaltung bleiben. Das Repository versioniert `.env.example` als dokumentiertes Template und ignoriert `.env`.

## PostgreSQL starten

Starte das offizielle Image von PostgreSQL 17 und lade seine Variablen aus `.env`:

```bash
docker run -d --name postgres_cont \
    --env-file .env \
    -v postgres-data:/var/lib/postgresql/data \
    -p 5432:5432 \
    postgres:17
```

| Option | Zweck |
| --- | --- |
| `-d` | Im Hintergrund ausführen |
| `--name postgres_cont` | Dem Container einen festen lokalen Namen geben |
| `--env-file .env` | Die Initialisierungswerte für PostgreSQL übergeben |
| `-v postgres-data:...` | Die Datenbank in einem benannten Volume dauerhaft speichern |
| `-p 5432:5432` | PostgreSQL für den Host-Rechner freigeben |
| `postgres:17` | Das offizielle, versionierte Image verwenden |

Die Initialisierungsvariablen werden nur angewendet, wenn das Datenverzeichnis leer ist. Wenn du `postgres-data` wiederverwendest, bleiben die vorhandene Datenbank und ihre Zugangsdaten erhalten.

## Bereitschaft prüfen

```bash
docker logs postgres_cont
docker exec postgres_cont pg_isready -U postgres -d fastapi_db
```

Der Befehl für die Bereitschaftsprüfung sollte melden, dass der Server Verbindungen annimmt.

## Mit psql verbinden

Am portabelsten ist es, den Client zu verwenden, der im Container schon vorhanden ist:

```bash
docker exec -it postgres_cont psql -U postgres -d fastapi_db
```

Wenn `psql` auf dem Host installiert ist, verwendet dieser gleichwertige Befehl den freigegebenen Port:

```bash
psql -h localhost -p 5432 -U postgres -d fastapi_db
```

## Tabelle erstellen und untersuchen

Der FastAPI-Service wird die Tabelle automatisch erstellen. Wenn du das SQL aber von Hand ausführst, wird der Datenbankvertrag sichtbar:

```sql
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(320) UNIQUE NOT NULL
);

INSERT INTO users (name, email)
VALUES ('Jane Doe', 'jane.doe@example.com');

SELECT id, name, email FROM users;
```

Nützliche `psql`-Befehle:

| Befehl | Zweck |
| --- | --- |
| `\dt` | Tabellen auflisten |
| `\d users` | Die Tabelle `users` beschreiben |
| `\q` | `psql` beenden |

Entferne die Beispielzeile, bevor du mit der API-Lektion beginnst, wenn du mit einer leeren Liste starten möchtest:

```sql
DELETE FROM users;
```

## Lebenszyklus des Containers

```bash
docker stop postgres_cont
docker start postgres_cont
docker ps -a
```

So ersetzt du den Container und behältst dabei das Volume der Datenbank:

```bash
docker rm -f postgres_cont
```

Lösche die dauerhaft gespeicherten Daten nur, wenn du bewusst eine leere Datenbank möchtest:

```bash
docker volume rm postgres-data
```

## Checkpoint

**Warum verwendet die API `localhost`, wenn sie auf dem Host läuft, aber einen Container-Namen, wenn sie später in Docker läuft?**

**Antwort:** `localhost` bezeichnet immer den aktuellen Netzwerk-Namespace. Auf dem Host erreicht es den freigegebenen Port der Datenbank. Im API-Container würde es auf den API-Container selbst zurückzeigen. Deshalb verwenden Container in einem gemeinsamen Docker-Netzwerk stattdessen den Namen des Datenbank-Containers oder des Service.

## Zusammenfassung

Du hast ein versioniertes PostgreSQL-Image gestartet, die lokale Konfiguration übergeben, die nicht in der Versionsverwaltung liegt, den Port von PostgreSQL freigegeben, den Zustand der Datenbank in einem benannten Volume dauerhaft gespeichert und den Server von beiden Seiten der Container-Grenze aus geprüft.
