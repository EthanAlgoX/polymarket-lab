from app.config import get_settings
from app.database import Database


def main() -> None:
    settings = get_settings()
    settings.ensure_directories()
    database = Database(settings.database_url)
    database.initialize()
    print("Database initialized:", settings.database_relative_path)
    database.close()


if __name__ == "__main__":
    main()
