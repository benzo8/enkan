import logging

HURT_LEVEL = 5
logging.addLevelName(HURT_LEVEL, "HURT")

def configure_logging(log_level: int = 2) -> None:
    """
    Set up root logger with numeric verbosity.
        5 -> HURT (very chatty)
        4 -> DEBUG
        3 -> WARNING
        2 -> INFO (default)
        1 -> ERROR
    """
    level_map = {
        5: HURT_LEVEL,
        4: logging.DEBUG,
        3: logging.WARNING,
        2: logging.INFO,
        1: logging.ERROR,
    }
    level = level_map.get(log_level, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress PIL's verbose debug if any
    logging.getLogger("PIL").setLevel(logging.ERROR)
