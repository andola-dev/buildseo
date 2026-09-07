"""Access to the process-wide resource container and its members."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.bootstrap import AppResources
from app.config.settings import Settings
from app.core.crypto.envelope import EnvelopeEncryptionService
from app.core.http_client import SafeHttpClient
from app.core.security.jwt import JwtService
from app.core.security.password import PasswordHasher


def get_resources(request: Request) -> AppResources:
    """Return the container attached to the app during startup."""
    resources: AppResources = request.app.state.resources
    return resources


ResourcesDep = Annotated[AppResources, Depends(get_resources)]


def get_settings_dep(resources: ResourcesDep) -> Settings:
    return resources.settings


def get_http_client(resources: ResourcesDep) -> SafeHttpClient:
    return resources.http_client


def get_encryption(resources: ResourcesDep) -> EnvelopeEncryptionService:
    return resources.encryption


def get_password_hasher(resources: ResourcesDep) -> PasswordHasher:
    return resources.password_hasher


def get_jwt_service(resources: ResourcesDep) -> JwtService:
    return resources.jwt_service


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
HttpClientDep = Annotated[SafeHttpClient, Depends(get_http_client)]
EncryptionDep = Annotated[EnvelopeEncryptionService, Depends(get_encryption)]
PasswordHasherDep = Annotated[PasswordHasher, Depends(get_password_hasher)]
JwtServiceDep = Annotated[JwtService, Depends(get_jwt_service)]
