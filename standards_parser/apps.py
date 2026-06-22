"""
App configuration for standards_parser application.
"""

from django.apps import AppConfig


class StandardsParserConfig(AppConfig):
    """Configuration class for standards_parser app."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'standards_parser'
    verbose_name = '标准文档解析'
    
    def ready(self):
        """
        Perform initialization when Django app is ready.
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info("standards_parser app initialized")
