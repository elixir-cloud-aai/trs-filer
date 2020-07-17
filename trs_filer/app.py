from foca.foca import foca
from pathlib import Path


if __name__ == '__main__':
    config = str(Path(__file__).resolve().parent / "app_config.yaml")
    app = foca("app_config.yaml")
    app.run(port=8080)
