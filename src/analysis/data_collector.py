"""
Multi-source data collector for market analysis.
"""
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from loguru import logger


class DataCollector:
    """Collects data from multiple sources for market analysis."""
    
    def __init__(
        self,
        news_api_key: Optional[str] = None,
        odds_api_key: Optional[str] = None
    ):
        """
        Initialize data collector.
        
        Args:
            news_api_key: NewsAPI key
            odds_api_key: The Odds API key
        """
        self.news_api_key = news_api_key
        self.odds_api_key = odds_api_key
        
        logger.info("Data collector initialized")
    
    def collect_all_data(
        self,
        market_question: str,
        sport: Optional[str] = None,
        teams: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Collect all available data for a market.
        
        Args:
            market_question: Market question
            sport: Sport category
            teams: List of team names
            
        Returns:
            Dictionary with collected data
        """
        data = {
            "market_question": market_question,
            "sport": sport,
            "sources": []
        }
        
        # Collect news
        if self.news_api_key and teams:
            news = self.get_news(teams)
            if news:
                data["news"] = news
                data["sources"].append("news")
        
        # Collect statistics (placeholder)
        if teams:
            stats = self.get_statistics(teams, sport)
            if stats:
                data["statistics"] = stats
                data["sources"].append("statistics")
        
        # Collect injury reports (placeholder)
        if teams:
            injuries = self.get_injury_reports(teams, sport)
            if injuries:
                data["injuries"] = injuries
                data["sources"].append("injuries")
        
        # Collect odds comparison
        if self.odds_api_key and sport:
            odds = self.get_odds_comparison(sport, teams)
            if odds:
                data["odds_comparison"] = odds
                data["sources"].append("odds")
        
        logger.info(f"Collected data from {len(data['sources'])} sources")
        return data
    
    def get_news(self, teams: List[str], max_articles: int = 5) -> Optional[str]:
        """
        Get recent news about teams.
        
        Args:
            teams: List of team names
            max_articles: Maximum articles to fetch
            
        Returns:
            Formatted news string
        """
        if not self.news_api_key:
            return None
        
        try:
            # Build query
            query = " OR ".join(teams)
            
            # NewsAPI endpoint
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": query,
                "apiKey": self.news_api_key,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": max_articles,
                "from": (datetime.now() - timedelta(days=3)).isoformat()
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            articles = response.json().get("articles", [])
            
            if not articles:
                return None
            
            # Format news
            news_text = []
            for article in articles[:max_articles]:
                title = article.get("title", "")
                description = article.get("description", "")
                published = article.get("publishedAt", "")
                
                news_text.append(f"- {title}\n  {description}\n  Published: {published}")
            
            return "\n\n".join(news_text)
            
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            return None
    
    def get_statistics(self, teams: List[str], sport: Optional[str]) -> Optional[str]:
        """
        Get team/player statistics.
        
        This is a placeholder. In production, you would integrate with:
        - API-FOOTBALL for soccer
        - NBA API for basketball
        - etc.
        
        Args:
            teams: List of team names
            sport: Sport category
            
        Returns:
            Formatted statistics string
        """
        # Placeholder implementation
        logger.debug(f"Statistics collection not implemented for {sport}")
        return f"Statistics for {', '.join(teams)} would be collected here."
    
    def get_injury_reports(self, teams: List[str], sport: Optional[str]) -> Optional[str]:
        """
        Get injury reports for teams.
        
        This is a placeholder. In production, you would scrape from:
        - ESPN
        - Official team websites
        - Sports news sites
        
        Args:
            teams: List of team names
            sport: Sport category
            
        Returns:
            Formatted injury report string
        """
        # Placeholder implementation
        logger.debug(f"Injury reports not implemented for {sport}")
        return f"Injury reports for {', '.join(teams)} would be collected here."
    
    def get_odds_comparison(
        self,
        sport: str,
        teams: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Get odds from traditional bookmakers for comparison.
        
        Args:
            sport: Sport category
            teams: List of team names
            
        Returns:
            Formatted odds comparison string
        """
        if not self.odds_api_key:
            return None
        
        try:
            # The Odds API endpoint
            # Note: This is simplified. Real implementation would need proper sport mapping
            url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
            params = {
                "apiKey": self.odds_api_key,
                "regions": "us",
                "markets": "h2h",  # Head to head
                "oddsFormat": "decimal"
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            events = response.json()
            
            if not events:
                return None
            
            # Format odds
            odds_text = []
            for event in events[:3]:  # Limit to 3 events
                home = event.get("home_team", "")
                away = event.get("away_team", "")
                
                # Filter by teams if provided
                if teams and not any(team in [home, away] for team in teams):
                    continue
                
                odds_text.append(f"{home} vs {away}")
                
                for bookmaker in event.get("bookmakers", [])[:2]:  # Top 2 bookmakers
                    name = bookmaker.get("title", "")
                    markets = bookmaker.get("markets", [])
                    
                    if markets:
                        outcomes = markets[0].get("outcomes", [])
                        odds_text.append(f"  {name}: {outcomes}")
            
            return "\n".join(odds_text) if odds_text else None
            
        except Exception as e:
            logger.error(f"Error fetching odds: {e}")
            return None
    
    def extract_teams_from_question(self, question: str) -> List[str]:
        """
        Extract team names from market question.
        
        This is a simple implementation. Could be improved with NER or LLM.
        
        Args:
            question: Market question
            
        Returns:
            List of potential team names
        """
        # Simple heuristic: look for capitalized words
        words = question.split()
        teams = []
        
        for i, word in enumerate(words):
            if word[0].isupper() and word.lower() not in ["will", "the", "win", "vs", "against"]:
                # Check if next word is also capitalized (team name might be multi-word)
                if i + 1 < len(words) and words[i + 1][0].isupper():
                    teams.append(f"{word} {words[i + 1]}")
                else:
                    teams.append(word)
        
        return list(set(teams))  # Remove duplicates
