"""
Azure Functions app entry point.

Registers all blueprints (timer, crawl, analyze, management API).
"""

import logging

import azure.functions as func
from functions.analyze_function import bp as analyze_bp
from functions.crawl_function import bp as crawl_bp
from functions.management_api import bp as api_bp
from functions.timer_trigger import bp as timer_bp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Register blueprints
app.register_blueprint(timer_bp)
app.register_blueprint(crawl_bp)
app.register_blueprint(analyze_bp)
app.register_blueprint(api_bp)

logger.info("Court Monitor function app initialised")
