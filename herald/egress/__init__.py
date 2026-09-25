"""Egress policy (E1): every outbound HTTP call Herald makes -- relay packets to the ED, protocol-mirror sync,
local model requests -- decides ALLOW / QUEUE / DENY through `EgressPolicy.decide` before it happens."""
from .policy import Decision, EgressPolicy, default_policy, host_of

__all__ = ["Decision", "EgressPolicy", "default_policy", "host_of"]
