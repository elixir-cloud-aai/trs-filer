from foca.foca import foca

if __name__ == '__main__':
    app = foca("app_config.yaml")
    app.run(port=8080)
