"""
X (Twitter) & BlueSky Social Media Publisher.
Automatically formats and broadcasts approved memorial posts and EOW anniversaries.
"""
import datetime
import aiohttp
from typing import Dict, Any
from app.config import settings
from app.utils.logger import logger


class SocialPublisher:
    """Social Media Publisher for X (Twitter) and BlueSky."""

    def __init__(self):
        self.enabled = settings.ENABLE_SOCIAL_POSTING

    async def publish_memorial(self, record_dict: Dict[str, Any]):
        """Formats and posts approved memorial tribute to X and BlueSky."""
        if not self.enabled:
            return

        name = record_dict.get("name", "Fallen Hero")
        agency = record_dict.get("agency", "Emergency Services")
        eow = record_dict.get("date_of_death", "Line of Duty")
        url = record_dict.get("article_url", "")

        post_text = (
            f"🕯️ IN MEMORY: We honor {name} of the {agency}.\n"
            f"End of Watch: {eow}.\n\n"
            f"Never forgotten. Ultimate sacrifice in service to the community.\n"
            f"📖 Read Full Memorial: {url}\n\n"
            f"#FallenHero #LineOfDuty #NeverForgotten"
        )

        await self._post_to_x(post_text)
        await self._post_to_bluesky(post_text)

    async def publish_anniversary(self, record_dict: Dict[str, Any], years_ago: int):
        """Posts EOW anniversary reminder to social media."""
        if not self.enabled:
            return

        name = record_dict.get("name", "Fallen Hero")
        agency = record_dict.get("agency", "Emergency Services")
        url = record_dict.get("article_url", "")

        post_text = (
            f"🕯️ EOW ANNIVERSARY ({years_ago} Year{'s' if years_ago > 1 else ''} Ago Today):\n"
            f"Remembering {name} of the {agency}.\n"
            f"Always in our hearts. Honor their service.\n\n"
            f"🔗 {url}\n"
            f"#AlwaysRemembered #HonorTheFallen"
        )

        await self._post_to_x(post_text)
        await self._post_to_bluesky(post_text)

    async def _post_to_x(self, text: str):
        """Posts tweet to X (Twitter API v2 REST endpoint or Fallback)."""
        if not settings.X_ACCESS_TOKEN:
            logger.info(f"[Social Simulation - X/Twitter]: {text[:80]}...")
            return

        try:
            url = "https://api.twitter.com/2/tweets"
            headers = {
                "Authorization": f"Bearer {settings.X_ACCESS_TOKEN}",
                "Content-Type": "application/json"
            }
            payload = {"text": text}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
                    if resp.status in (200, 201):
                        logger.info("Successfully posted memorial tribute to X (Twitter).")
                    else:
                        err = await resp.text()
                        logger.warning(f"X API response status {resp.status}: {err}")
        except Exception as e:
            logger.error(f"Error posting to X (Twitter): {e}")

    async def _post_to_bluesky(self, text: str):
        """Posts to BlueSky AT Protocol API."""
        if not settings.BLUESKY_HANDLE or not settings.BLUESKY_PASSWORD:
            logger.info(f"[Social Simulation - BlueSky]: {text[:80]}...")
            return

        try:
            async with aiohttp.ClientSession() as session:
                auth_url = "https://bsky.social/xrpc/com.atproto.server.createSession"
                auth_payload = {
                    "identifier": settings.BLUESKY_HANDLE,
                    "password": settings.BLUESKY_PASSWORD
                }
                async with session.post(auth_url, json=auth_payload, timeout=10) as auth_resp:
                    if auth_resp.status == 200:
                        auth_data = await auth_resp.json()
                        access_jwt = auth_data.get("accessJwt")
                        did = auth_data.get("did")

                        record_url = "https://bsky.social/xrpc/com.atproto.repo.createRecord"
                        headers = {"Authorization": f"Bearer {access_jwt}"}
                        record_payload = {
                            "repo": did,
                            "collection": "app.bsky.feed.post",
                            "record": {
                                "$type": "app.bsky.feed.post",
                                "text": text,
                                "createdAt": datetime.datetime.utcnow().isoformat() + "Z"
                            }
                        }
                        async with session.post(record_url, json=record_payload, headers=headers, timeout=10) as post_resp:
                            if post_resp.status == 200:
                                logger.info("Successfully posted memorial tribute to BlueSky.")
        except Exception as e:
            logger.error(f"Error posting to BlueSky: {e}")
