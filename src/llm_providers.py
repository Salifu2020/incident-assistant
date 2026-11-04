"""
LLM Provider abstraction layer.
Supports multiple LLM backends: Groq (recommended), Ollama (self-hosted), OpenAI.
"""
import os
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Generator

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def chat(self, messages: List[Dict], stream: bool = False, 
             temperature: float = 0.3, max_tokens: int = 500) -> str:
        """Send chat messages and get response."""
        pass
    
    @abstractmethod
    def chat_stream(self, messages: List[Dict], 
                    temperature: float = 0.3, max_tokens: int = 500) -> Generator[str, None, None]:
        """Stream chat response."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available."""
        pass


class GroqProvider(LLMProvider):
    """
    Groq LLM provider - Fast inference with open models.
    
    Recommended models:
    - llama-3.3-70b-versatile (best quality)
    - llama-3.1-8b-instant (fast, good quality)
    - mixtral-8x7b-32768 (good for long context)
    - gemma2-9b-it (Google's model)
    """
    
    # Model mapping from friendly names to Groq model IDs
    MODEL_MAP = {
        "llama3": "llama-3.3-70b-versatile",
        "llama3-70b": "llama-3.3-70b-versatile",
        "llama3-8b": "llama-3.1-8b-instant",
        "mixtral": "mixtral-8x7b-32768",
        "gemma2": "gemma2-9b-it",
        # Default mapping for common Ollama model names
        "mistral": "mixtral-8x7b-32768",
        "phi3:mini": "llama-3.1-8b-instant",
        "llama3.2:3b": "llama-3.1-8b-instant",
    }
    
    def __init__(self, api_key: str = None, model: str = "qwen/qwen3.8-27b"):
        """
        Initialize Groq provider.
        
        Args:
            api_key: Groq API key (defaults to GROQ_API_KEY env var)
            model: Model name (can be friendly name or full Groq model ID)
        """
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        # Map friendly names to Groq model IDs
        self.model = self.MODEL_MAP.get(model, model)
        self._client = None
        
        if not self.api_key:
            logger.warning("GROQ_API_KEY not set - Groq provider will not be available")
    
    @property
    def client(self):
        """Lazy-load Groq client."""
        if self._client is None and self.api_key:
            try:
                from groq import Groq
                self._client = Groq(api_key=self.api_key)
                logger.info(f"✅ Groq client initialized with model: {self.model}")
            except ImportError:
                logger.error("groq package not installed. Run: pip install groq")
                raise
        return self._client
    
    def is_available(self) -> bool:
        """Check if Groq is available."""
        if not self.api_key:
            return False
        try:
            # Quick test
            self.client
            return True
        except Exception as e:
            logger.error(f"Groq not available: {e}")
            return False
    
    def chat(self, messages: List[Dict], stream: bool = False,
             temperature: float = 0.3, max_tokens: int = 500) -> str:
        """Send chat messages and get response."""
        if stream:
            # Collect streamed response
            response_text = ""
            for chunk in self.chat_stream(messages, temperature, max_tokens):
                response_text += chunk
            return response_text.strip()
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False
        )
        message = response.choices[0].message
        content = (message.content or "").strip()
        # Some Groq models (e.g. gpt-oss) return reasoning with empty content.
        if not content:
            content = (getattr(message, "reasoning", None) or "").strip()
        return content
    
    def chat_stream(self, messages: List[Dict],
                    temperature: float = 0.3, max_tokens: int = 500) -> Generator[str, None, None]:
        """Stream chat response."""
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            piece = getattr(delta, "content", None) or getattr(delta, "reasoning", None)
            if piece:
                yield piece


