"""Security primitives for the DM pipeline.

Currently exports the `alert_security_event` dispatcher used by
`core/dm/phases/detection.py` to log prompt_injection and sensitive_content
detections without blocking the request.
"""

from core.security.alerting import alert_security_event

__all__ = ["alert_security_event"]
