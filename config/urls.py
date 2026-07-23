"""URL configuration for the ghi-diem-api project."""
from django.urls import path

from matches.api import api

urlpatterns = [
    path("api/", api.urls),
]
