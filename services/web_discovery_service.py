"""
Web Source Discovery Service
Core business logic for NotebookLM-style source discovery
"""

import re
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from urllib.parse import urlparse
from collections import defaultdict
from duckduckgo_search import DDGS
import validators

logger = logging.getLogger(__name__)


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class WebSource:
    """Discovered web source"""
    source_id: str
    title: str
    url: str
    publisher: str
    content_type: str
    source_format: str  # ✅ NEW: pdf, youtube, web
    relevance_reason: str
    published_date: Optional[str] = None
    snippet: Optional[str] = None
    
    def to_dict(self):
        return asdict(self)


@dataclass
class QueryIntent:
    """Query interpretation metadata"""
    original_query: str
    normalized_query: str
    is_time_sensitive: bool
    domain: str
    time_range: Optional[str] = None


@dataclass
class SearchResult:
    """Raw search result"""
    title: str
    url: str
    snippet: str
    published_date: Optional[str] = None


# ============================================================================
# AUTHORITATIVE DOMAINS
# ============================================================================

AUTHORITATIVE_DOMAINS = {
    # News
    'reuters.com', 'bbc.com', 'nytimes.com', 'theguardian.com', 'apnews.com',
    'bloomberg.com', 'wsj.com', 'ft.com', 'economist.com', 'cnbc.com',
    
    # Tech
    'techcrunch.com', 'wired.com', 'arstechnica.com', 'theverge.com',
    'ieee.org', 'acm.org', 'mit.edu', 'stanford.edu', 'arxiv.org',
    
    # Academic
    'nature.com', 'science.org', 'sciencedirect.com', 'springer.com',
    'plos.org', 'ncbi.nlm.nih.gov', 'pubmed.ncbi.nlm.nih.gov',
    
    # Reference
    'wikipedia.org', 'britannica.com', 'investopedia.com',
    
    # Official
    'who.int', 'cdc.gov', 'nasa.gov', 'nih.gov'
}

# ============================================================================
# SOURCE FORMAT DETECTION
# ============================================================================

def detect_source_format(url: str, title: str = "") -> str:
    """
    Detect source format from URL and title.
    
    Returns:
        - 'pdf': PDF document
        - 'youtube': YouTube video
        - 'web': Regular webpage
    """
    url_lower = url.lower()
    title_lower = title.lower()
    
    # YouTube detection
    youtube_domains = ['youtube.com', 'youtu.be', 'm.youtube.com']
    if any(domain in url_lower for domain in youtube_domains):
        return 'youtube'
    
    # PDF detection
    if url_lower.endswith('.pdf'):
        return 'pdf'
    
    # Check if PDF in title or URL path
    if '.pdf' in url_lower or 'pdf' in title_lower:
        return 'pdf'
    
    # Default to web
    return 'web'


# ============================================================================
# WEB SOURCE DISCOVERY SERVICE
# ============================================================================

