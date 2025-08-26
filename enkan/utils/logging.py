import logging

def configure_logging(debug: bool = False, quiet: bool = False) -> None:
    """
    Set up root logger.
    debug=True  -> DEBUG level
    quiet=True  -> only WARN+
    default     -> INFO
    """
    level = logging.WARNING if quiet else (logging.DEBUG if debug else logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress PIL’s verbose debug if any
    logging.getLogger("PIL").setLevel(logging.ERROR)