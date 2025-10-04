"""
Document Processing Service

Uses Docling to extract and convert documents to markdown format.
Supports PDF, Excel, CSV, Word documents.
"""

import logging
import hashlib
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from io import BytesIO

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    """Service for processing documents with Docling."""

    def __init__(self):
        """Initialize document processing service."""
        # Import docling only when needed
        self.converter = None

    def _get_converter(self):
        """Lazy load docling converter."""
        if self.converter is None:
            try:
                from docling.document_converter import DocumentConverter
                self.converter = DocumentConverter()
                logger.info("Docling DocumentConverter initialized successfully")
            except ImportError as e:
                logger.error(f"Failed to import Docling: {e}")
                raise ImportError("Docling is not installed. Install with: pip install docling")
        return self.converter

    def process_document(
        self,
        file_content: bytes,
        filename: str,
        document_type: str
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Process document and extract markdown content.

        Args:
            file_content: Binary content of the document
            filename: Original filename
            document_type: Type of document (pdf, excel, csv, word, txt)

        Returns:
            Tuple of (
                success: bool,
                markdown_content: str or None,
                content_hash: str or None,
                error_message: str or None
            )
        """
        try:
            # Calculate content hash
            content_hash = hashlib.sha256(file_content).hexdigest()

            # Handle different document types
            if document_type == 'pdf':
                return self._process_pdf(file_content, content_hash)
            elif document_type == 'txt':
                return self._process_txt(file_content, content_hash)
            elif document_type in ['excel', 'csv']:
                return self._process_spreadsheet(file_content, document_type, content_hash)
            elif document_type == 'word':
                return self._process_word(file_content, content_hash)
            else:
                return False, None, None, f"Unsupported document type: {document_type}"

        except Exception as e:
            error_msg = f"Error processing document: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, None, None, error_msg

    def _process_pdf(self, file_content: bytes, content_hash: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """Process PDF document with Docling."""
        try:
            converter = self._get_converter()

            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_file.write(file_content)
                temp_path = temp_file.name

            try:
                # Convert PDF to markdown
                result = converter.convert(temp_path)
                markdown_content = result.document.export_to_markdown()

                logger.info(f"Successfully processed PDF, extracted {len(markdown_content)} characters")
                return True, markdown_content, content_hash, None

            finally:
                # Clean up temp file
                Path(temp_path).unlink(missing_ok=True)

        except Exception as e:
            error_msg = f"Error processing PDF: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, None, None, error_msg

    def _process_txt(self, file_content: bytes, content_hash: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """Process plain text file."""
        try:
            # Decode text
            text_content = file_content.decode('utf-8')

            # Convert to markdown (just wrap in code block or keep as is)
            markdown_content = f"```\n{text_content}\n```"

            logger.info(f"Successfully processed TXT file, {len(text_content)} characters")
            return True, markdown_content, content_hash, None

        except UnicodeDecodeError:
            # Try other encodings
            for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    text_content = file_content.decode(encoding)
                    markdown_content = f"```\n{text_content}\n```"
                    return True, markdown_content, content_hash, None
                except:
                    continue

            return False, None, None, "Failed to decode text file"

    def _process_spreadsheet(self, file_content: bytes, doc_type: str, content_hash: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """Process Excel or CSV file."""
        try:
            import pandas as pd

            # Read file
            if doc_type == 'csv':
                df = pd.read_csv(BytesIO(file_content))
            else:  # excel
                df = pd.read_excel(BytesIO(file_content))

            # Convert to markdown table
            markdown_content = df.to_markdown(index=False)

            logger.info(f"Successfully processed {doc_type.upper()} file, {len(df)} rows")
            return True, markdown_content, content_hash, None

        except Exception as e:
            error_msg = f"Error processing spreadsheet: {str(e)}"
            logger.error(error_msg)
            return False, None, None, error_msg

    def _process_word(self, file_content: bytes, content_hash: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """Process Word document."""
        try:
            converter = self._get_converter()

            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as temp_file:
                temp_file.write(file_content)
                temp_path = temp_file.name

            try:
                # Convert Word to markdown
                result = converter.convert(temp_path)
                markdown_content = result.document.export_to_markdown()

                logger.info(f"Successfully processed Word document")
                return True, markdown_content, content_hash, None

            finally:
                Path(temp_path).unlink(missing_ok=True)

        except Exception as e:
            error_msg = f"Error processing Word document: {str(e)}"
            logger.error(error_msg)
            return False, None, None, error_msg

    @staticmethod
    def detect_document_type(filename: str) -> str:
        """
        Detect document type from filename.

        Args:
            filename: Original filename

        Returns:
            Document type: pdf, excel, csv, word, txt, or other
        """
        extension = Path(filename).suffix.lower()

        type_mapping = {
            '.pdf': 'pdf',
            '.xlsx': 'excel',
            '.xls': 'excel',
            '.csv': 'csv',
            '.docx': 'word',
            '.doc': 'word',
            '.txt': 'txt',
        }

        return type_mapping.get(extension, 'other')


# Singleton instance
document_processing_service = DocumentProcessingService()
