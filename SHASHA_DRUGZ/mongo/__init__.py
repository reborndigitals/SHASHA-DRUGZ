#supported by federation 
from async_pymongo import AsyncClient

from config import DATABASE_NAME, MONGO_DB_URI

mongo = AsyncClient(MONGO_DB_URI)
dbname = mongo[DATABASE_NAME]
