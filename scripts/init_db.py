from app.config import get_settings
from app.database import Base, Database


def main() -> None:
    settings = get_settings()
    settings.ensure_directories()
    database = Database(settings.database_url)
    try:
        # Schema preparation is idempotent; only service startup should mark
        # existing opportunity snapshots unverified after a restart.
        Base.metadata.create_all(database.engine)
        print("Database initialized:", settings.database_relative_path)
    finally:
        database.close()


if __name__ == "__main__":
    main()
