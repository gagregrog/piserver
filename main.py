from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from log import setup_logging
from api import router

setup_logging()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
