"""Vercel FastAPI entrypoint. Importing this file never connects to a database."""
from xcomify.vercel_runtime import create_hosted_app

app = create_hosted_app()
