import os

basedir = os.path.abspath(os.path.dirname(__file__))


class DevConfig:
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(basedir, 'scanner_rdb.db')}"
    SQLALCHEMY_ECHO = True