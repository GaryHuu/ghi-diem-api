import uuid

from ninja.security import APIKeyHeader


class DeviceAuth(APIKeyHeader):
    """Ownership via the ``X-Device-Id`` header.

    The value must be a valid UUID (the FE self-generates one). Missing or
    malformed header => ninja responds 401. The parsed :class:`uuid.UUID`
    becomes ``request.auth``.
    """

    param_name = "X-Device-Id"

    def authenticate(self, request, key):
        if not key:
            return None
        try:
            return uuid.UUID(str(key))
        except (ValueError, AttributeError, TypeError):
            return None


device_auth = DeviceAuth()
