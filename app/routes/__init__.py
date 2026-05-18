from .cloudsql import sql_bp
from .storage import storage_bp
from .documentai import documentai_bp
from .gemini import gemini_bp
from .workspace import workspace_bp

def register_routes(app):
    app.register_blueprint(sql_bp)
    app.register_blueprint(storage_bp)
    app.register_blueprint(documentai_bp)
    app.register_blueprint(gemini_bp)
    app.register_blueprint(workspace_bp)
