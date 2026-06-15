"""
Vercel entrypoint for Flask app
Imports and exposes the Flask application for serverless deployment
"""

import sys
import os
import traceback

try:
    # Add source directory to path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'source'))

    # Import and expose the Flask app
    from WebApp import app

    # Add error handler for unhandled exceptions
    @app.errorhandler(500)
    def handle_500(error):
        return {
            "error": "Internal Server Error",
            "message": str(error),
            "type": type(error).__name__
        }, 500

    # Export for Vercel
    __all__ = ['app']

except Exception as e:
    print(f"FATAL ERROR during app initialization: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    raise
