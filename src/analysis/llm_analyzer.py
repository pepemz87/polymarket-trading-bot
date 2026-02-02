"""
LLM-based market analysis using Gemini and Groq.
"""
import json
from typing import Optional, Dict, Any
from datetime import datetime
from loguru import logger

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    logger.warning("google-generativeai not installed")
    GEMINI_AVAILABLE = False

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    logger.warning("groq not installed")
    GROQ_AVAILABLE = False

from ..models.schemas import LLMPrediction


class LLMAnalyzer:
    """LLM-powered market analysis."""
    
    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        primary_provider: str = "gemini",
        gemini_model: str = "gemini-1.5-flash",
        groq_model: str = "llama-3.1-70b-versatile",
        temperature: float = 0.3
    ):
        """
        Initialize LLM analyzer.
        
        Args:
            gemini_api_key: Gemini API key
            groq_api_key: Groq API key
            primary_provider: 'gemini' or 'groq'
            gemini_model: Gemini model name
            groq_model: Groq model name
            temperature: Sampling temperature
        """
        self.primary_provider = primary_provider
        self.temperature = temperature
        
        # Initialize Gemini
        self.gemini_client = None
        self.gemini_model_name = gemini_model
        if GEMINI_AVAILABLE and gemini_api_key:
            try:
                genai.configure(api_key=gemini_api_key)
                self.gemini_client = genai.GenerativeModel(gemini_model)
                logger.info(f"Gemini initialized: {gemini_model}")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
        
        # Initialize Groq
        self.groq_client = None
        self.groq_model_name = groq_model
        if GROQ_AVAILABLE and groq_api_key:
            try:
                self.groq_client = Groq(api_key=groq_api_key)
                logger.info(f"Groq initialized: {groq_model}")
            except Exception as e:
                logger.error(f"Failed to initialize Groq: {e}")
    
    def analyze_market(
        self,
        market_question: str,
        market_id: str,
        current_yes_price: float,
        current_no_price: float,
        context_data: Dict[str, Any]
    ) -> Optional[LLMPrediction]:
        """
        Analyze a market and generate prediction.
        
        Args:
            market_question: Market question
            market_id: Market ID
            current_yes_price: Current YES price
            current_no_price: Current NO price
            context_data: Additional context (stats, news, etc.)
            
        Returns:
            LLMPrediction or None
        """
        # Build prompt
        prompt = self._build_prompt(
            market_question,
            current_yes_price,
            current_no_price,
            context_data
        )
        
        # Try primary provider first
        provider = self.primary_provider
        response = self._call_llm(prompt, provider)
        
        # Fallback to other provider if primary fails
        if not response:
            provider = "groq" if self.primary_provider == "gemini" else "gemini"
            logger.warning(f"Primary LLM failed, trying fallback: {provider}")
            response = self._call_llm(prompt, provider)
        
        if not response:
            logger.error("All LLM providers failed")
            return None
        
        # Parse response
        try:
            prediction = self._parse_response(
                response,
                market_id,
                market_question,
                current_yes_price,
                current_no_price,
                provider,
                context_data.get("sources", [])
            )
            return prediction
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return None
    
    def _build_prompt(
        self,
        market_question: str,
        yes_price: float,
        no_price: float,
        context: Dict[str, Any]
    ) -> str:
        """Build analysis prompt."""
        
        prompt = f"""You are an expert sports betting analyst. Analyze the following prediction market and provide your assessment.

MARKET QUESTION:
{market_question}

CURRENT MARKET PRICES:
- YES: {yes_price:.3f} (implied probability: {yes_price*100:.1f}%)
- NO: {no_price:.3f} (implied probability: {no_price*100:.1f}%)

"""
        
        # Add context data
        if context.get("statistics"):
            prompt += f"\nSTATISTICS:\n{context['statistics']}\n"
        
        if context.get("news"):
            prompt += f"\nRECENT NEWS:\n{context['news']}\n"
        
        if context.get("injuries"):
            prompt += f"\nINJURY REPORTS:\n{context['injuries']}\n"
        
        if context.get("odds_comparison"):
            prompt += f"\nODDS COMPARISON:\n{context['odds_comparison']}\n"
        
        prompt += """
TASK:
Analyze this market and provide your prediction in the following JSON format:

{
  "predicted_outcome": "yes" or "no",
  "confidence": <integer from 0-100>,
  "expected_probability": <float from 0-1>,
  "reasoning": "<detailed explanation of your analysis>"
}

GUIDELINES:
1. Consider all available data (statistics, news, injuries, odds)
2. Compare your estimated probability with the market price
3. Confidence should reflect how certain you are (70+ = high confidence)
4. Expected probability is YOUR estimate of the true probability
5. Reasoning should explain key factors in your decision
6. Be conservative - only high confidence if you have strong evidence

Respond ONLY with the JSON object, no additional text.
"""
        
        return prompt
    
    def _call_llm(self, prompt: str, provider: str) -> Optional[str]:
        """Call LLM provider."""
        
        try:
            if provider == "gemini" and self.gemini_client:
                response = self.gemini_client.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        temperature=self.temperature,
                        max_output_tokens=2000
                    )
                )
                return response.text
            
            elif provider == "groq" and self.groq_client:
                response = self.groq_client.chat.completions.create(
                    model=self.groq_model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=2000
                )
                return response.choices[0].message.content
            
            else:
                logger.error(f"Provider {provider} not available")
                return None
                
        except Exception as e:
            logger.error(f"LLM call failed ({provider}): {e}")
            return None
    
    def _parse_response(
        self,
        response: str,
        market_id: str,
        market_question: str,
        yes_price: float,
        no_price: float,
        provider: str,
        sources: list
    ) -> LLMPrediction:
        """Parse LLM response into structured prediction."""
        
        # Extract JSON from response
        response = response.strip()
        
        # Try to find JSON in response
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1].split("```")[0]
        
        # Parse JSON
        data = json.loads(response)
        
        # Create prediction object
        prediction = LLMPrediction(
            predicted_outcome=data["predicted_outcome"].lower(),
            confidence=int(data["confidence"]),
            expected_probability=float(data["expected_probability"]),
            reasoning=data["reasoning"],
            market_id=market_id,
            market_question=market_question,
            current_yes_price=yes_price,
            current_no_price=no_price,
            llm_provider=provider,
            llm_model=self.gemini_model_name if provider == "gemini" else self.groq_model_name,
            data_sources=sources,
            timestamp=datetime.utcnow()
        )
        
        logger.info(f"LLM prediction: {prediction.predicted_outcome} ({prediction.confidence}% confidence)")
        
        return prediction
