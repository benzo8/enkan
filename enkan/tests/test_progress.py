from enkan import config as config_module
from enkan.config import Config
from enkan.utils.argparse_setup import get_arg_parser
from enkan.utils.progress import Progress


def test_progress_quiet_uses_current_config(monkeypatch):
    monkeypatch.setattr(config_module, "_current_config", None)
    args = get_arg_parser().parse_args(["--quiet"])
    Config.from_args(args)

    progress = Progress(range(1), tk_enabled=False)

    try:
        assert progress._console.__class__.__name__ == "_NullProgress"
    finally:
        progress.close()
