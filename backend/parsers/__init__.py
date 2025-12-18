"""
File Parsers Module

Provides parsers for various file formats:
- Excel (.xlsx, .xls)
- CSV (.csv) with Strong App, Hevy, FitNotes support
- JSON (.json)
- Text (.txt) with LLM fallback

Also provides URL parsing for video platforms:
- YouTube (youtube.com, youtu.be)
- Instagram (instagram.com/p/, /reel/, /tv/)
- TikTok (tiktok.com, vm.tiktok.com)

Usage:
    from parsers import FileParserFactory, FileInfo

    parser = FileParserFactory.get_parser(file_info)
    result = await parser.parse(content, file_info)

    # For URLs
    from parsers import URLParser, fetch_url_metadata
    metadata = await fetch_url_metadata(url)
"""

import base64
import logging
from typing import Optional, List

from .models import (
    ParseResult,
    ParsedWorkout,
    ParsedExercise,
    DetectedPatterns,
    DetectedPattern,
    ColumnInfo,
    FileInfo,
    ExerciseFlag,
)
from .base import BaseParser
from .excel_parser import ExcelParser
from .csv_parser import CSVParser
from .json_parser import JSONParser
from .text_parser import TextParser
from .url_parser import (
    URLParser,
    URLMetadata,
    identify_platform,
    is_valid_url,
    fetch_url_metadata,
    fetch_url_metadata_batch,
)

logger = logging.getLogger(__name__)


class FileParserFactory:
    """Factory for creating appropriate file parsers"""

    _parsers: List[BaseParser] = [
        ExcelParser(),
        CSVParser(),
        JSONParser(),
        TextParser(),
    ]

    @classmethod
    def get_parser(cls, file_info: FileInfo) -> Optional[BaseParser]:
        """
        Get the appropriate parser for the given file.

        Args:
            file_info: Information about the file to parse

        Returns:
            Parser instance or None if no parser can handle the file
        """
        for parser in cls._parsers:
            if parser.can_parse(file_info):
                return parser
        return None

    @classmethod
    async def parse_file(cls, content: bytes, file_info: FileInfo) -> ParseResult:
        """
        Parse a file using the appropriate parser.

        Args:
            content: Raw file bytes
            file_info: Information about the file

        Returns:
            ParseResult with workouts, patterns, and metadata
        """
        parser = cls.get_parser(file_info)

        if not parser:
            return ParseResult(
                success=False,
                errors=[f"No parser available for file type: {file_info.extension}"],
                confidence=0
            )

        return await parser.parse(content, file_info)

    @classmethod
    async def parse_base64(cls, base64_content: str, filename: str) -> ParseResult:
        """
        Parse a base64-encoded file.

        Args:
            base64_content: Base64-encoded file content
            filename: Original filename (for extension detection)

        Returns:
            ParseResult with workouts, patterns, and metadata
        """
        try:
            # Decode base64
            content = base64.b64decode(base64_content)

            # Create file info
            extension = ''
            if '.' in filename:
                extension = '.' + filename.rsplit('.', 1)[-1].lower()

            file_info = FileInfo(
                filename=filename,
                extension=extension,
                size_bytes=len(content)
            )

            return await cls.parse_file(content, file_info)

        except Exception as e:
            logger.exception(f"Failed to parse base64 content: {e}")
            return ParseResult(
                success=False,
                errors=[f"Failed to decode file: {str(e)}"],
                confidence=0
            )


# Convenience function
async def parse_file(content: bytes, filename: str) -> ParseResult:
    """
    Parse a file and return normalized workout data.

    Args:
        content: Raw file bytes
        filename: Original filename

    Returns:
        ParseResult with workouts, patterns, and metadata
    """
    extension = ''
    if '.' in filename:
        extension = '.' + filename.rsplit('.', 1)[-1].lower()

    file_info = FileInfo(
        filename=filename,
        extension=extension,
        size_bytes=len(content)
    )

    return await FileParserFactory.parse_file(content, file_info)


__all__ = [
    # Models
    'ParseResult',
    'ParsedWorkout',
    'ParsedExercise',
    'DetectedPatterns',
    'DetectedPattern',
    'ColumnInfo',
    'FileInfo',
    'ExerciseFlag',
    # File Parsers
    'BaseParser',
    'ExcelParser',
    'CSVParser',
    'JSONParser',
    'TextParser',
    # URL Parser
    'URLParser',
    'URLMetadata',
    'identify_platform',
    'is_valid_url',
    'fetch_url_metadata',
    'fetch_url_metadata_batch',
    # Factory
    'FileParserFactory',
    # Convenience
    'parse_file',
]
