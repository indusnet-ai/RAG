# import logging
# import os
# from typing import List, Dict, Any, Optional, Tuple
# from dataclasses import dataclass
# from pathlib import Path
# from urllib.parse import urlparse, urljoin
# import time
# from datetime import datetime

# from firecrawl import Firecrawl
# from services.doc_processor import DocumentChunk
# from dotenv import load_dotenv
# load_dotenv()

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


# @dataclass
# class WebPageData:
#     """Represents scraped web page data with additional metadata"""
#     url: str
#     title: str
#     content: str
#     metadata: Dict[str, Any]
#     success: bool
#     error: Optional[str] = None


# class WebScraper:
#     def __init__(self, api_key: str):
#         self.api_key = api_key
#         self.app = Firecrawl(api_key=api_key)
        
#         logger.info("WebScraper initialized with Firecrawl")
    
#     def scrape_url(
#     self,
#     url: str,
#     chunk_size: int = 1000,
#     chunk_overlap: int = 100,
#     wait_for_results: int = 30
# ) -> List[DocumentChunk]:
#         """
#         Scrape a single URL and return chunks.
#         """
#         if not self._is_valid_url(url):
#             raise ValueError(f"Invalid URL format: {url}")
        
#         logger.info(f"Scraping URL: {url}")
        
#         try:
#             scrape_params = {
#             "formats": ["markdown", "html"],
#             "timeout": wait_for_results * 1000,
#             "actions": [
#                 {"action": "wait", "milliseconds": 5000}
#             ]
#         }
#             result = self.app.scrape(url, **scrape_params)
#             page_data = self._process_firecrawl_result(result, url)
            
#             chunks = self._create_chunks_from_web_content(
#                 page_data, 
#                 chunk_size, 
#                 chunk_overlap
#             )
            
#             logger.info(f"Successfully scraped {url}: {len(chunks)} chunks created")
#             return chunks
            
#         except Exception as e:
#             logger.error(f"Error scraping URL {url}: {str(e)}")
#             raise
    
#     def crawl_recursively(
#     self,
#     url: str,
#     chunk_size: int = 1000,
#     chunk_overlap: int = 100,
#     max_pages: int = 100
# ) -> Tuple[List[DocumentChunk], List[str]]:
#         """
#         Recursively crawl by extracting and following HTML links
#         """
#         from bs4 import BeautifulSoup
        
#         base_domain = urlparse(url).netloc
#         visited = set()
#         to_visit = [url]
#         all_chunks = []
#         crawled_urls = []
        
#         logger.info(f"🔥 Starting recursive crawl from: {url} (max {max_pages} pages)")
        
#         def is_valid_internal_url(check_url):
#             """Filter out external links and social media"""
#             parsed = urlparse(check_url)
            
#             # Must be same domain
#             if parsed.netloc != base_domain:
#                 return False
            
#             # Exclude social media, files, etc.
#             exclude_patterns = [
#                 'facebook.com', 'twitter.com', 'x.com', 'linkedin.com',
#                 'instagram.com', 'youtube.com', 'sharer',
#                 '.pdf', '.jpg', '.png', '.zip', '.doc', '.xls'
#             ]
            
#             for pattern in exclude_patterns:
#                 if pattern in check_url.lower():
#                     return False
            
#             return True
        
#         while to_visit and len(visited) < max_pages:
#             current_url = to_visit.pop(0)
            
#             # Skip if already visited
#             if current_url in visited:
#                 continue
            
#             logger.info(f"  📄 [{len(visited)+1}/{max_pages}] Crawling: {current_url}")
            
#             try:
#                 # Scrape the page
#                 result = self.app.scrape(
#                     current_url,
#                     formats=['html', 'markdown'],
#                     wait_for=5000
#                 )
                
#                 visited.add(current_url)
                
#                 # Process content into chunks
#                 page_data = self._process_firecrawl_result(result, current_url)
#                 chunks = self._create_chunks_from_web_content(
#                     page_data,
#                     chunk_size,
#                     chunk_overlap
#                 )
                
#                 if chunks:  # Only add if content exists
#                     all_chunks.extend(chunks)
#                     crawled_urls.append(current_url)
#                     logger.info(f"      ✓ Generated {len(chunks)} chunks")
#                 else:
#                     logger.warning(f"      ⚠️ No content extracted")
                
#                 # Extract links from HTML
#                 soup = BeautifulSoup(result.html, 'html.parser')
#                 new_links = 0
                
#                 for link in soup.find_all('a', href=True):
#                     href = link['href']
#                     full_url = urljoin(current_url, href)
                    
