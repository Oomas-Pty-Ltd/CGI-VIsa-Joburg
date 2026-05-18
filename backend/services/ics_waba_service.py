"""
====================================================================
ICS WABA SERVICE - WhatsApp Business API Client
====================================================================
Wraps the ICS Production WhatsApp Solution API v3.1
Endpoints:
  - Session Comm: https://media.sendmsg.in/sessioncomm
  - Bulk Send:    https://media.sendmsg.in/mediasend
====================================================================
"""
import logging
import os
import httpx
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

ICS_SESSION_COMM_URL = "https://media.sendmsg.in/sessioncomm"
ICS_MEDIA_SEND_URL   = "https://media.sendmsg.in/mediasend"

ICS_USER = os.environ.get("ICS_WABA_USER", "")
ICS_PASS = os.environ.get("ICS_WABA_PASS", "")
ICS_FROM = os.environ.get("ICS_WABA_FROM", "")   # WABA business number e.g. 27XXXXXXXXXX


class ICSWABAService:
    """Client for the ICS WhatsApp Business API."""

    def __init__(self):
        self.user = ICS_USER
        self.pw   = ICS_PASS
        self.from_ = ICS_FROM
        self.enabled = bool(self.user and self.pw and self.from_)
        # ICS production account returns 500 for interactive (list/buttons) messages.
        # Set True here to skip the interactive attempt and go straight to plain-text fallback.
        self._interactive_unsupported = bool(os.environ.get("ICS_DISABLE_INTERACTIVE", "true").lower() != "false")
        if not self.enabled:
            logger.warning(
                "ICS WABA not configured. Set ICS_WABA_USER, ICS_WABA_PASS, ICS_WABA_FROM in .env"
            )

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------
    async def _post(self, url: str, payload: Dict) -> Dict:
        """Send a POST request to ICS API and return JSON response."""
        if not self.enabled:
            logger.warning("[ICS DISABLED] ICS WABA service not configured. Set ICS_WABA_USER, ICS_WABA_PASS, ICS_WABA_FROM in .env")
            logger.debug("[ICS MOCK] POST %s | payload=%s", url, payload)
            return {"status": "mock", "mid": "mock_mid", "warning": "ICS WABA not configured"}
        import json as _json
        logger.info("[ICS SEND] POST %s | to=%s", url, payload.get("sessiondata", {}).get("to", "unknown"))
        logger.info("[ICS PAYLOAD] %s", _json.dumps(payload, default=str))
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                logger.info(
                    "[ICS RESPONSE] status=%s | size=%d bytes | body=%s",
                    resp.status_code, len(resp.text), resp.text[:500],
                )
                resp.raise_for_status()
                result = resp.json()
                logger.info(
                    "[ICS SUCCESS] to=%s | mid=%s | full_response=%s",
                    payload.get("sessiondata", {}).get("to", "unknown"),
                    result.get("mid", "no_mid"),
                    result,
                )
                return result
        except httpx.HTTPStatusError as exc:
            error_msg = f"ICS API HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.error("[ICS ERROR] %s", error_msg)
            return {"error": error_msg, "error_code": exc.response.status_code, "success": False}
        except httpx.ConnectError as exc:
            error_msg = f"ICS API connection failed: {str(exc)}"
            logger.error("[ICS CONNECT_ERROR] %s", error_msg)
            return {"error": error_msg, "error_type": "connection", "success": False}
        except httpx.TimeoutException as exc:
            error_msg = f"ICS API timeout (15s): {str(exc)}"
            logger.error("[ICS TIMEOUT] %s", error_msg)
            return {"error": error_msg, "error_type": "timeout", "success": False}
        except Exception as exc:
            error_msg = f"ICS API request failed: {type(exc).__name__}: {str(exc)}"
            logger.error("[ICS EXCEPTION] %s", error_msg)
            return {"error": error_msg, "error_type": type(exc).__name__, "success": False}

    def _base_session(self, to: str, from_override: str = "") -> Dict:
        """Build the common sessiondata wrapper.
        from_override: use the WABA number from the incoming webhook when available
        (more reliable than the static .env value)."""
        sender = from_override.strip() or self.from_
        return {
            "user": self.user,
            "pass": self.pw,
            "sessiondata": {
                "from": sender,
                "to": to,
            }
        }

    # ------------------------------------------------------------------
    # Text message
    # ------------------------------------------------------------------
    async def send_text(self, to: str, text: str, from_override: str = "") -> Dict:
        """Send a plain-text session message."""
        payload = self._base_session(to, from_override)
        payload["sessiondata"]["type"] = "text"
        payload["sessiondata"]["message"] = {"text": text}
        return await self._post(ICS_SESSION_COMM_URL, payload)

    # ------------------------------------------------------------------
    # Interactive buttons (max 3) — with plain-text fallback
    # ------------------------------------------------------------------
    async def send_buttons(
        self,
        to: str,
        body: str,
        buttons: List[Dict[str, str]],
        header: Optional[str] = None,
        footer: Optional[str] = None,
        from_override: str = "",
    ) -> Dict:
        """Send an interactive button message (max 3 buttons).
        Falls back to a numbered plain-text message if ICS rejects the interactive call."""
        if not self._interactive_unsupported:
            interactive: Dict[str, Any] = {
                "type": "button",
                "body": {"text": body},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                        for b in buttons[:3]
                    ]
                }
            }
            if header:
                interactive["header"] = {"type": "text", "text": header[:60]}
            if footer:
                interactive["footer"] = {"text": footer[:60]}

            payload = self._base_session(to, from_override)
            payload["sessiondata"]["type"] = "interactive"
            payload["sessiondata"]["interactive"] = interactive
            result = await self._post(ICS_SESSION_COMM_URL, payload)

            if "error" not in result:
                return result

            logger.warning("Interactive buttons failed — switching to plain-text permanently")
            self._interactive_unsupported = True

        # Plain-text fallback
        lines = []
        if header:
            lines.append(f"*{header}*")
        lines.append(body)
        for i, b in enumerate(buttons[:3], 1):
            lines.append(f"  {i}. {b['title']}")
        if footer:
            lines.append(f"_{footer}_")
        return await self.send_text(to, "\n".join(lines), from_override)

    # ------------------------------------------------------------------
    # Interactive list (max 10 rows across sections) — with plain-text fallback
    # ------------------------------------------------------------------
    async def send_list(
        self,
        to: str,
        body: str,
        button_label: str,
        sections: List[Dict],
        header: Optional[str] = None,
        footer: Optional[str] = None,
        from_override: str = "",
    ) -> Dict:
        """Send an interactive list message.
        Falls back to a numbered plain-text menu if ICS rejects the interactive call."""
        if not self._interactive_unsupported:
            interactive: Dict[str, Any] = {
                "type": "list",
                "body": {"text": body},
                "action": {
                    "button": button_label[:20],
                    "sections": sections[:10],
                }
            }
            if header:
                interactive["header"] = {"type": "text", "text": header[:60]}
            if footer:
                interactive["footer"] = {"text": footer[:60]}

            payload = self._base_session(to, from_override)
            payload["sessiondata"]["type"] = "interactive"
            payload["sessiondata"]["interactive"] = interactive
            result = await self._post(ICS_SESSION_COMM_URL, payload)

            if "error" not in result:
                return result

            logger.warning("Interactive list failed — switching to plain-text permanently")
            self._interactive_unsupported = True

        # Plain-text fallback: numbered menu
        lines = []
        if header:
            lines.append(f"*{header}*\n")
        lines.append(body + "\n")
        n = 1
        for section in sections:
            if section.get("title"):
                lines.append(f"*{section['title']}*")
            for row in section.get("rows", []):
                lines.append(f"  {n}. {row['title']}")
                n += 1
        if footer:
            lines.append(f"\n_{footer}_")
        lines.append("\n_Reply with the number of your choice._")
        return await self.send_text(to, "\n".join(lines), from_override)

    # ------------------------------------------------------------------
    # Media message
    # ------------------------------------------------------------------
    async def send_media(
        self,
        to: str,
        media_type: str,        # "image", "document", "video"
        url: str,
        caption: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Dict:
        """Send a media message (image / document / video)."""
        message: Dict[str, Any] = {"url": url}
        if caption:
            message["caption"] = caption
        if filename and media_type == "document":
            message["filename"] = filename

        payload = self._base_session(to)
        payload["sessiondata"]["type"] = media_type
        payload["sessiondata"]["message"] = message
        return await self._post(ICS_SESSION_COMM_URL, payload)

    # ------------------------------------------------------------------
    # Template message (outbound outside 24-hour session window)
    # ------------------------------------------------------------------
    async def send_template(
        self,
        to: str,
        template_id: str,
        placeholders: Optional[List[Dict]] = None,
        media_id: Optional[str] = None,
        smsgid: Optional[str] = None,
    ) -> Dict:
        """Send a pre-approved WhatsApp template message."""
        payload: Dict[str, Any] = {
            "user": self.user,
            "pass": self.pw,
            "from": self.from_,
            "to": to,
            "templateid": template_id,
            "placeholders": placeholders or [],
            "buttons": [],
        }
        if media_id:
            payload["mediaid"] = media_id
        if smsgid:
            payload["smsgid"] = smsgid

        return await self._post(ICS_MEDIA_SEND_URL, payload)


# Singleton instance used by routes
ics_waba = ICSWABAService()
