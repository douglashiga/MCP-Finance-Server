"""
LLM abstraction layer for enrichment services.
Handles provider selection (Ollama, OpenAI) and client instantiation.
"""
import os
import logging
import requests
from typing import Optional, Dict, Any, List
from dataloader.database import SessionLocal
from dataloader.models import LLMConfig

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self, config: LLMConfig):
        self.provider = config.provider.lower()
        self.model = config.model_name
        self.api_key = config.api_key
        # Default Ollama to host.docker.internal if not specified, assuming running in Docker
        self.api_base = config.api_base or "http://host.docker.internal:11434"

    def chat_completion(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> Optional[str]:
        """
        Generic chat completion wrapper.
        messages format: [{"role": "user", "content": "..."}]
        """
        if self.provider == "ollama":
            return self._call_ollama(messages, temperature)
        elif self.provider == "openai":
            return self._call_openai(messages, temperature)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _call_ollama(self, messages: List[Dict[str, str]], temperature: float) -> Optional[str]:
        url = f"{self.api_base.rstrip('/')}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content")
        except Exception as e:
            logger.error(f"Ollama API call failed: {e}")
            return None

    def _call_openai(self, messages: List[Dict[str, str]], temperature: float) -> Optional[str]:
        # Implemented using requests to avoid heavy dependencies if possible, 
        # or use standard openai lib if available. For now, simple HTTP.
        url = "https://api.openai.com/v1/chat/completions"
        if self.api_base and "openai.com" not in self.api_base:
             url = f"{self.api_base.rstrip('/')}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            return None

def get_llm_client(config_id: Optional[int] = None) -> Optional[LLMClient]:
    """Factory to get configured LLM client."""
    session = SessionLocal()
    try:
        if config_id:
            config = session.query(LLMConfig).filter(LLMConfig.id == config_id).first()
        else:
            # Get default active config
            config = session.query(LLMConfig).filter(
                LLMConfig.is_active == True,
                LLMConfig.is_default == True
            ).first()
            
            # Fallback to any active if no default
            if not config:
                config = session.query(LLMConfig).filter(LLMConfig.is_active == True).first()
        
        if not config:
            logger.warning("No active LLM configuration found.")
            return None
            
        return LLMClient(config)
    finally:
        session.close()
