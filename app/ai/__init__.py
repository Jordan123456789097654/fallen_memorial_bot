"""
AI Layer initialization.
"""
from app.ai.provider import AIProvider
from app.ai.gemini import GeminiProvider

def get_ai_provider() -> AIProvider:
    """Factory function returning configured AI Provider instance."""
    return GeminiProvider()