#                     # Filter and add to queue
#                     if is_valid_internal_url(full_url) and full_url not in visited:
#                         if full_url not in to_visit:
#                             to_visit.append(full_url)
#                             new_links += 1
                
#                 logger.info(f"      🔗 Found {new_links} new links")
                
#             except Exception as e:
#                 logger.error(f"      ✗ Error: {str(e)}")
#                 visited.add(current_url)
#                 continue
        
#         logger.info(f"🎉 Recursive crawl complete: {len(all_chunks)} chunks from {len(crawled_urls)} pages")
#         return all_chunks, crawled_urls
            
#     # except Exception as e:
#     #     logger.error(f"Error crawling URL {url}: {str(e)}")
#     #     raise
    
#     def _process_firecrawl_result(self, result: Any, url: str) -> WebPageData:
#         """Process Firecrawl result into WebPageData"""
#         try:
#             content = result.markdown
#             metadata_dict = result.metadata_dict
#             metadata = {
#                 'scraped_at': datetime.now().isoformat(),
#                 'original_url': url,
#                 'title': metadata_dict.get('title', ''),
#                 'description': metadata_dict.get('description', ''),
#                 'keywords': metadata_dict.get('keywords', []),
#                 'language': metadata_dict.get('language', 'en'),
#                 'word_count': len(content.split()) if content else 0,
#                 'character_count': len(content) if content else 0,
#                 'domain': urlparse(url).netloc
#             }
            
#             return WebPageData(
#                 url=url,
#                 title=metadata['title'] or f"Web Page - {metadata['domain']}",
#                 content=content,
#                 metadata=metadata,
#                 success=True
#             )
            
#         except Exception as e:
#             logger.error(f"Error processing Firecrawl result: {str(e)}")
#             return WebPageData(
#                 url=url,
#                 title=f"Error - {urlparse(url).netloc}",
#                 content="",
#                 metadata={'error': str(e), 'scraped_at': datetime.now().isoformat()},
#                 success=False,
#                 error=str(e)
#             )
    
#     def _create_chunks_from_web_content(
#         self,
#         page_data: WebPageData,
#         chunk_size: int,
#         chunk_overlap: int
#     ) -> List[DocumentChunk]:
#         """Create chunks from web page content"""
#         if not page_data.success or not page_data.content.strip():
#             logger.warning(f"No content to process for {page_data.url}")
#             return []
        
#         chunks = []
#         content = page_data.content
#         start = 0
#         chunk_index = 0
        
#         while start < len(content):
#             end = min(start + chunk_size, len(content))
            
#             # Try to break at natural boundaries
#             if end < len(content):
#                 # Try to break at double newline (paragraph)
#                 last_double_newline = content.rfind('\n\n', start, end)
#                 if last_double_newline > start + chunk_size * 0.3:
#                     end = last_double_newline + 2
#                 else:
#                     # Try to break at period
#                     last_period = content.rfind('.', start, end)
#                     if last_period > start + chunk_size * 0.5:
#                         end = last_period + 1
            
#             chunk_text = content[start:end].strip()
            
#             if chunk_text:
#                 chunk_metadata = page_data.metadata.copy()
#                 chunk_metadata.update({
#                     'chunk_character_start': start,
#                     'chunk_character_end': end - 1,
#                     'url_fragment': f"{page_data.url}#chunk-{chunk_index}"
#                 })
                
#                 chunk = DocumentChunk(
#                     content=chunk_text,
#                     source_file=page_data.title,
#                     source_type='web',
#                     page_number=None,
#                     chunk_index=chunk_index,
#                     start_char=start,
#                     end_char=end-1,
#                     metadata=chunk_metadata
#                 )
                
#                 chunks.append(chunk)
#                 chunk_index += 1
            
#             start = max(start + chunk_size - chunk_overlap, end)
        
#         return chunks
    
#     def batch_scrape_urls(
#         self,
#         urls: List[str],
#         chunk_size: int = 1000,
#         chunk_overlap: int = 100,
#         delay_between_requests: float = 1.0
#     ) -> List[List[DocumentChunk]]:
#         """Scrape multiple URLs in batch"""
#         all_chunks = []
#         for i, url in enumerate(urls):
#             try:
#                 chunks = self.scrape_url(url, chunk_size, chunk_overlap)
#                 all_chunks.append(chunks)
#                 logger.info(f"Successfully scraped {url}: {len(chunks)} chunks")
                
#                 if i < len(urls) - 1:
#                     time.sleep(delay_between_requests)
                    
