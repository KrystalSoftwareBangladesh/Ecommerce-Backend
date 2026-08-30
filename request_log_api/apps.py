from django.apps import AppConfig


class RequestLogApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'request_log_api'
    verbose_name = 'API Request Logs'