class OllamaProvider(LLMProvider):
    """
    Ollama LLM provider - Self-hosted open models.
    
    Requires Ollama to be running (locally or remote).
    """
    
    def __init__(self, host: str = None, model: str = "mistral"):
        """
        Initialize Ollama provider.
        
        Args:
            host: Ollama host URL (defaults to OLLAMA_HOST env var or localhost)
            model: Model name
        """
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = model
        self._available = None
        
        # Set host for ollama library
        if self.host:
            os.environ["OLLAMA_HOST"] = self.host
    
    def is_available(self) -> bool:
        """Check if Ollama is available."""
        if self._available is not None:
            return self._available
        
        try:
            import ollama
            # Try a simple API call
            ollama.list()
            self._available = True
            logger.info(f"✅ Ollama available at {self.host}")
        except Exception as e:
            logger.warning(f"Ollama not available at {self.host}: {e}")
            self._available = False
        
        return self._available
    
    def chat(self, messages: List[Dict], stream: bool = False,
             temperature: float = 0.3, max_tokens: int = 500) -> str:
        """Send chat messages and get response."""
        import ollama
        
        if stream:
            response_text = ""
            for chunk in self.chat_stream(messages, temperature, max_tokens):
                response_text += chunk
            return response_text.strip()
        
        response = ollama.chat(
            model=self.model,
            messages=messages,
            stream=False,
            options={
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        )
        return response["message"]["content"].strip()
    
    def chat_stream(self, messages: List[Dict],
                    temperature: float = 0.3, max_tokens: int = 500) -> Generator[str, None, None]:
        """Stream chat response."""
        import ollama
        
        stream = ollama.chat(
            model=self.model,
            messages=messages,
            stream=True,
            options={
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        )
        for chunk in stream:
            if 'message' in chunk and 'content' in chunk['message']:
                yield chunk['message']['content']


class OpenAIProvider(LLMProvider):
    """
    OpenAI LLM provider - GPT models.
    """
    
    def __init__(self, api_key: str = None, model: str = "gpt-3.5-turbo"):
        """
        Initialize OpenAI provider.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model name
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self._client = None
        
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set - OpenAI provider will not be available")
    
    @property
    def client(self):
        """Lazy-load OpenAI client."""
        if self._client is None and self.api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
                logger.info(f"✅ OpenAI client initialized with model: {self.model}")
            except ImportError:
                logger.error("openai package not installed. Run: pip install openai")
                raise
        return self._client
    
    def is_available(self) -> bool:
        """Check if OpenAI is available."""
        if not self.api_key:
            return False
        try:
            self.client
            return True
        except Exception as e:
            logger.error(f"OpenAI not available: {e}")
            return False
    
    def chat(self, messages: List[Dict], stream: bool = False,
             temperature: float = 0.3, max_tokens: int = 500) -> str:
        """Send chat messages and get response."""
        if stream:
            response_text = ""
            for chunk in self.chat_stream(messages, temperature, max_tokens):
                response_text += chunk
            return response_text.strip()
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False
        )
        return response.choices[0].message.content.strip()
    
    def chat_stream(self, messages: List[Dict],
                    temperature: float = 0.3, max_tokens: int = 500) -> Generator[str, None, None]:
        """Stream chat response."""
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


def get_llm_provider(provider_name: str = None, model: str = None) -> LLMProvider:
    """
    Factory function to get the appropriate LLM provider.
    
    Priority order (if provider_name not specified):
    1. Groq (if GROQ_API_KEY is set)
    2. OpenAI (if OPENAI_API_KEY is set)
    3. Ollama (fallback, requires running server)
    
    Args:
        provider_name: Explicit provider name ("groq", "openai", "ollama")
        model: Model name for the provider
    
    Returns:
        LLMProvider instance
    """
    # Check environment for provider preference
    provider_name = provider_name or os.environ.get("LLM_PROVIDER", "auto")
    model = model or os.environ.get("LLM_MODEL", "qwen/qwen3.8-27b")
    
    if provider_name == "groq" or (provider_name == "auto" and os.environ.get("GROQ_API_KEY")):
        provider = GroqProvider(model=model)
        if provider.is_available():
            logger.info(f"🚀 Using Groq LLM provider with model: {provider.model}")
            return provider
        elif provider_name == "groq":
            raise RuntimeError("Groq provider requested but not available (check GROQ_API_KEY)")
    
    if provider_name == "openai" or (provider_name == "auto" and os.environ.get("OPENAI_API_KEY")):
        provider = OpenAIProvider(model=model)
        if provider.is_available():
            logger.info(f"🚀 Using OpenAI LLM provider with model: {model}")
            return provider
        elif provider_name == "openai":
            raise RuntimeError("OpenAI provider requested but not available (check OPENAI_API_KEY)")
    
    # Fallback to Ollama
    provider = OllamaProvider(model=model)
    if provider.is_available():
        logger.info(f"🚀 Using Ollama LLM provider with model: {model}")
        return provider
    
    raise RuntimeError(
        "No LLM provider available. Please set one of:\n"
        "  - GROQ_API_KEY (recommended, free tier available at console.groq.com)\n"
        "  - OPENAI_API_KEY\n"
        "  - OLLAMA_HOST (and ensure Ollama is running)"
    )