#             except Exception as e:
#                 logger.error(f"Failed to scrape {url}: {str(e)}")
#                 all_chunks.append([])
        
#         total_chunks = sum(len(chunks) for chunks in all_chunks)
#         logger.info(f"Batch scraping complete: {total_chunks} total chunks from {len(urls)} URLs")
        
#         return all_chunks
    
#     def get_url_preview(self, url: str) -> Dict[str, Any]:
#         """Get a quick preview of a URL without full scraping"""
#         try:
#             result = self.app.scrape(url, **{
#                 'formats': ['markdown'],
#                 'timeout': 10000
#             })
            
#             content = result.markdown
#             metadata_dict = result.metadata_dict
            
#             preview_info = {
#                 'url': url,
#                 'title': metadata_dict.get('title', ''),
#                 'description': metadata_dict.get('description', ''),
#                 'word_count': len(content.split()) if content else 0,
#                 'character_count': len(content) if content else 0,
#                 'domain': urlparse(url).netloc,
#                 'content_preview': content[:500] + '...' if len(content) > 500 else content,
#                 'language': metadata_dict.get('language', 'unknown')
#             }
#             return preview_info
            
#         except Exception as e:
#             logger.error(f"Error getting URL preview: {str(e)}")
#             return {'error': str(e)}
    
#     def _is_valid_url(self, url: str) -> bool:
#         """Validate URL format"""
#         try:
#             result = urlparse(url)
#             return all([result.scheme, result.netloc])
#         except:
#             return False


# if __name__ == "__main__":
#     api_key = os.getenv("FIRECRAWL_API_KEY")
#     if not api_key:
#         print("Please set FIRECRAWL_API_KEY environment variable")
#         exit(1)
    
#     scraper = WebScraper(api_key)
    
#     try:
#         # Test scraping single URL
#         test_url = "https://blog.dailydoseofds.com/p/5-chunking-strategies-for-rag"
#         print(f"\n{'='*60}")
#         print(f"TEST 1: Scraping single URL")
#         print(f"{'='*60}")
#         chunks = scraper.scrape_url(test_url)
#         print(f"✅ Generated {len(chunks)} chunks")
        
#         # Test crawling
#         print(f"\n{'='*60}")
#         print(f"TEST 2: Crawling website")
#         print(f"{'='*60}")
#         crawl_url = "https://example.com"
#         chunks, crawled_urls = scraper.crawl_url(crawl_url, max_pages=5)
#         print(f"✅ Crawled {len(crawled_urls)} pages")
#         print(f"📄 Pages crawled:")
#         for url in crawled_urls:
#             print(f"   - {url}")
#         print(f"✅ Total chunks: {len(chunks)}")
        
#     except Exception as e:
#         print(f"❌ Error in test: {e}")

# import logging
# import os
# from typing import List, Dict, Any, Optional, Tuple
# from dataclasses import dataclass
# from pathlib import Path
# from urllib.parse import urlparse, urljoin
# import time
# from datetime import datetime
 
# from firecrawl import Firecrawl
# from services.doc_processor import DocumentChunk
# from dotenv import load_dotenv
# load_dotenv()
 
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)
 
 
# @dataclass
# class WebPageData:
#     """Represents scraped web page data with additional metadata"""
#     url: str
#     title: str
#     content: str
#     metadata: Dict[str, Any]
#     success: bool
#     error: Optional[str] = None
 
 
# class WebScraper:
#     def __init__(self, api_key: str):
#         self.api_key = api_key
#         self.app = Firecrawl(api_key=api_key)
       
#         logger.info("WebScraper initialized with Firecrawl")
   
#     def scrape_url(
#     self,
#     url: str,
#     chunk_size: int = 1000,
#     chunk_overlap: int = 100,
#     wait_for_results: int = 30
# ) -> List[DocumentChunk]:
#         """
#         Scrape a single URL and return chunks.
#         """
#         if not self._is_valid_url(url):
#             raise ValueError(f"Invalid URL format: {url}")
       
#         logger.info(f"Scraping URL: {url}")
       
#         try:
#             scrape_params = {
#             "formats": ["markdown", "html"],
#             "timeout": wait_for_results * 1000,
#             "actions": [
#                 {"action": "wait", "milliseconds": 5000}
#             ]
#         }
#             result = self.app.scrape(url, **scrape_params)
#             page_data = self._process_firecrawl_result(result, url)
           
#             chunks = self._create_chunks_from_web_content(
#                 page_data,
#                 chunk_size,
#                 chunk_overlap
#             )
           
