import logging
import uuid
from pathlib import Path

import requests

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import inngest
import inngest.fast_api

from data_loader import load_and_chunk_pdf, embed_texts
from vector_db import QdrantStorage

from custom_types import (
    RAGSearchResult,
    RAGUpsertResult,
    RAGChunkAndSrc,
)


# ============================================================
# INNGEST CLIENT
# ============================================================

inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logging.getLogger("uvicorn"),
    is_production=False,
    serializer=inngest.PydanticSerializer(),
)


# ============================================================
# RAG: INGEST PDF
# ============================================================

@inngest_client.create_function(
    fn_id="RAG: Ingest PDF",
    trigger=inngest.TriggerEvent(
        event="rag/ingest_pdf"
    ),
)
async def rag_ingest_pdf(ctx: inngest.Context):

    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:

        pdf_path = ctx.event.data["pdf_path"]

        source_id = ctx.event.data.get(
            "source_id",
            pdf_path
        )

        chunks = load_and_chunk_pdf(
            pdf_path
        )

        return RAGChunkAndSrc(
            chunks=chunks,
            source_id=source_id
        )

    def _upsert(
        chunks_and_src: RAGChunkAndSrc
    ) -> RAGUpsertResult:

        chunks = chunks_and_src.chunks
        source_id = chunks_and_src.source_id

        vecs = embed_texts(chunks)

        ids = [
            str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{source_id}:{i}"
                )
            )
            for i in range(len(chunks))
        ]

        payloads = [
            {
                "source": source_id,
                "text": chunks[i]
            }
            for i in range(len(chunks))
        ]

        QdrantStorage().upsert(
            ids,
            vecs,
            payloads
        )

        return RAGUpsertResult(
            ingested=len(chunks)
        )

    chunks_and_src = await ctx.step.run(
        "load-and-chunk",
        lambda: _load(ctx),
        output_type=RAGChunkAndSrc
    )

    ingested = await ctx.step.run(
        "embed-and-upsert",
        lambda: _upsert(chunks_and_src),
        output_type=RAGUpsertResult
    )

    return ingested.model_dump()


# ============================================================
# RAG: QUERY PDF
# ============================================================

@inngest_client.create_function(
    fn_id="RAG: Query PDF",
    trigger=inngest.TriggerEvent(
        event="rag/query_pdf_ai"
    ),
)
async def rag_query_pdf_ai(
    ctx: inngest.Context
):

    def _search(
        question: str,
        top_k: int = 5
    ) -> RAGSearchResult:

        query_vec = embed_texts(
            [question]
        )[0]

        store = QdrantStorage()

        found = store.search(
            query_vec,
            top_k
        )

        return RAGSearchResult(
            contexts=found["contexts"],
            sources=found["sources"]
        )

    question = ctx.event.data["question"]

    top_k = int(
        ctx.event.data.get(
            "top_k",
            5
        )
    )

    found = await ctx.step.run(
        "embed-and-search",
        lambda: _search(
            question,
            top_k
        ),
        output_type=RAGSearchResult
    )

    context_block = "\n\n".join(
        f"- {c}"
        for c in found.contexts
    )

    user_content = (
        "Use the following context to answer the question.\n\n"
        f"Context:\n{context_block}\n\n"
        f"Question: {question}\n"
        "Answer concisely using the context above."
    )

    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": "llama3.2:3b",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You answer questions using only "
                        "the provided context."
                    )
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            "stream": False
        },
        timeout=120
    )

    response.raise_for_status()

    result = response.json()

    answer = result["message"]["content"].strip()

    return {
        "answer": answer,
        "sources": found.sources,
        "num_contexts": len(found.contexts)
    }


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI()


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# UPLOAD DIRECTORY
# ============================================================

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "message": "RAG backend is running"
    }


# ============================================================
# FRONTEND: UPLOAD PDF
# ============================================================

@app.post("/api/upload")
async def upload_pdf(
    file: UploadFile = File(...)
):

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file selected"
        )

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )

    file_path = UPLOAD_DIR / file.filename

    try:

        with open(file_path, "wb") as buffer:
            while True:

                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                buffer.write(chunk)

        # Load PDF
        chunks = load_and_chunk_pdf(
            str(file_path)
        )

        # Generate local embeddings
        vectors = embed_texts(chunks)

        # Generate IDs
        ids = [
            str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{file.filename}:{i}"
                )
            )
            for i in range(len(chunks))
        ]

        # Payloads
        payloads = [
            {
                "source": file.filename,
                "text": chunks[i]
            }
            for i in range(len(chunks))
        ]

        # Store in Qdrant
        QdrantStorage().upsert(
            ids,
            vectors,
            payloads
        )

        return {
            "success": True,
            "filename": file.filename,
            "chunks": len(chunks),
            "message": "PDF uploaded and indexed successfully"
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ============================================================
# FRONTEND: ASK QUESTION
# ============================================================

@app.post("/api/query")
async def query_pdf(data: dict):

    question = data.get("question")

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question is required"
        )

    top_k = int(
        data.get(
            "top_k",
            5
        )
    )

    try:

        # ----------------------------------------------------
        # Generate question embedding
        # ----------------------------------------------------

        query_vector = embed_texts(
            [question]
        )[0]

        # ----------------------------------------------------
        # Search Qdrant
        # ----------------------------------------------------

        store = QdrantStorage()

        found = store.search(
            query_vector,
            top_k
        )

        contexts = found["contexts"]
        sources = found["sources"]

        # ----------------------------------------------------
        # Create context
        # ----------------------------------------------------

        context_block = "\n\n".join(
            f"- {context}"
            for context in contexts
        )

        user_content = (
            "Use the following context to answer the question.\n\n"
            f"Context:\n{context_block}\n\n"
            f"Question: {question}\n"
            "Answer concisely using the context above."
        )

        # ----------------------------------------------------
        # Ollama
        # ----------------------------------------------------

        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "llama3.2:3b",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You answer questions using only "
                            "the provided context."
                        )
                    },
                    {
                        "role": "user",
                        "content": user_content
                    }
                ],
                "stream": False
            },
            timeout=120
        )

        response.raise_for_status()

        result = response.json()

        answer = result["message"]["content"].strip()

        return {
            "answer": answer,
            "sources": sources,
            "num_contexts": len(contexts)
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ============================================================
# INNGEST SERVER
# ============================================================

inngest.fast_api.serve(
    app,
    inngest_client,
    functions=[
        rag_ingest_pdf,
        rag_query_pdf_ai
    ],
)