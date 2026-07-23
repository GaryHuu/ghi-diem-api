from django.urls import re_path

from .consumers import ShareConsumer

websocket_urlpatterns = [
    re_path(r"^ws/share/(?P<token>[^/]+)/?$", ShareConsumer.as_asgi()),
]