#             logger.info(f"Successfully scraped {url}: {len(chunks)} chunks created")
#             return chunks
           
#         except Exception as e:
#             logger.error(f"Error scraping URL {url}: {str(e)}")
#             raise
   
#     def crawl_recursively(
#     self,
#     url: str,
#     chunk_size: int = 1000,
#     chunk_overlap: int = 100,
#     max_pages: int = 100
# ) -> Tuple[List[DocumentChunk], List[str]]:
#         """
#         Recursively crawl by extracting and following HTML links
#         """
#         from bs4 import BeautifulSoup
       
#         base_domain = urlparse(url).netloc
#         visited = set()
#         to_visit = [url]
#         all_chunks = []
#         crawled_urls = []
       
#         logger.info(f"🔥 Starting recursive crawl from: {url} (max {max_pages} pages)")
       
#         def is_valid_internal_url(check_url):
#             """Filter out external links and social media"""
#             parsed = urlparse(check_url)
           
#             # Must be same domain
#             if parsed.netloc != base_domain:
#                 return False
           
#             # Exclude social media, files, etc.
#             exclude_patterns = [
#                 'facebook.com', 'twitter.com', 'x.com', 'linkedin.com',
#                 'instagram.com', 'youtube.com', 'sharer',
#                 '.pdf', '.jpg', '.png', '.zip', '.doc', '.xls'
#             ]
           
#             for pattern in exclude_patterns:
#                 if pattern in check_url.lower():
#                     return False
           
#             return True
       
#         while to_visit and len(visited) < max_pages:
#             current_url = to_visit.pop(0)
           
#             # Skip if already visited
#             if current_url in visited:
#                 continue
           
#             logger.info(f"  📄 [{len(visited)+1}/{max_pages}] Crawling: {current_url}")
           
#             try:
#                 # Scrape the page
#                 result = self.app.scrape(
#                     current_url,
#                     formats=['html', 'markdown'],
#                     wait_for=5000
#                 )
               
#                 visited.add(current_url)
               
#                 # Process content into chunks
#                 page_data = self._process_firecrawl_result(result, current_url)
#                 chunks = self._create_chunks_from_web_content(
#                     page_data,
#                     chunk_size,
#                     chunk_overlap
#                 )
               
#                 if chunks:  # Only add if content exists
#                     all_chunks.extend(chunks)
#                     crawled_urls.append(current_url)
#                     logger.info(f"      ✓ Generated {len(chunks)} chunks")
#                 else:
#                     logger.warning(f"      ⚠️ No content extracted")
               
#                 # Extract links from HTML
#                 soup = BeautifulSoup(result.html, 'html.parser')
#                 new_links = 0
               
#                 for link in soup.find_all('a', href=True):
#                     href = link['href']
#                     full_url = urljoin(current_url, href)
                   
#                     # Filter and add to queue
#                     if is_valid_internal_url(full_url) and full_url not in visited:
#                         if full_url not in to_visit:
#                             to_visit.append(full_url)
#                             new_links += 1
               
#                 logger.info(f"      🔗 Found {new_links} new links")
               
#             except Exception as e:
#                 logger.error(f"      ✗ Error: {str(e)}")
#                 visited.add(current_url)
#                 continue
       
#         logger.info(f"🎉 Recursive crawl complete: {len(all_chunks)} chunks from {len(crawled_urls)} pages")
#         return all_chunks, crawled_urls
           
#     # except Exception as e:
#     #     logger.error(f"Error crawling URL {url}: {str(e)}")
#     #     raise
   
#     def _process_firecrawl_result(self, result: Any, url: str) -> WebPageData:
#         """Process Firecrawl result into WebPageData"""
#         try:
#             content = result.markdown
#             metadata_dict = result.metadata_dict
#             metadata = {
#                 'scraped_at': datetime.now().isoformat(),
#                 'original_url': url,
#                 'title': metadata_dict.get('title', ''),
#                 'description': metadata_dict.get('description', ''),
#                 'keywords': metadata_dict.get('keywords', []),
#                 'language': metadata_dict.get('language', 'en'),
#                 'word_count': len(content.split()) if content else 0,
#                 'character_count': len(content) if content else 0,
#                 'domain': urlparse(url).netloc
#             }
           
#             return WebPageData(
#                 url=url,
#                 title=metadata['title'] or f"Web Page - {metadata['domain']}",
#                 content=content,
#                 metadata=metadata,
#                 success=True
#             )
           
