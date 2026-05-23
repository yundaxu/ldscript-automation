"""模拟器脚本自助 Web Panel - Flask application factory."""
import os
from flask import Flask

from auto_ld._compat import get_project_root


def create_app(ld=None, adb_provider=None, loader=None, scheduler=None, worker=None, settings=None):
    template_dir = os.path.join(get_project_root(), "templates")
    app = Flask(__name__, template_folder=template_dir)
    app.config["JSON_AS_ASCII"] = False

    app.config["AUTOLD_LD"] = ld
    app.config["AUTOLD_ADB_PROVIDER"] = adb_provider
    app.config["AUTOLD_LOADER"] = loader
    app.config["AUTOLD_SCHEDULER"] = scheduler
    app.config["AUTOLD_WORKER"] = worker
    app.config["AUTOLD_SETTINGS"] = settings or {}

    from auto_ld.web.routes import bp
    app.register_blueprint(bp)

    return app
