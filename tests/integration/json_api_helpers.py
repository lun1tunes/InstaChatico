"""Shared helper functions for JSON API integration tests."""


def auth_headers(env):
    """Generate authorization headers for JSON API requests."""
    return {"Authorization": f"Bearer {env['json_api_token']}"}