#         except Exception as e:
#             logger.error(f"Error processing Firecrawl result: {str(e)}")
#             return WebPageData(
#                 url=url,
#                 title=f"Error - {urlparse(url).netloc}",
#                 content="",
#                 metadata={'error': str(e), 'scraped_at': datetime.now().isoformat()},
#                 success=False,
#                 error=str(e)
#             )
   
#     def _create_chunks_from_web_content(
#         self,
#         page_data: WebPageData,
#         chunk_size: int,
#         chunk_overlap: int
#     ) -> List[DocumentChunk]:
#         """Create chunks from web page content"""
#         if not page_data.success or not page_data.content.strip():
#             logger.warning(f"No content to process for {page_data.url}")
#             return []
       
#         chunks = []
#         content = page_data.content
#         start = 0
#         chunk_index = 0
       
#         while start < len(content):
#             end = min(start + chunk_size, len(content))
           
#             # Try to break at natural boundaries
#             if end < len(content):
#                 # Try to break at double newline (paragraph)
#                 last_double_newline = content.rfind('\n\n', start, end)
#                 if last_double_newline > start + chunk_size * 0.3:
#                     end = last_double_newline + 2
#                 else:
#                     # Try to break at period
#                     last_period = content.rfind('.', start, end)
#                     if last_period > start + chunk_size * 0.5:
#                         end = last_period + 1
           
#             chunk_text = content[start:end].strip()
           
#             if chunk_text:
#                 chunk_metadata = page_data.metadata.copy()
#                 chunk_metadata.update({
#                     'chunk_character_start': start,
#                     'chunk_character_end': end - 1,
#                     'url_fragment': f"{page_data.url}#chunk-{chunk_index}"
#                 })
               
#                 chunk = DocumentChunk(
#                     content=chunk_text,
#                     source_file=page_data.title,
#                     source_type='web',
#                     page_number=None,
#                     chunk_index=chunk_index,
#                     start_char=start,
#                     end_char=end-1,
#                     metadata=chunk_metadata
#                 )
               
#                 chunks.append(chunk)
#                 chunk_index += 1
           
#             start = max(start + chunk_size - chunk_overlap, end)
       
#         return chunks
   
#     def batch_scrape_urls(
#         self,
#         urls: List[str],
#         chunk_size: int = 1000,
#         chunk_overlap: int = 100,
#         delay_between_requests: float = 1.0
#     ) -> List[List[DocumentChunk]]:
#         """Scrape multiple URLs in batch"""
#         all_chunks = []
#         for i, url in enumerate(urls):
#             try:
#                 chunks = self.scrape_url(url, chunk_size, chunk_overlap)
#                 all_chunks.append(chunks)
#                 logger.info(f"Successfully scraped {url}: {len(chunks)} chunks")
               
#                 if i < len(urls) - 1:
#                     time.sleep(delay_between_requests)
                   
#             except Exception as e:
#                 logger.error(f"Failed to scrape {url}: {str(e)}")
#                 all_chunks.append([])
       
#         total_chunks = sum(len(chunks) for chunks in all_chunks)
#         logger.info(f"Batch scraping complete: {total_chunks} total chunks from {len(urls)} URLs")
       
#         return all_chunks
   
#     def get_url_preview(self, url: str) -> Dict[str, Any]:
#         """Get a quick preview of a URL without full scraping"""
#         try:
#             result = self.app.scrape(url, **{
#                 'formats': ['markdown'],
#                 'timeout': 10000
#             })
           
#             content = result.markdown
#             metadata_dict = result.metadata_dict
           
#             preview_info = {
#                 'url': url,
#                 'title': metadata_dict.get('title', ''),
#                 'description': metadata_dict.get('description', ''),
#                 'word_count': len(content.split()) if content else 0,
#                 'character_count': len(content) if content else 0,
#                 'domain': urlparse(url).netloc,
#                 'content_preview': content[:500] + '...' if len(content) > 500 else content,
#                 'language': metadata_dict.get('language', 'unknown')
#             }
#             return preview_info
           
#         except Exception as e:
#             logger.error(f"Error getting URL preview: {str(e)}")
#             return {'error': str(e)}
   
#     def _is_valid_url(self, url: str) -> bool:
#         """Validate URL format"""
#         try:
#             result = urlparse(url)
#             return all([result.scheme, result.netloc])
#         except:
#             return False
 
 
# if __name__ == "__main__":
#     api_key = os.getenv("FIRECRAWL_API_KEY")
#     if not api_key:
#         print("Please set FIRECRAWL_API_KEY environment variable")
#         exit(1)
   
#     scraper = WebScraper(api_key)
   
