from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import ActiveCredentialListView, RevealCredentialSecretView


urlpatterns = [
    path("token/", TokenObtainPairView.as_view(), name="api_token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="api_token_refresh"),
    path(
        "credentials/active/",
        ActiveCredentialListView.as_view(),
        name="api_active_credentials",
    ),
    path(
        "credentials/reveal-secret/",
        RevealCredentialSecretView.as_view(),
        name="api_reveal_credential_secret",
    ),
]
