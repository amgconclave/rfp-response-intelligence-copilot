import re
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile

from app.core.config import Settings
from app.models.domain import Chunk, Document
from app.repositories.memory import InMemoryRepository
from app.vectorstores.base import BaseVectorStore


class DocumentIngestionService:
    def __init__(
        self,
        repo: InMemoryRepository,
        vector_store: BaseVectorStore,
        settings: Settings,
    ) -> None:
        self.repo = repo
        self.vector_store = vector_store
        self.settings = settings

    async def ingest_path(
        self,
        path: str | Path,
        document_type: str = "unknown",
        source: str = "local",
        tags: list[str] | None = None,
    ) -> tuple[Document, list[Chunk]]:
        resolved = self._resolve_path(path)
        text = self._parse_document(resolved)
        document = Document(
            filename=resolved.name,
            document_type=document_type,
            source=source,
            tags=tags or [],
            metadata={"path": str(resolved)},
        )
        chunks = self._chunk_text(document.id, text, resolved.name)
        self.repo.documents[document.id] = document
        for chunk in chunks:
            self.repo.chunks[chunk.id] = chunk
        await self.vector_store.upsert(chunks)
        return document, chunks

    async def ingest_upload(
        self,
        upload: UploadFile,
        document_type: str = "unknown",
        source: str = "upload",
        tags: list[str] | None = None,
    ) -> tuple[Document, list[Chunk]]:
        content = await upload.read()
        text = self._parse_bytes(content, upload.filename or "uploaded_document.txt")
        document = Document(
            filename=upload.filename or "uploaded_document.txt",
            document_type=document_type,
            source=source,
            tags=tags or [],
            metadata={"content_type": upload.content_type},
        )
        chunks = self._chunk_text(document.id, text, document.filename)
        self.repo.documents[document.id] = document
        for chunk in chunks:
            self.repo.chunks[chunk.id] = chunk
        await self.vector_store.upsert(chunks)
        return document, chunks

    def list_documents(self) -> list[Document]:
        return sorted(self.repo.documents.values(), key=lambda doc: doc.created_at, reverse=True)

    def get_text(self, document_id: str) -> str:
        chunks = [chunk for chunk in self.repo.chunks.values() if chunk.document_id == document_id]
        return "\n\n".join(chunk.text for chunk in chunks)

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if not candidate.exists():
            sample_candidate = self.settings.sample_data_dir / str(path)
            if sample_candidate.exists():
                candidate = sample_candidate
        if not candidate.exists():
            raise FileNotFoundError(f"Document not found: {path}")
        return candidate

    def _parse_document(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        return path.read_text(encoding="utf-8")

    def _parse_bytes(self, content: bytes, filename: str) -> str:
        if Path(filename).suffix.lower() == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        return content.decode("utf-8", errors="ignore")

    def _chunk_text(self, document_id: str, text: str, filename: str) -> list[Chunk]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        chunks: list[Chunk] = []
        buffer: list[str] = []
        token_count = 0
        page = 1
        for paragraph in paragraphs:
            words = paragraph.split()
            if token_count + len(words) > 180 and buffer:
                chunk_text = "\n\n".join(buffer)
                chunks.append(
                    Chunk(
                        document_id=document_id,
                        text=chunk_text,
                        metadata={"filename": filename, "page": page},
                        token_count=len(chunk_text.split()),
                    )
                )
                buffer = []
                token_count = 0
                page += 1
            buffer.append(paragraph)
            token_count += len(words)
        if buffer:
            chunk_text = "\n\n".join(buffer)
            chunks.append(
                Chunk(
                    document_id=document_id,
                    text=chunk_text,
                    metadata={"filename": filename, "page": page},
                    token_count=len(chunk_text.split()),
                )
            )
        return chunks