#     try:
#         # Test scraping single URL
#         test_url = "https://blog.dailydoseofds.com/p/5-chunking-strategies-for-rag"
#         print(f"\n{'='*60}")
#         print(f"TEST 1: Scraping single URL")
#         print(f"{'='*60}")
#         chunks = scraper.scrape_url(test_url)
#         print(f"✅ Generated {len(chunks)} chunks")
       
#         # Test crawling
#         print(f"\n{'='*60}")
#         print(f"TEST 2: Crawling website")
#         print(f"{'='*60}")
#         crawl_url = "https://example.com"
#         chunks, crawled_urls = scraper.crawl_url(crawl_url, max_pages=5)
#         print(f"✅ Crawled {len(crawled_urls)} pages")
#         print(f"📄 Pages crawled:")
#         for url in crawled_urls:
#             print(f"   - {url}")
#         print(f"✅ Total chunks: {len(chunks)}")
       
#     except Exception as e:
#         print(f"❌ Error in test: {e}")
 
import logging
import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urljoin
import time
from datetime import datetime
from bs4 import BeautifulSoup
 
from crawl4ai import AsyncWebCrawler
import asyncio
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from crawl4ai.chunking_strategy import RegexChunking
from services.doc_processor import DocumentChunk
from crawl4ai import AsyncWebCrawler, BrowserConfig
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
from crawl4ai import UndetectedAdapter
from crawl4ai import CrawlerRunConfig
 
 
from dotenv import load_dotenv
 
load_dotenv()
 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
 
 
@dataclass
class WebPageData:
    """Represents scraped web page data with additional metadata"""
    url: str
    title: str
    content: str
    metadata: Dict[str, Any]
    success: bool
    error: Optional[str] = None
 
 
