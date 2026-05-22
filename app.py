"""
Vercel entrypoint for Flask app
Imports and exposes the Flask application for serverless deployment
"""

import sys
import os

# Add source directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'source'))

# Import and expose the Flask app
from WebApp import app

# Export for Vercel
__all__ = ['app']
