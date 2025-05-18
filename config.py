# config.py
import os

class Config:
    SQLALCHEMY_DATABASE_URI = 'postgresql://admin:Admin%40123@localhost:5432/bugsmashers_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_key')