# class WebScraper:
#     def __init__(self, api_key: str = None):
#         """Initialize WebScraper - no crawler instance needed"""
#         self.crawler_config = {"verbose": False, "headless": True}
#         logger.info("WebScraper initialized with Crawl4AI")
class WebScraper:
    def __init__(self, api_key: str = None, use_undetected: bool = False):
        browser_config = BrowserConfig(headless=True)
 
        adapters = []
        if use_undetected:
            adapters.append(UndetectedAdapter())
 
        crawler_strategy = AsyncPlaywrightCrawlerStrategy(
            browser_config=browser_config,
            adapters=adapters
        )
 
        self.crawler_config = {
            "crawler_strategy": crawler_strategy,
            "verbose": False
        }
 
        logger.info(
            f"WebScraper initialized with Crawl4AI | undetected={use_undetected}"
        )
 
   
    async def scrape_url(
        self,
        url: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
        wait_for_results: int = 30
    ) -> List[DocumentChunk]:
        """Scrape a single URL"""
        if not self._is_valid_url(url):
            raise ValueError(f"Invalid URL format: {url}")
       
        logger.info(f"Scraping URL: {url}")
       
        try:
            # ✅ Use context manager (official pattern)
            async with AsyncWebCrawler(**self.crawler_config) as crawler:
                result = await crawler.arun(
                    url=url,
                    word_count_threshold=10,
                    bypass_cache=True
                )
               
                # Check success
                if not result.success:
                    raise Exception(f"Crawl failed: {result.error_message if hasattr(result, 'error_message') else 'Unknown error'}")
               
                page_data = self._process_crawl4ai_result(result, url)
                chunks = self._create_chunks_from_web_content(
                    page_data, chunk_size, chunk_overlap
                )
               
                logger.info(f"Successfully scraped {url}: {len(chunks)} chunks created")
                return chunks
               
        except Exception as e:
            logger.error(f"Error scraping URL {url}: {str(e)}")
            raise
   
    async def crawl_recursively(
        self,
        url: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
        max_pages: int = 100
    ) -> Tuple[List[DocumentChunk], List[str]]:
        """Recursively crawl by extracting and following HTML links"""
        base_domain = urlparse(url).netloc
        visited = set()
        to_visit = [url]
        all_chunks = []
        crawled_urls = []
       
        logger.info(f"🔥 Starting recursive crawl from: {url} (max {max_pages} pages)")
       
        def is_valid_internal_url(check_url):
            """Filter out external links and social media"""
            parsed = urlparse(check_url)
           
            # Must be same domain
            if parsed.netloc != base_domain:
                return False
           
            # Exclude social media, files, etc.
            exclude_patterns = [
                'facebook.com', 'twitter.com', 'x.com', 'linkedin.com',
                'instagram.com', 'youtube.com', 'sharer',
                '.pdf', '.jpg', '.png', '.zip', '.doc', '.xls'
            ]
           
            for pattern in exclude_patterns:
                if pattern in check_url.lower():
                    return False
           
            return True
       
        # ✅ Use context manager for the entire crawl session
        async with AsyncWebCrawler(**self.crawler_config) as crawler:
            while to_visit and len(visited) < max_pages:
                current_url = to_visit.pop(0)
               
                # Skip if already visited
                if current_url in visited:
                    continue
               
                logger.info(f"  📄 [{len(visited)+1}/{max_pages}] Crawling: {current_url}")
               
                try:
                    # ✅ Use the same crawler instance
                    result = await crawler.arun(
                        url=current_url,
                        word_count_threshold=10,
                        bypass_cache=True
                    )
 
                    visited.add(current_url)
                   
                    # Process content into chunks
                    page_data = self._process_crawl4ai_result(result, current_url)
                    chunks = self._create_chunks_from_web_content(
                        page_data,
                        chunk_size,
                        chunk_overlap
                    )
                   
                    if chunks:  # Only add if content exists
                        all_chunks.extend(chunks)
                        crawled_urls.append(current_url)
                        logger.info(f"      ✓ Generated {len(chunks)} chunks")
                    else:
                        logger.warning(f"      ⚠️ No content extracted")
                   
                    # Extract links from HTML using BeautifulSoup
                    if hasattr(result, 'html') and result.html:
                        soup = BeautifulSoup(result.html, 'html.parser')
                        new_links = 0
                       
                        for link in soup.find_all('a', href=True):
                            href = link['href']
                            full_url = urljoin(current_url, href)
                           
                            # Filter and add to queue
                            if is_valid_internal_url(full_url) and full_url not in visited:
                                if full_url not in to_visit:
                                    to_visit.append(full_url)
                                    new_links += 1
                       
                        logger.info(f"      🔗 Found {new_links} new links")
                   
                except Exception as e:
                    logger.error(f"      ✗ Error: {str(e)}")
                    visited.add(current_url)
                    continue
       
        logger.info(f"🎉 Recursive crawl complete: {len(all_chunks)} chunks from {len(crawled_urls)} pages")
        return all_chunks, crawled_urls
   
    def _process_crawl4ai_result(self, result: Any, url: str) -> WebPageData:
        """Process Crawl4AI result into WebPageData"""
        try:
            # Crawl4AI provides clean markdown and metadata
            content = result.markdown if hasattr(result, 'markdown') else ""
            if not content and hasattr(result, 'fit_markdown'):
                content = result.fit_markdown
           
            # Safely extract metadata
            result_metadata = getattr(result, 'metadata', {}) or {}
           
            # Extract metadata
            metadata = {
                'scraped_at': datetime.now().isoformat(),
                'original_url': url,
                'title': result_metadata.get('title', '') if isinstance(result_metadata, dict) else '',
                'description': result_metadata.get('description', '') if isinstance(result_metadata, dict) else '',
                'keywords': result_metadata.get('keywords', []) if isinstance(result_metadata, dict) else [],
                'language': result_metadata.get('language', 'en') if isinstance(result_metadata, dict) else 'en',
                'word_count': len(content.split()) if content else 0,
                'character_count': len(content) if content else 0,
                'domain': urlparse(url).netloc
            }
           
            # If no title in metadata, try to extract from content
            if not metadata['title'] and content:
                lines = content.split('\n')
                for line in lines:
                    if line.strip().startswith('#'):
                        metadata['title'] = line.strip('#').strip()
                        break
           
            return WebPageData(
                url=url,
                title=metadata['title'] or f"Web Page - {metadata['domain']}",
                content=content,
                metadata=metadata,
                success=True
            )
           
        except Exception as e:
            logger.error(f"Error processing Crawl4AI result: {str(e)}")
            return WebPageData(
                url=url,
                title=f"Error - {urlparse(url).netloc}",
                content="",
                metadata={'error': str(e), 'scraped_at': datetime.now().isoformat()},
                success=False,
                error=str(e)
            )
   
    def _create_chunks_from_web_content(
        self,
        page_data: WebPageData,
        chunk_size: int,
        chunk_overlap: int
    ) -> List[DocumentChunk]:
        """Create chunks from web page content"""
        if not page_data.success or not page_data.content.strip():
            logger.warning(f"No content to process for {page_data.url}")
            return []
       
        chunks = []
        content = page_data.content
        start = 0
        chunk_index = 0
       
        while start < len(content):
            end = min(start + chunk_size, len(content))
           
            # Try to break at natural boundaries
            if end < len(content):
                # Try to break at double newline (paragraph)
                last_double_newline = content.rfind('\n\n', start, end)
                if last_double_newline > start + chunk_size * 0.3:
                    end = last_double_newline + 2
                else:
                    # Try to break at period
                    last_period = content.rfind('.', start, end)
                    if last_period > start + chunk_size * 0.5:
                        end = last_period + 1
           
            chunk_text = content[start:end].strip()
           
            if chunk_text:
                chunk_metadata = page_data.metadata.copy()
                chunk_metadata.update({
                    'chunk_character_start': start,
                    'chunk_character_end': end - 1,
                    'url_fragment': f"{page_data.url}#chunk-{chunk_index}"
                })
               
                chunk = DocumentChunk(
                    content=chunk_text,
                    source_file=page_data.title,
                    source_type='web',
                    page_number=None,
                    chunk_index=chunk_index,
                    start_char=start,
                    end_char=end-1,
                    metadata=chunk_metadata
                )
               
                chunks.append(chunk)
                chunk_index += 1
           
            start = max(start + chunk_size - chunk_overlap, end)
       
        return chunks
   
    async def batch_scrape_urls(
        self,
        urls: List[str],
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
        delay_between_requests: float = 1.0
    ) -> List[List[DocumentChunk]]:
        """Scrape multiple URLs in batch"""
        all_chunks = []
        for i, url in enumerate(urls):
            try:
                chunks = await self.scrape_url(url, chunk_size, chunk_overlap)
                all_chunks.append(chunks)
                logger.info(f"Successfully scraped {url}: {len(chunks)} chunks")
               
                if i < len(urls) - 1:
                    await asyncio.sleep(delay_between_requests)
                   
            except Exception as e:
                logger.error(f"Failed to scrape {url}: {str(e)}")
                all_chunks.append([])
       
        total_chunks = sum(len(chunks) for chunks in all_chunks)
        logger.info(f"Batch scraping complete: {total_chunks} total chunks from {len(urls)} URLs")
       
        return all_chunks
   
    async def get_url_preview(self, url: str) -> Dict[str, Any]:
        """Get a quick preview of a URL without full scraping"""
        try:
            # ✅ Use context manager
            async with AsyncWebCrawler(**self.crawler_config) as crawler:
                result = await crawler.arun(
                    url=url,
                    word_count_threshold=10,
                    bypass_cache=True
                )
 
                content = result.markdown if hasattr(result, 'markdown') else (result.fit_markdown if hasattr(result, 'fit_markdown') else "")
               
                result_metadata = getattr(result, 'metadata', {}) or {}
               
                preview_info = {
                    'url': url,
                    'title': result_metadata.get('title', '') if isinstance(result_metadata, dict) else '',
                    'description': result_metadata.get('description', '') if isinstance(result_metadata, dict) else '',
                    'word_count': len(content.split()) if content else 0,
                    'character_count': len(content) if content else 0,
                    'domain': urlparse(url).netloc,
                    'content_preview': content[:500] + '...' if len(content) > 500 else content,
                    'language': result_metadata.get('language', 'unknown') if isinstance(result_metadata, dict) else 'unknown'
                }
                return preview_info
           
        except Exception as e:
            logger.error(f"Error getting URL preview: {str(e)}")
            return {'error': str(e)}
   
    def _is_valid_url(self, url: str) -> bool:
        """Validate URL format"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
 
 
if __name__ == "__main__":
    # No API key needed for Crawl4AI (it's open-source!)
    scraper = WebScraper()
   
    async def test():
        try:
            # Test scraping single URL
            test_url = "https://blog.dailydoseofds.com/p/5-chunking-strategies-for-rag"
            print(f"\n{'='*60}")
            print(f"TEST 1: Scraping single URL")
            print(f"{'='*60}")
            chunks = await scraper.scrape_url(test_url)
            print(f"✅ Generated {len(chunks)} chunks")
           
            # Test crawling
            print(f"\n{'='*60}")
            print(f"TEST 2: Crawling website")
            print(f"{'='*60}")
            crawl_url = "https://example.com"
            chunks, crawled_urls = await scraper.crawl_recursively(crawl_url, max_pages=5)
            print(f"✅ Crawled {len(crawled_urls)} pages")
            print(f"📄 Pages crawled:")
            for url in crawled_urls:
                print(f"   - {url}")
            print(f"✅ Total chunks: {len(chunks)}")
           
        except Exception as e:
            print(f"❌ Error in test: {e}")
   
    # Run the async test
    asyncio.run(test())
 