"""
Google Gemini Implementation of AIProvider with Advanced Multi-Stage Intelligence Prompts.
"""
import json
import re
from typing import Dict, Any, List
from app.ai.provider import AIProvider
from app.ai.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    MEMORIAL_GENERATION_PROMPT,
    EULOGY_GENERATION_PROMPT,
    INCIDENT_REPORT_PROMPT,
    TIMELINE_EXTRACTION_PROMPT
)
from app.config import settings
from app.utils.logger import logger

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class GeminiProvider(AIProvider):
    """Google Gemini AI Provider with robust fallback heuristics."""

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model_name = settings.GEMINI_MODEL
        self._initialized = False

        if HAS_GENAI and self.api_key and self.api_key != "your_google_gemini_api_key_here":
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(self.model_name)
                self._initialized = True
                logger.info(f"Initialized Gemini AI Provider with model: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini AI: {e}")

    async def extract_info(self, raw_text: str, article_title: str) -> Dict[str, Any]:
        """Parses article text using Gemini or fallback keyword heuristics."""
        combined_text = f"Title: {article_title}\n\nContent:\n{raw_text}"

        if self._initialized:
            try:
                prompt = f"{EXTRACTION_SYSTEM_PROMPT}\n\nNews Article:\n{combined_text}"
                response = self.model.generate_content(prompt)
                response_text = response.text.strip()

                if response_text.startswith("```"):
                    response_text = re.sub(r"^```(?:json)?\n?", "", response_text)
                    response_text = re.sub(r"\n?```$", "", response_text)

                data = json.loads(response_text)
                return {
                    "is_fallen_responder": data.get("is_fallen_responder", True),
                    "name": data.get("name", "Unknown Hero"),
                    "agency": data.get("agency", "Unknown Emergency Agency"),
                    "category": data.get("category", "OTHER"),
                    "date_of_incident": data.get("date_of_incident", "Recent"),
                    "date_of_death": data.get("date_of_death", "End of Watch"),
                    "summary": data.get("summary", article_title),
                    "k9_handler_name": data.get("k9_handler_name"),
                    "k9_breed": data.get("k9_breed"),
                    "service_years": data.get("service_years"),
                    "unit_badge": data.get("unit_badge")
                }
            except Exception as e:
                logger.error(f"Gemini API extraction error: {e}. Utilizing fallback parser.")

        return self._fallback_extraction(combined_text, article_title)

    async def generate_memorial(self, extracted_data: Dict[str, Any], verse: Dict[str, str]) -> str:
        """Generates a solemn memorial tribute using Gemini or template fallback."""
        name = extracted_data.get("name", "Fallen Hero")
        agency = extracted_data.get("agency", "Emergency Services")
        category = extracted_data.get("category", "OTHER")
        summary = extracted_data.get("summary", "In solemn remembrance of faithful service.")
        date_of_death = extracted_data.get("date_of_death", "End of Watch")
        v_text = verse.get("text", "")
        v_ref = verse.get("reference", "")

        if self._initialized:
            try:
                prompt = MEMORIAL_GENERATION_PROMPT.format(
                    name=name,
                    agency=agency,
                    category=category,
                    summary=summary,
                    date_of_death=date_of_death,
                    verse_text=v_text,
                    verse_ref=v_ref
                )
                response = self.model.generate_content(prompt)
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                logger.error(f"Gemini memorial generation failed: {e}")

        return (
            f"It is with heavy hearts and profound honor that we remember **{name}** of **{agency}**. "
            f"{summary}\n\n"
            f"We honor their noble dedication, courage, and ultimate sacrifice in service to the community. "
            f"May their bravery never be forgotten, and may comfort rest upon their loved ones, colleagues, and agency.\n\n"
            f"> *\"{v_text}\"* — **{v_ref}**\n\n"
            f"**End of Watch / Date:** {date_of_death}"
        )

    async def generate_eulogy(self, record_data: Dict[str, Any]) -> str:
        """Generates a formal State Funeral Eulogy speech draft."""
        name = record_data.get("name", "Fallen Emergency Responder")
        agency = record_data.get("agency", "Emergency Services")
        summary = record_data.get("summary", "Honoring faithful service.")
        eow = record_data.get("date_of_death", "End of Watch")

        if self._initialized:
            try:
                prompt = EULOGY_GENERATION_PROMPT.format(
                    name=name,
                    agency=agency,
                    summary=summary,
                    date_of_death=eow
                )
                response = self.model.generate_content(prompt)
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                logger.error(f"Gemini eulogy generation failed: {e}")

        return (
            f"**Formal State Funeral Eulogy for {name}**\n\n"
            f"Friends, family, and honored colleagues:\n\n"
            f"We gather today in heavy silence to honor a true guardian of our community, **{name}** of the **{agency}**. "
            f"When danger called, {name} stood without hesitation on the front lines of public service.\n\n"
            f"{summary}\n\n"
            f"Their courage represents the highest ideals of selflessness and honor. Though their End of Watch arrived far too soon on {eow}, "
            f"their legacy of protection, valor, and sacrifice will forever shine as a beacon of light in our community.\n\n"
            f"May peace rest upon their family, strength upon their fellow responders, and everlasting honor upon their memory. Rest in peace, your watch is ended."
        )

    async def extract_timeline(self, raw_text: str) -> List[Dict[str, str]]:
        """Extracts a chronological timeline of events."""
        if self._initialized and raw_text:
            try:
                prompt = TIMELINE_EXTRACTION_PROMPT.format(text=raw_text)
                response = self.model.generate_content(prompt)
                resp_text = response.text.strip()
                if resp_text.startswith("```"):
                    resp_text = re.sub(r"^```(?:json)?\n?", "", resp_text)
                    resp_text = re.sub(r"\n?```$", "", resp_text)
                return json.loads(resp_text)
            except Exception as e:
                logger.error(f"Gemini timeline extraction error: {e}")

        return [
            {"time_or_date": "Incident Date", "event": "Emergency response call dispatched."},
            {"time_or_date": "End of Watch", "event": "Responder sustained fatal injuries in the line of duty."}
        ]

    def _fallback_extraction(self, text: str, title: str) -> Dict[str, Any]:
        """Simple heuristic extraction fallback."""
        lower = f"{title} {text}".lower()

        category = "OTHER"
        if any(w in lower for w in ["police", "officer", "sheriff", "trooper", "deputy", "cop"]):
            category = "LAW_ENFORCEMENT"
        elif any(w in lower for w in ["firefighter", "fire department", "fire captain", "chief"]):
            category = "FIRE"
        elif any(w in lower for w in ["paramedic", "emt", "ambulance", "ems"]):
            category = "EMS"
        elif any(w in lower for w in ["k9", "k-9"]):
            category = "K9"
        elif any(w in lower for w in ["dispatcher", "911", "communications"]):
            category = "DISPATCH"
        elif any(w in lower for w in ["rescue", "search and rescue"]):
            category = "RESCUE"

        is_fallen = any(w in lower for w in ["died", "killed", "passed away", "end of watch", "eow", "fatal", "tribute", "memorial", "line of duty"])

        return {
            "is_fallen_responder": is_fallen,
            "name": title.split(":")[-1].strip() if ":" in title else "Fallen Emergency Responder",
            "agency": "Emergency Services Department",
            "category": category,
            "date_of_incident": "Recent",
            "date_of_death": "End of Watch",
            "summary": title,
            "k9_handler_name": None,
            "k9_breed": None,
            "service_years": None,
            "unit_badge": None
        }
