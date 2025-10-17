"""
Unit tests for DocumentProcessingService.
"""

import pytest
from unittest.mock import MagicMock, patch, mock_open
from io import BytesIO

from core.services.document_processing_service import DocumentProcessingService


@pytest.mark.unit
@pytest.mark.service
class TestDocumentProcessingService:
    """Test DocumentProcessingService methods."""

    @pytest.fixture
    def service(self):
        """Create DocumentProcessingService instance."""
        return DocumentProcessingService()

    def test_detect_document_type_pdf(self, service):
        """Test detecting PDF document type."""
        assert service.detect_document_type("document.pdf") == "pdf"
        assert service.detect_document_type("Document.PDF") == "pdf"

    def test_detect_document_type_excel(self, service):
        """Test detecting Excel document types."""
        assert service.detect_document_type("spreadsheet.xlsx") == "excel"
        assert service.detect_document_type("old_format.xls") == "excel"

    def test_detect_document_type_csv(self, service):
        """Test detecting CSV document type."""
        assert service.detect_document_type("data.csv") == "csv"

    def test_detect_document_type_word(self, service):
        """Test detecting Word document types."""
        assert service.detect_document_type("document.docx") == "word"
        assert service.detect_document_type("old_doc.doc") == "word"

    def test_detect_document_type_txt(self, service):
        """Test detecting text document type."""
        assert service.detect_document_type("readme.txt") == "txt"

    def test_detect_document_type_unknown(self, service):
        """Test detecting unknown document type."""
        assert service.detect_document_type("file.unknown") == "other"
        assert service.detect_document_type("noextension") == "other"

    @patch("core.services.document_processing_service.pdfplumber.open")
    def test_process_pdf_success(self, mock_pdf_open, service):
        """Test successful PDF processing."""
        # Arrange
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Page 1 content"
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Page 2 content"

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page1, mock_page2]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock()

        mock_pdf_open.return_value = mock_pdf

        file_content = b"fake pdf content"

        # Act
        success, markdown, content_hash, error = service._process_pdf(file_content, "test_hash")

        # Assert
        assert success is True
        assert "## Page 1" in markdown
        assert "Page 1 content" in markdown
        assert "## Page 2" in markdown
        assert "Page 2 content" in markdown
        assert content_hash == "test_hash"
        assert error is None

    @patch("core.services.document_processing_service.pdfplumber.open")
    def test_process_pdf_no_text(self, mock_pdf_open, service):
        """Test PDF processing with no extractable text."""
        # Arrange
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock()

        mock_pdf_open.return_value = mock_pdf

        # Act
        success, markdown, content_hash, error = service._process_pdf(b"content", "hash")

        # Assert
        assert success is False
        assert markdown is None
        assert error == "No text content found in PDF"

    @patch("core.services.document_processing_service.pdfplumber.open")
    def test_process_pdf_exception(self, mock_pdf_open, service):
        """Test PDF processing handles exceptions."""
        # Arrange
        mock_pdf_open.side_effect = Exception("PDF parsing error")

        # Act
        success, markdown, content_hash, error = service._process_pdf(b"content", "hash")

        # Assert
        assert success is False
        assert markdown is None
        assert "Error processing PDF" in error

    def test_process_txt_success(self, service):
        """Test successful text file processing."""
        # Arrange
        file_content = b"Line 1\nLine 2\nLine 3"

        # Act
        success, markdown, content_hash, error = service._process_txt(file_content, "test_hash")

        # Assert
        assert success is True
        assert "```" in markdown
        assert "Line 1" in markdown
        assert "Line 2" in markdown
        assert content_hash == "test_hash"
        assert error is None

    def test_process_txt_utf8_decode_error_fallback(self, service):
        """Test text processing falls back to other encodings."""
        # Arrange
        # Create content that's not valid UTF-8 but valid latin-1
        file_content = b"\xe9\xe0\xe7"  # Valid latin-1, invalid UTF-8

        # Act
        success, markdown, content_hash, error = service._process_txt(file_content, "test_hash")

        # Assert
        assert success is True
        assert markdown is not None
        assert "```" in markdown

    def test_process_txt_all_encodings_fail(self, service):
        """Test text processing when all encodings fail."""
        # Arrange
        # Create truly invalid content
        with patch.object(bytes, "decode", side_effect=UnicodeDecodeError("test", b"", 0, 1, "test")):
            file_content = b"content"

            # Act
            success, markdown, content_hash, error = service._process_txt(file_content, "hash")

            # Assert
            assert success is False
            assert markdown is None
            assert "Failed to decode text file" in error

    @patch("core.services.document_processing_service.pd.read_csv")
    def test_process_spreadsheet_csv_success(self, mock_read_csv, service):
        """Test successful CSV processing."""
        # Arrange
        import pandas as pd
        mock_df = pd.DataFrame({
            "Column1": ["A", "B"],
            "Column2": [1, 2]
        })
        mock_read_csv.return_value = mock_df

        file_content = b"Column1,Column2\nA,1\nB,2"

        # Act
        success, markdown, content_hash, error = service._process_spreadsheet(
            file_content, "csv", "test_hash"
        )

        # Assert
        assert success is True
        assert markdown is not None
        assert "Column1" in markdown
        assert "Column2" in markdown
        assert content_hash == "test_hash"
        assert error is None

    @patch("core.services.document_processing_service.pd.read_excel")
    def test_process_spreadsheet_excel_success(self, mock_read_excel, service):
        """Test successful Excel processing."""
        # Arrange
        import pandas as pd
        mock_df = pd.DataFrame({
            "Name": ["Alice", "Bob"],
            "Age": [30, 25]
        })
        mock_read_excel.return_value = mock_df

        file_content = b"fake excel content"

        # Act
        success, markdown, content_hash, error = service._process_spreadsheet(
            file_content, "excel", "test_hash"
        )

        # Assert
        assert success is True
        assert markdown is not None
        assert "Name" in markdown
        assert content_hash == "test_hash"
        assert error is None

    @patch("core.services.document_processing_service.pd.read_csv")
    def test_process_spreadsheet_exception(self, mock_read_csv, service):
        """Test spreadsheet processing handles exceptions."""
        # Arrange
        mock_read_csv.side_effect = Exception("Invalid CSV format")

        # Act
        success, markdown, content_hash, error = service._process_spreadsheet(
            b"content", "csv", "hash"
        )

        # Assert
        assert success is False
        assert markdown is None
        assert "Error processing spreadsheet" in error

    @patch("core.services.document_processing_service.Document")
    def test_process_word_success(self, mock_document_class, service):
        """Test successful Word document processing."""
        # Arrange
        mock_para1 = MagicMock()
        mock_para1.text = "Paragraph 1"
        mock_para2 = MagicMock()
        mock_para2.text = "Paragraph 2"

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para1, mock_para2]
        mock_doc.tables = []

        mock_document_class.return_value = mock_doc

        file_content = b"fake word content"

        # Act
        success, markdown, content_hash, error = service._process_word(file_content, "test_hash")

        # Assert
        assert success is True
        assert "Paragraph 1" in markdown
        assert "Paragraph 2" in markdown
        assert content_hash == "test_hash"
        assert error is None

    @patch("core.services.document_processing_service.Document")
    def test_process_word_with_tables(self, mock_document_class, service):
        """Test Word processing with tables."""
        # Arrange
        mock_para = MagicMock()
        mock_para.text = "Document header"

        # Mock table
        mock_cell1 = MagicMock()
        mock_cell1.text = "Cell1"
        mock_cell2 = MagicMock()
        mock_cell2.text = "Cell2"
        mock_row = MagicMock()
        mock_row.cells = [mock_cell1, mock_cell2]
        mock_table = MagicMock()
        mock_table.rows = [mock_row]

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para]
        mock_doc.tables = [mock_table]

        mock_document_class.return_value = mock_doc

        # Act
        success, markdown, content_hash, error = service._process_word(b"content", "hash")

        # Assert
        assert success is True
        assert "Document header" in markdown
        assert "Cell1 | Cell2" in markdown

    @patch("core.services.document_processing_service.Document")
    def test_process_word_no_content(self, mock_document_class, service):
        """Test Word processing with no content."""
        # Arrange
        mock_para = MagicMock()
        mock_para.text = "   "  # Only whitespace

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para]
        mock_doc.tables = []

        mock_document_class.return_value = mock_doc

        # Act
        success, markdown, content_hash, error = service._process_word(b"content", "hash")

        # Assert
        assert success is False
        assert markdown is None
        assert "No text content found" in error

    @patch("core.services.document_processing_service.Document")
    def test_process_word_exception(self, mock_document_class, service):
        """Test Word processing handles exceptions."""
        # Arrange
        mock_document_class.side_effect = Exception("Invalid Word document")

        # Act
        success, markdown, content_hash, error = service._process_word(b"content", "hash")

        # Assert
        assert success is False
        assert markdown is None
        assert "Error processing Word document" in error

    @patch.object(DocumentProcessingService, "_process_pdf")
    def test_process_document_pdf(self, mock_process_pdf, service):
        """Test process_document routes to PDF processor."""
        # Arrange
        mock_process_pdf.return_value = (True, "markdown", "hash", None)
        file_content = b"pdf content"

        # Act
        success, markdown, content_hash, error = service.process_document(
            file_content, "doc.pdf", "pdf"
        )

        # Assert
        assert success is True
        mock_process_pdf.assert_called_once()
        # Verify hash was calculated
        call_args = mock_process_pdf.call_args
        assert call_args[0][1] is not None  # Hash should be generated

    @patch.object(DocumentProcessingService, "_process_txt")
    def test_process_document_txt(self, mock_process_txt, service):
        """Test process_document routes to text processor."""
        # Arrange
        mock_process_txt.return_value = (True, "markdown", "hash", None)

        # Act
        service.process_document(b"text content", "doc.txt", "txt")

        # Assert
        mock_process_txt.assert_called_once()

    @patch.object(DocumentProcessingService, "_process_spreadsheet")
    def test_process_document_spreadsheet(self, mock_process_spreadsheet, service):
        """Test process_document routes to spreadsheet processor."""
        # Arrange
        mock_process_spreadsheet.return_value = (True, "markdown", "hash", None)

        # Act
        service.process_document(b"csv content", "data.csv", "csv")

        # Assert
        mock_process_spreadsheet.assert_called_once()

    @patch.object(DocumentProcessingService, "_process_word")
    def test_process_document_word(self, mock_process_word, service):
        """Test process_document routes to Word processor."""
        # Arrange
        mock_process_word.return_value = (True, "markdown", "hash", None)

        # Act
        service.process_document(b"word content", "doc.docx", "word")

        # Assert
        mock_process_word.assert_called_once()

    def test_process_document_unsupported_type(self, service):
        """Test process_document with unsupported document type."""
        # Act
        success, markdown, content_hash, error = service.process_document(
            b"content", "file.unknown", "unsupported"
        )

        # Assert
        assert success is False
        assert markdown is None
        assert content_hash is None
        assert "Unsupported document type" in error

    def test_process_document_exception(self, service):
        """Test process_document handles exceptions during processing."""
        # Arrange
        with patch.object(service, "_process_pdf", side_effect=Exception("Unexpected error")):
            # Act
            success, markdown, content_hash, error = service.process_document(
                b"content", "doc.pdf", "pdf"
            )

            # Assert
            assert success is False
            assert markdown is None
            assert "Error processing document" in error

    def test_process_document_calculates_hash(self, service):
        """Test that process_document calculates content hash."""
        # Arrange
        file_content = b"test content"

        with patch.object(service, "_process_txt") as mock_process_txt:
            mock_process_txt.return_value = (True, "markdown", None, None)

            # Act
            service.process_document(file_content, "test.txt", "txt")

            # Assert
            # Verify that hash was passed to processor
            call_args = mock_process_txt.call_args
            content_hash = call_args[0][1]
            assert content_hash is not None
            assert len(content_hash) == 64  # SHA256 hash length
