from flask import Flask
from flask_cors import CORS
from .routes import register_routes
from .extensions import connector, storage_client

def create_app():
    app = Flask(__name__)
    # CORS(app, resources={r"/*": {"origins": "*"}})
    CORS(app, resources={r"/*": {
    "origins": "*",  # Esto permite cualquier dominio
    "methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"],
    "expose_headers": ["Content-Type","Content-Disposition"]
    }})
    
    # Registrar todas las rutas
    register_routes(app)

    @app.route("/")
    def root():
        return {"msg": "API modularizada en Cloud Run"}

    return app
