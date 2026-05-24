__all__ = [
    "DocxParser",
    "MarkdownParser",
    "PdfTextParser",
    "TextParser",
]


def __getattr__(name: str):
    if name == "DocxParser":
        from app.services.document_parsing.parsers.docx_parser import DocxParser

        return DocxParser
    if name == "MarkdownParser":
        from app.services.document_parsing.parsers.markdown_parser import MarkdownParser

        return MarkdownParser
    if name == "PdfTextParser":
        from app.services.document_parsing.parsers.pdf_text_parser import PdfTextParser

        return PdfTextParser
    if name == "TextParser":
        from app.services.document_parsing.parsers.text_parser import TextParser

        return TextParser
    raise AttributeError(name)
