"""
Abstract Base Class for AI Provider Interface.
Includes contracts for basic extraction, memorial text, eulogies, and incident timelines.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List


class AIProvider(ABC):
    """Abstract class defining contract for AI processing engines."""

    @abstractmethod
    async def extract_info(self, raw_text: str, article_title: str) -> Dict[str, Any]:
        """Parses news text to classify responder type and extract key details."""
        pass

    @abstractmethod
    async def generate_memorial(self, extracted_data: Dict[str, Any], verse: Dict[str, str]) -> str:
        """Generates a solemn, respectful memorial announcement incorporating scripture."""
        pass

    @abstractmethod
    async def generate_eulogy(self, record_data: Dict[str, Any]) -> str:
        """Generates a comprehensive, formal eulogy speech draft for a fallen responder."""
        pass

    @abstractmethod
    async def extract_timeline(self, raw_text: str) -> List[Dict[str, str]]:
        """Extracts a chronological timeline of key incident events from the raw article text."""
        pass
