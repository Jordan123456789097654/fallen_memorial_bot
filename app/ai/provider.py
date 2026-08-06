"""
Abstract Base Class for AI Provider Interface.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List


class AIProvider(ABC):
    """Abstract class defining contract for AI processing engines."""

    @abstractmethod
    async def extract_info(self, raw_text: str, article_title: str) -> Dict[str, Any]:
        """Parses news text to classify responder type and extract key details."""
        pass

    async def extract_memorial_data(self, scraped_or_text: Any, article_title: str = "") -> Dict[str, Any]:
        """Parses news text to classify responder type and extract key details."""
        if isinstance(scraped_or_text, dict):
            raw_text = scraped_or_text.get("raw_content") or scraped_or_text.get("summary") or ""
            title = scraped_or_text.get("article_title") or article_title
            res = await self.extract_info(raw_text, title)
            res["is_line_of_duty_death"] = res.get("is_fallen_responder", True)
            return res
        res = await self.extract_info(str(scraped_or_text), article_title)
        res["is_line_of_duty_death"] = res.get("is_fallen_responder", True)
        return res

    @abstractmethod
    async def generate_memorial(self, extracted_data: Dict[str, Any], verse: Dict[str, str]) -> str:
        """Generates a solemn, respectful memorial announcement incorporating scripture."""
        pass

    async def generate_memorial_text(self, extracted_data: Dict[str, Any], verse: Dict[str, str] = None) -> str:
        """Generates a solemn, respectful memorial announcement incorporating scripture."""
        if verse is None:
            verse = {"text": "Greater love has no one than this...", "reference": "John 15:13"}
        return await self.generate_memorial(extracted_data, verse)

    @abstractmethod
    async def generate_eulogy(self, record_data: Dict[str, Any]) -> str:
        """Generates a formal eulogy speech draft for a fallen responder."""
        pass

    @abstractmethod
    async def extract_timeline(self, raw_text: str) -> List[Dict[str, str]]:
        """Extracts a chronological timeline of key incident events."""
        pass
