from fastapi import FastAPI

from log import setup_logging
from api import router

setup_logging()

app = FastAPI()
app.include_router(router)
