from foca.foca import foca

if __name__ == '__main__':
    app = foca("config.yaml")
    app.run(port=app.port)
