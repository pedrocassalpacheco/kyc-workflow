"""Model access for the workflow. Import from here, not from the submodules.

    from kyc_workflow.gateway import HeliosGateway, AnthropicBackend, ModelRequest

Only `anthropic_backend` imports the Anthropic SDK.
"""

from kyc_workflow.gateway.fake import FakeBackend, FakeGateway
from kyc_workflow.gateway.helios import HeliosGateway, MetadataEntry
from kyc_workflow.gateway.protocol import (
    BackendError,
    BackendResult,
    GatewayError,
    HeliosRejected,
    HeliosUnavailable,
    HeliosUnsupported,
    ModelBackend,
    ModelGateway,
    ModelRequest,
    ModelResponse,
    TokenUsage,
    ToolCall,
    ToolDef,
)

__all__ = [
    "AnthropicBackend",
    "BackendError",
    "BackendResult",
    "FakeBackend",
    "FakeGateway",
    "GatewayError",
    "HeliosGateway",
    "HeliosRejected",
    "HeliosUnavailable",
    "HeliosUnsupported",
    "MetadataEntry",
    "ModelBackend",
    "ModelGateway",
    "ModelRequest",
    "ModelResponse",
    "TokenUsage",
    "ToolCall",
    "ToolDef",
]


def __getattr__(name: str):
    # Lazy so that importing the gateway package never imports the SDK unless asked.
    if name == "AnthropicBackend":
        from kyc_workflow.gateway.anthropic_backend import AnthropicBackend

        return AnthropicBackend
    raise AttributeError(name)
