def get_storage(storage_type: str = "sqlite", **kwargs):
    if storage_type == "postgres":
        from .postgres import PostgresStorage
        return PostgresStorage(kwargs["dsn"], retention=kwargs.get("retention", 2000))
    if storage_type == "sqlite":
        from .sqlite import SQLiteStorage
        return SQLiteStorage(kwargs.get("path", "bitteam_klines.db"), retention=kwargs.get("retention", 2000))
    raise ValueError("Unknown candle storage backend")


def __getattr__(name):
    if name == "SQLiteStorage":
        from .sqlite import SQLiteStorage
        return SQLiteStorage
    if name == "PostgresStorage":
        from .postgres import PostgresStorage
        return PostgresStorage
    raise AttributeError(name)
