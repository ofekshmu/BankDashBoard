"""Vercel entrypoint — exposes the Flask app for serverless deployment."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'source'))

from WebApp import app  # noqa: E402  — must be top-level for Vercel to find it

@app.errorhandler(500)
def handle_500(error):
    return {"error": "Internal Server Error", "message": str(error)}, 500
