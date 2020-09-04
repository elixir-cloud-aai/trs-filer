import os

from foca.foca import foca


def main():
    app = foca(
        os.path.join(
            os.path.dirname(__file__),
            "config.yaml",
        )
    )
    app.run(port=app.port)


if __name__ == '__main__':
    main()
