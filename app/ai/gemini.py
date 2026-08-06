"""
Google Gemini Implementation of AIProvider with Support for Both 'google-genai' and 'google-generativeai'.
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

HAS_NEW_GENAI = False
HAS_LEGACY_GENAI = False

try:
    from google import genai as new_genai
    HAS_NEW_GENAI = True
except ImportError:
    HAS_NEW_GENAI = False

try:
    import google.generativeai as legacy_genai
    HAS_LEGACY_GENAI = True
except ImportError:
    HAS_LEGACY_GENAI = False


class GeminiProvider(AIProvider):
    """Google Gemini AI Provider supporting new google.genai and legacy packages."""

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model_name = settings.GEMINI_MODEL or "gemini-2.5-flash"
        self._initialized = False
        self.new_client = None
        self.legacy_model = None

        if HAS_NEW_GENAI and self.api_key and self.api_key != "your_google_gemini_api_key_here":
            try:
                self.new_client = new_genai.Client(api_key=self.api_key)
                self._initialized = True
                logger.info(f"Initialized Google GenAI (new SDK) with model: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize new Google GenAI SDK: {e}")

        if not self._initialized and HAS_LEGACY_GENAI and self.api_key and self.api_key != "your_google_gemini_api_key_here":
            try:
                legacy_genai.configure(api_key=self.api_key)
                self.legacy_model = legacy_genai.GenerativeModel(self.model_name)
                self._initialized = True
                logger.info(f"Initialized Google GenerativeAI (legacy SDK) with model: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize legacy Gemini AI: {e}")

    def _generate_text(self, prompt: str) -> str:
        """Internal helper for generating text across new or legacy Gemini SDKs with automatic model fallback."""
        if not self._initialized:
            return ""

        models_to_try = [self.model_name, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        seen = set()
        unique_models = []
        for m in models_to_try:
            clean_m = m.replace("models/", "") if m else ""
            if clean_m and clean_m not in seen:
                seen.add(clean_m)
                unique_models.append(clean_m)

        for m_name in unique_models:
            try:
                if self.new_client:
                    response = self.new_client.models.generate_content(
                        model=m_name,
                        contents=prompt
                    )
                    if response and response.text:
                        return response.text.strip()
                elif self.legacy_model:
                    response = self.legacy_model.generate_content(prompt)
                    if response and response.text:
                        return response.text.strip()
            except Exception as e:
                logger.error(f"Gemini API text generation error ({m_name}): {e}")
                continue
        return ""

    async def extract_memorial_data(self, scraped_or_text: Any, article_title: str = "") -> Dict[str, Any]:
        """Alias for extract_info supporting both dict payload and raw_text args."""
        if isinstance(scraped_or_text, dict):
            raw_text = scraped_or_text.get("raw_content") or scraped_or_text.get("summary") or ""
            title = scraped_or_text.get("article_title") or article_title
            res = await self.extract_info(raw_text, title)
            res["is_line_of_duty_death"] = res.get("is_fallen_responder", True)
            return res
        res = await self.extract_info(str(scraped_or_text), article_title)
        res["is_line_of_duty_death"] = res.get("is_fallen_responder", True)
        return res

    async def generate_memorial_text(self, extracted_data: Dict[str, Any], verse: Dict[str, str] = None) -> str:
        """Alias for generate_memorial."""
        if verse is None:
            verse = {
                "text": "Greater love has no one than this: to lay down one's life for one's friends.",
                "reference": "John 15:13"
            }
        return await self.generate_memorial(extracted_data, verse)

    async def extract_info(self, raw_text: str, article_title: str) -> Dict[str, Any]:
        """Parses article text using Gemini or fallback keyword heuristics."""
        combined_text = f"Title: {article_title}\n\nContent:\n{raw_text}"

        if self._initialized:
            try:
                prompt = f"{EXTRACTION_SYSTEM_PROMPT}\n\nNews Article:\n{combined_text}"
                response_text = self._generate_text(prompt)

                if response_text:
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
            prompt = MEMORIAL_GENERATION_PROMPT.format(
                name=name,
                agency=agency,
                category=category,
                summary=summary,
                date_of_death=date_of_death,
                verse_text=v_text,
                verse_ref=v_ref
            )
            text = self._generate_text(prompt)
            if text:
                return text

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
            prompt = EULOGY_GENERATION_PROMPT.format(
                name=name,
                agency=agency,
                summary=summary,
                date_of_death=eow
            )
            text = self._generate_text(prompt)
            if text:
                return text

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

    async def translate_memorial(self, text: str, target_language: str) -> str:
        """Translates memorial text and scripture into Spanish, French, German, or other languages."""
        if self._initialized and text:
            prompt = f"Translate the following solemn emergency responder memorial tribute text into {target_language}. Maintain reverence and honor:\n\n{text}"
            res_text = self._generate_text(prompt)
            if res_text:
                return res_text
        return f"[{target_language.upper()} TRANSLATION]: {text}"

    async def extract_timeline(self, raw_text: str) -> List[Dict[str, str]]:
        """Extracts a chronological timeline of events."""
        if self._initialized and raw_text:
            try:
                prompt = TIMELINE_EXTRACTION_PROMPT.format(text=raw_text)
                resp_text = self._generate_text(prompt)
                if resp_text:
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
        """Smart regex and heuristic extraction fallback for news titles & articles."""
        lower = f"{title} {text}".lower()

        category = "OTHER"
        if any(w in lower for w in ["police", "officer", "sheriff", "trooper", "deputy", "cop", "patrol"]):
            category = "LAW_ENFORCEMENT"
        elif any(w in lower for w in ["firefighter", "fire department", "fire captain", "chief", "firefighting"]):
            category = "FIRE"
        elif any(w in lower for w in ["paramedic", "emt", "ambulance", "ems"]):
            category = "EMS"
        elif any(w in lower for w in ["k9", "k-9"]):
            category = "K9"
        elif any(w in lower for w in ["dispatcher", "911", "communications"]):
            category = "DISPATCH"
        elif any(w in lower for w in ["rescue", "search and rescue"]):
            category = "RESCUE"

        # 1. Smart Name Extraction
        name_match = re.search(r'\b(Officer|Deputy|Trooper|Detective|Sergeant|Captain|Lieutenant|Chief|Firefighter|Paramedic|K9|K-9)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)', title + " " + text)
        if name_match:
            name = f"{name_match.group(1)} {name_match.group(2)}"
        else:
            clean_t = re.sub(r'\s*-\s*[A-Za-z0-9\.]+$', '', title).strip()
            name = clean_t if clean_t else "Fallen Emergency Hero"

        # 2. Smart Agency Extraction
        agency_match = re.search(r'\b([A-Z][a-zA-Z\s]+(Police|Sheriff|Fire|EMS|State Police|Highway Patrol|Department|Dept|PD))\b', title + " " + text)
        if agency_match:
            agency = agency_match.group(1).strip()
        elif "las vegas" in lower:
            agency = "Las Vegas Metropolitan Police Department"
        else:
            agency = "Emergency Services Department"

        # 3. Date of Death / EOW
        date_match = re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:,\s+\d{4})?\b', title + " " + text, re.IGNORECASE)
        if date_match:
            eow_date = date_match.group(0)
        else:
            eow_date = datetime.utcnow().strftime("%B %d, %Y")

        is_fallen = any(w in lower for w in ["died", "killed", "passed away", "end of watch", "eow", "fatal", "tribute", "memorial", "line of duty", "shootout", "crash"])

        return {
            "is_fallen_responder": is_fallen,
            "name": name,
            "agency": agency,
            "category": category,
            "date_of_incident": "Recent Line of Duty Incident",
            "date_of_death": eow_date,
            "summary": title,
            "k9_handler_name": None,
            "k9_breed": None,
            "service_years": None,
            "unit_badge": None
        }
