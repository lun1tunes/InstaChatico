"""
Unit tests for DocumentProcessingService.
"""

import pytest
from unittest.mock import MagicMock, patch
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

    def test_process_pdf_success(self, service):
        """Test successful PDF processing."""
        with patch("pdfplumber.open") as mock_pdf_open:
            # Arrange
            mock_page1 = MagicMock()
            mock_page1.extract_text.return_value = "Page 1 content"
            mock_page2 = MagicMock()
            mock_page2.extract_text.return_value = "Page 2 content"

            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page1, mock_page2]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__aexit__ = MagicMock()

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

    def test_process_pdf_no_text(self, service):
        """Test PDF processing with no extractable text."""
        with patch("pdfplumber.open") as mock_pdf_open:
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

    def test_process_pdf_exception(self, service):
        """Test PDF processing handles exceptions."""
        with patch("pdfplumber.open") as mock_pdf_open:
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
        """Test text processing when all encoding attempts fail."""
        # Arrange
        # Create a mock bytes object that fails all decode attempts
        file_content = MagicMock(spec=bytes)
        file_content.decode = MagicMock(side_effect=UnicodeDecodeError('utf-8', b'', 0, 1, 'Mock decode error'))

        # Act
        success, markdown, content_hash, error = service._process_txt(file_content, "test_hash")

        # Assert
        assert success is False
        assert markdown is None
        assert "Failed to decode text file" in error

    def test_process_spreadsheet_csv_success(self, service):
        """Test successful CSV processing."""
        with patch("pandas.read_csv") as mock_read_csv:
            # Arrange
            mock_df = MagicMock()
            mock_df.__len__ = MagicMock(return_value=2)
            mock_df.to_markdown = MagicMock(return_value="| Column1 | Column2 |\n|---------|--------|\n| A       | 1      |\n| B       | 2      |")
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
            mock_df.to_markdown.assert_called_once_with(index=False)

    def test_process_spreadsheet_excel_success(self, service):
        """Test successful Excel processing."""
        with patch("pandas.read_excel") as mock_read_excel:
            # Arrange
            mock_df = MagicMock()
            mock_df.__len__ = MagicMock(return_value=2)
            mock_df.to_markdown = MagicMock(return_value="| Name  | Age |\n|-------|-----|\n| Alice | 30  |\n| Bob   | 25  |")
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
            mock_df.to_markdown.assert_called_once_with(index=False)

    def test_process_spreadsheet_exception(self, service):
        """Test spreadsheet processing handles exceptions."""
        with patch("pandas.read_csv") as mock_read_csv:
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

    def test_process_word_success(self, service):
        """Test successful Word document processing."""
        with patch("docx.Document") as mock_document_class:
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

    def test_process_word_with_tables(self, service):
        """Test Word processing with tables."""
        with patch("docx.Document") as mock_document_class:
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

    def test_process_word_no_content(self, service):
        """Test Word processing with no content."""
        with patch("docx.Document") as mock_document_class:
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

    def test_process_word_exception(self, service):
        """Test Word processing handles exceptions."""
        with patch("docx.Document") as mock_document_class:
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

    @patch.object(DocumentProcessingService, "_process_spreadsheet")
    def test_process_document_csv(self, mock_process_spreadsheet, service):
        """Test process_document routes to spreadsheet processor for CSV."""
        # Arrange
        mock_process_spreadsheet.return_value = (True, "markdown", "hash", None)
        file_content = b"csv content"

        # Act
        success, markdown, content_hash, error = service.process_document(
            file_content, "data.csv", "csv"
        )

        # Assert
        assert success is True
        mock_process_spreadsheet.assert_called_once()

    @patch.object(DocumentProcessingService, "_process_spreadsheet")
    def test_process_document_excel(self, mock_process_spreadsheet, service):
        """Test process_document routes to spreadsheet processor for Excel."""
        # Arrange
        mock_process_spreadsheet.return_value = (True, "markdown", "hash", None)
        file_content = b"excel content"

        # Act
        success, markdown, content_hash, error = service.process_document(
            file_content, "data.xlsx", "excel"
        )

        # Assert
        assert success is True
        mock_process_spreadsheet.assert_called_once()

    @patch.object(DocumentProcessingService, "_process_word")
    def test_process_document_word(self, mock_process_word, service):
        """Test process_document routes to Word processor."""
        # Arrange
        mock_process_word.return_value = (True, "markdown", "hash", None)
        file_content = b"word content"

        # Act
        success, markdown, content_hash, error = service.process_document(
            file_content, "doc.docx", "word"
        )

        # Assert
        assert success is True
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

    def test_process_document_general_exception(self, service):
        """Test process_document handles general exceptions."""
        # Arrange
        with patch("hashlib.sha256") as mock_hash:
            mock_hash.side_effect = Exception("Hash calculation failed")

            # Act
            success, markdown, content_hash, error = service.process_document(
                b"content", "doc.pdf", "pdf"
            )

            # Assert
            assert success is False
            assert markdown is None
            assert content_hash is None
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
