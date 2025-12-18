"""
URL Parser

Parses URLs from video platforms:
- YouTube (youtube.com, youtu.be)
- Instagram (instagram.com/p/, /reel/, /tv/)
- TikTok (tiktok.com, vm.tiktok.com)

Fetches metadata and routes to workout-ingestor-api for full processing.
"""

import re
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse, parse_qs
import httpx

logger = logging.getLogger(__name__)

# Workout ingestor API URL
INGESTOR_API_URL = "http://workout-ingestor:8004"


@dataclass
class URLMetadata:
    """Metadata extracted from a URL"""
    url: str
    platform: str  # 'youtube', 'instagram', 'tiktok', 'unknown'
    video_id: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    description: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "platform": self.platform,
            "video_id": self.video_id,
            "title": self.title,
            "author": self.author,
            "thumbnail_url": self.thumbnail_url,
            "duration_seconds": self.duration_seconds,
            "description": self.description,
            "error": self.error,
        }


class URLParser:
    """Parser for video URLs from various platforms"""

    # YouTube patterns
    YOUTUBE_PATTERNS = [
        re.compile(r'(?:youtube\.com/watch\?.*v=|youtu\.be/)([A-Za-z0-9_-]{11})'),
        re.compile(r'youtube\.com/embed/([A-Za-z0-9_-]{11})'),
        re.compile(r'youtube\.com/v/([A-Za-z0-9_-]{11})'),
        re.compile(r'youtube\.com/shorts/([A-Za-z0-9_-]{11})'),
    ]

    # Instagram patterns
    INSTAGRAM_PATTERNS = [
        re.compile(r'instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)'),
    ]

    # TikTok patterns
    TIKTOK_PATTERNS = [
        re.compile(r'tiktok\.com/@[\w.]+/video/(\d+)'),
        re.compile(r'tiktok\.com/t/([A-Za-z0-9_-]+)'),
        re.compile(r'vm\.tiktok\.com/([A-Za-z0-9_-]+)'),
    ]

    @classmethod
    def identify_platform(cls, url: str) -> Tuple[str, Optional[str]]:
        """
        Identify the platform and extract video ID from URL.

        Returns:
            Tuple of (platform, video_id)
        """
        url = url.strip()

        # Check YouTube
        for pattern in cls.YOUTUBE_PATTERNS:
            match = pattern.search(url)
            if match:
                return ('youtube', match.group(1))

        # Check Instagram
        for pattern in cls.INSTAGRAM_PATTERNS:
            match = pattern.search(url)
            if match:
                return ('instagram', match.group(1))

        # Check TikTok
        for pattern in cls.TIKTOK_PATTERNS:
            match = pattern.search(url)
            if match:
                return ('tiktok', match.group(1))

        # Also check by domain for shortened URLs
        parsed = urlparse(url)
        hostname = (parsed.hostname or '').lower()

        if 'youtube' in hostname or hostname == 'youtu.be':
            return ('youtube', None)
        if 'instagram' in hostname:
            return ('instagram', None)
        if 'tiktok' in hostname:
            return ('tiktok', None)

        return ('unknown', None)

    @classmethod
    def is_valid_url(cls, url: str) -> bool:
        """Check if URL is from a supported platform"""
        platform, _ = cls.identify_platform(url)
        return platform != 'unknown'

    @classmethod
    async def fetch_metadata(cls, url: str) -> URLMetadata:
        """
        Fetch metadata for a single URL.

        Uses oEmbed APIs when available for quick metadata without downloading.
        """
        platform, video_id = cls.identify_platform(url)

        if platform == 'unknown':
            return URLMetadata(
                url=url,
                platform='unknown',
                error="URL not from a supported platform (YouTube, Instagram, TikTok)"
            )

        try:
            if platform == 'youtube':
                return await cls._fetch_youtube_metadata(url, video_id)
            elif platform == 'instagram':
                return await cls._fetch_instagram_metadata(url, video_id)
            elif platform == 'tiktok':
                return await cls._fetch_tiktok_metadata(url, video_id)
        except Exception as e:
            logger.exception(f"Error fetching metadata for {url}: {e}")
            return URLMetadata(
                url=url,
                platform=platform,
                video_id=video_id,
                error=str(e)
            )

        return URLMetadata(url=url, platform=platform, video_id=video_id)

    @classmethod
    async def _fetch_youtube_metadata(cls, url: str, video_id: Optional[str]) -> URLMetadata:
        """Fetch YouTube video metadata using oEmbed"""
        # Use YouTube oEmbed API (no API key required)
        oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(oembed_url)

                if response.status_code == 200:
                    data = response.json()
                    return URLMetadata(
                        url=url,
                        platform='youtube',
                        video_id=video_id,
                        title=data.get('title'),
                        author=data.get('author_name'),
                        thumbnail_url=data.get('thumbnail_url'),
                    )
                else:
                    return URLMetadata(
                        url=url,
                        platform='youtube',
                        video_id=video_id,
                        error=f"Could not fetch metadata (status {response.status_code})"
                    )
            except httpx.ConnectError:
                return URLMetadata(
                    url=url,
                    platform='youtube',
                    video_id=video_id,
                    error="Could not connect to YouTube"
                )

    @classmethod
    async def _fetch_instagram_metadata(cls, url: str, video_id: Optional[str]) -> URLMetadata:
        """
        Fetch Instagram metadata.

        Instagram doesn't have a public oEmbed API, so we return basic info
        and let the full ingestion handle the details.
        """
        # Instagram oEmbed requires authentication, so we just return what we know
        return URLMetadata(
            url=url,
            platform='instagram',
            video_id=video_id,
            title=f"Instagram Post {video_id}" if video_id else "Instagram Post",
            # Thumbnail would require scraping, done during full ingestion
        )

    @classmethod
    async def _fetch_tiktok_metadata(cls, url: str, video_id: Optional[str]) -> URLMetadata:
        """Fetch TikTok video metadata using oEmbed"""
        # TikTok has a public oEmbed API
        oembed_url = f"https://www.tiktok.com/oembed?url={url}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(oembed_url)

                if response.status_code == 200:
                    data = response.json()
                    return URLMetadata(
                        url=url,
                        platform='tiktok',
                        video_id=video_id,
                        title=data.get('title'),
                        author=data.get('author_name'),
                        thumbnail_url=data.get('thumbnail_url'),
                    )
                else:
                    return URLMetadata(
                        url=url,
                        platform='tiktok',
                        video_id=video_id,
                        error=f"Could not fetch metadata (status {response.status_code})"
                    )
            except httpx.ConnectError:
                return URLMetadata(
                    url=url,
                    platform='tiktok',
                    video_id=video_id,
                    error="Could not connect to TikTok"
                )

    @classmethod
    async def fetch_metadata_batch(
        cls,
        urls: List[str],
        max_concurrent: int = 5
    ) -> List[URLMetadata]:
        """
        Fetch metadata for multiple URLs with concurrency limit.

        Args:
            urls: List of URLs to process
            max_concurrent: Maximum concurrent requests

        Returns:
            List of URLMetadata in same order as input URLs
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_limit(url: str) -> URLMetadata:
            async with semaphore:
                return await cls.fetch_metadata(url)

        tasks = [fetch_with_limit(url) for url in urls]
        return await asyncio.gather(*tasks)

    @classmethod
    async def ingest_url(cls, url: str, platform: str) -> Dict[str, Any]:
        """
        Full URL ingestion via workout-ingestor-api.

        This performs the complete workout extraction process.

        Args:
            url: Video URL
            platform: Platform identifier ('youtube', 'instagram', 'tiktok')

        Returns:
            Workout data from the ingestor API
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                if platform == 'youtube':
                    response = await client.post(
                        f"{INGESTOR_API_URL}/ingest/youtube",
                        json={"url": url}
                    )
                elif platform == 'tiktok':
                    response = await client.post(
                        f"{INGESTOR_API_URL}/ingest/tiktok",
                        json={"url": url, "mode": "auto"}
                    )
                elif platform == 'instagram':
                    response = await client.post(
                        f"{INGESTOR_API_URL}/ingest/instagram_test",
                        json={"url": url}
                    )
                else:
                    # Generic URL ingestion
                    response = await client.post(
                        f"{INGESTOR_API_URL}/ingest/url",
                        json=url
                    )

                if response.status_code == 200:
                    return {
                        "success": True,
                        "workout": response.json()
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Ingestion failed: {response.text}"
                    }

            except httpx.ConnectError:
                return {
                    "success": False,
                    "error": "Could not connect to workout-ingestor service"
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e)
                }


# Convenience functions
def identify_platform(url: str) -> Tuple[str, Optional[str]]:
    """Identify platform and video ID from URL"""
    return URLParser.identify_platform(url)


def is_valid_url(url: str) -> bool:
    """Check if URL is from a supported platform"""
    return URLParser.is_valid_url(url)


async def fetch_url_metadata(url: str) -> URLMetadata:
    """Fetch metadata for a single URL"""
    return await URLParser.fetch_metadata(url)


async def fetch_url_metadata_batch(urls: List[str], max_concurrent: int = 5) -> List[URLMetadata]:
    """Fetch metadata for multiple URLs"""
    return await URLParser.fetch_metadata_batch(urls, max_concurrent)