class WebDiscoveryService:
    """
    Service for discovering and curating web sources.
    
    Features:
    - Query interpretation with time-sensitivity detection
    - Multi-angle search intent expansion
    - DuckDuckGo web search (free, no API key)
    - Authority-based ranking
    - Publisher diversity enforcement
    - Structured source output
    """
    
    def __init__(self):
        self.ddgs = DDGS()
        logger.info("✅ WebDiscoveryService initialized")
    
    
    # ========================================================================
    # STEP 1: QUERY INTERPRETATION
    # ========================================================================
    
    def interpret_query(self, user_query: str) -> QueryIntent:
        """
        Analyze query to understand intent and requirements.
        
        Detects:
        - Time sensitivity (latest, recent, 2024)
        - Domain (news, tech, academic, health, etc.)
        - Time range (week, month, year)
        """
        normalized = user_query.strip().lower()
        
        # Time sensitivity detection
        time_keywords = [
            'latest', 'recent', 'new', 'current', 'today', 'this week',
            'this month', 'this year', '2024', '2025', '2026', 'now',
            'upcoming', 'breaking', 'update'
        ]
        is_time_sensitive = any(kw in normalized for kw in time_keywords)
        
        # Time range
        time_range = None
        if is_time_sensitive:
            if any(kw in normalized for kw in ['today', 'this week', 'breaking']):
                time_range = 'week'
            elif any(kw in normalized for kw in ['this month', 'recent']):
                time_range = 'month'
            else:
                time_range = 'year'
        
        # Domain identification
        domain = 'general'
        domain_keywords = {
            'news': ['news', 'breaking', 'reported', 'announced'],
            'tech': ['technology', 'software', 'ai', 'computing', 'tech', 'quantum', 'programming'],
            'academic': ['research', 'study', 'paper', 'journal', 'academic', 'scientific'],
            'health': ['health', 'medical', 'disease', 'treatment', 'medicine'],
            'finance': ['stock', 'market', 'finance', 'investment', 'economy'],
            'reference': ['what is', 'how to', 'guide', 'tutorial', 'definition']
        }
        
        for domain_name, keywords in domain_keywords.items():
            if any(keyword in normalized for keyword in keywords):
                domain = domain_name
                break
        
        logger.info(f"📋 Query interpreted: time_sensitive={is_time_sensitive}, domain={domain}")
        
        return QueryIntent(
            original_query=user_query,
            normalized_query=normalized,
            is_time_sensitive=is_time_sensitive,
            domain=domain,
            time_range=time_range
        )
    
    
    # ========================================================================
    # STEP 2: SEARCH INTENT EXPANSION
    # ========================================================================
    
    def expand_search_intents(self, query_intent: QueryIntent, num_intents: int = 4) -> List[str]:
        """
        Generate multiple search queries from different angles.
        
        Strategies:
        - Original query with time constraint
        - Domain-specific modifier
        - Practical/application angle
        - Authoritative sources angle
        """
        base_query = query_intent.normalized_query
        intents = []
        
        # Intent 1: Original with time
        if query_intent.is_time_sensitive:
            current_year = datetime.now().year
            intents.append(f"{base_query} {current_year}")
        else:
            intents.append(base_query)
        
        # Intent 2: Domain modifier
        domain_modifiers = {
            'news': 'news',
            'tech': 'technical overview',
            'academic': 'research',
            'health': 'medical information',
            'finance': 'analysis',
            'reference': 'guide'
        }
        modifier = domain_modifiers.get(query_intent.domain, 'overview')
        intents.append(f"{base_query} {modifier}")
        
        # Intent 3: Practical angle
        if query_intent.domain in ['tech', 'reference']:
            intents.append(f"{base_query} applications")
        elif query_intent.domain == 'news':
            intents.append(f"{base_query} latest updates")
        else:
            intents.append(f"{base_query} examples")
        
        # Intent 4: Authority angle
        authority_terms = {
            'news': 'official',
            'tech': 'documentation',
            'academic': 'peer reviewed',
            'health': 'clinical',
            'finance': 'expert',
            'reference': 'comprehensive'
        }
        authority = authority_terms.get(query_intent.domain, 'authoritative')
        intents.append(f"{base_query} {authority}")
        
        # Deduplicate
        seen = set()
        unique_intents = []
        for intent in intents[:num_intents]:
            if intent not in seen:
                seen.add(intent)
                unique_intents.append(intent)
        
        logger.info(f"🔍 Generated {len(unique_intents)} search intents")
        return unique_intents
    
    
    # ========================================================================
    # STEP 3: WEB SEARCH
    # ========================================================================
    
    def search_web(self, search_intents: List[str], results_per_intent: int = 15) -> List[SearchResult]:
        """
        Perform web searches using DuckDuckGo.
        
        Returns raw search results with title, URL, snippet.
        """
        all_results = []
        
        for intent in search_intents:
            try:
                logger.info(f"🌐 Searching: '{intent}'")
                
                # ✅ FIXED: Changed 'keywords' to 'query'
                results = self.ddgs.text(
                    query=intent,  # Changed from: keywords=intent
                    max_results=results_per_intent
                )
                
                for result in results:
                    search_result = SearchResult(
                        title=result.get('title', ''),
                        url=result.get('href', ''),
                        snippet=result.get('body', ''),
                        published_date=None
                    )
                    
                    if validators.url(search_result.url):
                        all_results.append(search_result)
                
            except Exception as e:
                logger.error(f"❌ Search error for '{intent}': {str(e)}")
                continue
        
        logger.info(f"📊 Collected {len(all_results)} search results")
        return all_results
    
    
    # ========================================================================
    # STEP 4: RANKING & FILTERING
    # ========================================================================
    
    @staticmethod
    def get_domain(url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return ''
    
    
    @staticmethod
    def is_authoritative(domain: str) -> bool:
        """Check if domain is authoritative"""
        if domain in AUTHORITATIVE_DOMAINS:
            return True
        if domain.endswith('.edu') or domain.endswith('.gov'):
            return True
        parts = domain.split('.')
        if len(parts) > 2:
            parent = '.'.join(parts[-2:])
            if parent in AUTHORITATIVE_DOMAINS:
                return True
        return False
    
    
    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize URL for deduplication"""
        try:
            parsed = urlparse(url)
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            return normalized.rstrip('/').lower()
        except:
            return url.lower()
    
    
    def calculate_relevance_score(
        self,
        result: SearchResult,
        original_query: str,
        is_time_sensitive: bool
    ) -> float:
        """
        Score search result by relevance (0-100).
        
        Factors:
        - Domain authority (0-40 points)
        - Query term coverage (0-30 points)
        - Title quality (0-20 points)
        - Content type (0-10 points)
        """
        score = 0.0
        
        # Domain authority
        domain = self.get_domain(result.url)
        if self.is_authoritative(domain):
            score += 40
        elif any(tld in domain for tld in ['.edu', '.gov', '.org']):
            score += 25
        else:
            score += 10
        
        # Query coverage
        query_terms = set(original_query.lower().split())
        title_lower = result.title.lower()
        snippet_lower = result.snippet.lower()
        
        title_matches = sum(1 for term in query_terms if term in title_lower)
        title_coverage = (title_matches / len(query_terms)) if query_terms else 0
        score += title_coverage * 20
        
        snippet_matches = sum(1 for term in query_terms if term in snippet_lower)
        snippet_coverage = (snippet_matches / len(query_terms)) if query_terms else 0
        score += snippet_coverage * 10
        
        # Title quality
        if 30 < len(result.title) < 100:
            score += 15
        elif len(result.title) >= 100:
            score += 10
        else:
            score += 5
        
        # Penalize clickbait
        clickbait = ['shocking', 'unbelievable', 'you won\'t believe', 'must see']
        if any(word in title_lower for word in clickbait):
            score -= 20
        
        # Content type hints
        content_indicators = {
            'article': ['article', 'blog', 'post'],
            'paper': ['paper', 'research', 'study'],
            'news': ['news', 'report', 'announced'],
            'docs': ['docs', 'documentation', 'guide']
        }
        
        for _, indicators in content_indicators.items():
            if any(ind in title_lower or ind in snippet_lower for ind in indicators):
                score += 10
                break
        
        return min(score, 100)
    
    
    def rank_and_filter(
        self,
        search_results: List[SearchResult],
        query_intent: QueryIntent,
        min_score: float = 20.0
    ) -> List[SearchResult]:
        """
        Rank results and remove duplicates/low-quality sources.
        """
        # Deduplicate
        seen_urls = set()
        unique_results = []
        
        for result in search_results:
            normalized = self.normalize_url(result.url)
            if normalized not in seen_urls:
                seen_urls.add(normalized)
                unique_results.append(result)
        
        logger.info(f"✂️ After deduplication: {len(unique_results)} unique URLs")
        
        # Score and filter
        scored_results = []
        for result in unique_results:
            score = self.calculate_relevance_score(
                result,
                query_intent.original_query,
                query_intent.is_time_sensitive
            )
            if score >= min_score:
                scored_results.append((score, result))
        
        logger.info(f"🎯 After filtering: {len(scored_results)} sources")
        
        # Sort by score
        scored_results.sort(key=lambda x: x[0], reverse=True)
        
        return [result for score, result in scored_results]
    
    
    # ========================================================================
    # STEP 5: CURATION
    # ========================================================================
    
    def curate_sources(
        self,
        ranked_results: List[SearchResult],
        max_sources: int = 10,
        max_per_domain: int = 2
    ) -> List[SearchResult]:
        """
        Select top N sources with publisher diversity.
        """
        domain_counts = defaultdict(int)
        selected = []
        
        for result in ranked_results:
            if len(selected) >= max_sources:
                break
            
            domain = self.get_domain(result.url)
            
            if domain_counts[domain] >= max_per_domain:
                continue
            
            selected.append(result)
            domain_counts[domain] += 1
        
        logger.info(f"📚 Curated {len(selected)} diverse sources")
        return selected
    
    
    # ========================================================================
    # STEP 6: CONVERSION
    # ========================================================================
    
    @staticmethod
    def infer_content_type(result: SearchResult) -> str:
        """Infer content type from title/URL"""
        title_lower = result.title.lower()
        url_lower = result.url.lower()
        
        if any(term in title_lower for term in ['paper', 'journal', 'study', 'research']):
            return 'paper'
        if any(term in title_lower for term in ['news', 'breaking', 'reported']):
            return 'news'
        if 'docs' in url_lower or 'documentation' in title_lower:
            return 'documentation'
        if 'blog' in url_lower or 'blog' in title_lower:
            return 'blog'
        
        return 'article'
    
    
    def generate_relevance_reason(
        self,
        result: SearchResult,
        query_intent: QueryIntent
    ) -> str:
        """Generate explanation for why source was selected"""
        domain = self.get_domain(result.url)
        reasons = []
        
        if self.is_authoritative(domain):
            reasons.append("Authoritative source")
        
        if query_intent.domain == 'news' and 'news' in result.title.lower():
            reasons.append("Recent news coverage")
        elif query_intent.domain == 'academic' and 'research' in result.title.lower():
            reasons.append("Academic research")
        elif query_intent.domain == 'tech' and any(t in domain for t in ['tech', 'ieee', 'acm']):
            reasons.append("Technical authority")
        
        if query_intent.is_time_sensitive:
            reasons.append("Recent publication")
        
        query_terms = query_intent.normalized_query.split()
        if len(query_terms) > 2:
            matches = sum(1 for term in query_terms if term in result.title.lower())
            if matches >= len(query_terms) * 0.7:
                reasons.append("High query relevance")
        
        if not reasons:
            reasons.append("Relevant to query")
        
        return "; ".join(reasons[:2])
    
    
    def convert_to_sources(
    self,
    curated_results: List[SearchResult],
    query_intent: QueryIntent
) -> List[WebSource]:
        """Convert SearchResults to WebSource objects"""
        sources = []
        
        for idx, result in enumerate(curated_results, 1):
            # ✅ Detect source format
            source_format = detect_source_format(result.url, result.title)
            
            source = WebSource(
                source_id=f"src_{idx:03d}",
                title=result.title,
                url=result.url,
                publisher=self.get_domain(result.url),
                content_type=self.infer_content_type(result),
                source_format=source_format,  # ✅ NEW
                relevance_reason=self.generate_relevance_reason(result, query_intent),
                published_date=result.published_date,
                snippet=result.snippet[:200] if result.snippet else None
            )
            sources.append(source)
        
        logger.info(f"✅ Converted {len(sources)} sources")
        return sources
    
    
    # ========================================================================
    # MAIN ORCHESTRATION
    # ========================================================================
    
    def discover_sources(
        self,
        user_query: str,
        max_sources: int = 10,
        results_per_intent: int = 15,
        num_intents: int = 4
    ) -> List[WebSource]:
        """
        Main orchestration: Discover and curate web sources.
        
        Pipeline:
        1. Interpret query
        2. Expand search intents
        3. Search web (DuckDuckGo)
        4. Rank and filter
        5. Curate for diversity
        6. Convert to structured sources
        
        Args:
            user_query: Natural language query
            max_sources: Maximum sources to return
            results_per_intent: Results per search query
            num_intents: Number of search variations
            
        Returns:
            List of WebSource objects
        """
        try:
            logger.info(f"🚀 Starting source discovery: '{user_query}'")
            
            # Step 1: Interpret
            query_intent = self.interpret_query(user_query)
            
            # Step 2: Expand
            search_intents = self.expand_search_intents(query_intent, num_intents)
            
            # Step 3: Search
            search_results = self.search_web(search_intents, results_per_intent)
            
            if not search_results:
                logger.warning("⚠️ No search results found")
                return []
            
            # Step 4: Rank & Filter
            ranked_results = self.rank_and_filter(search_results, query_intent)
            
            if not ranked_results:
                logger.warning("⚠️ No results passed filtering")
                return []
            
            # Step 5: Curate
            curated_results = self.curate_sources(ranked_results, max_sources)
            
            # Step 6: Convert
            sources = self.convert_to_sources(curated_results, query_intent)
            
            logger.info(f"✅ Discovery complete: {len(sources)} sources")
            return sources
            
        except Exception as e:
            logger.error(f"❌ Source discovery error: {str(e)}", exc_info=True)
            raise