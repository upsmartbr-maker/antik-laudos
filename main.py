import os
import io
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from gemini_service import gerar_dados_laudo_gemini
from pdf_service import render_html_laudo, convert_html_to_pdf

# Carrega variáveis de ambiente (.env)
load_dotenv()

app = FastAPI(
    title="Casa Antik - Backend de Geração de Laudos em PDF",
    description="API para análise técnica automatizada por Visão Computacional (Gemini API) e exportação em PDF A4.",
    version="1.0.0"
)

# Habilita CORS para integração com aplicações web/frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join("static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Monta o diretório de arquivos estáticos
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


class URLInputPayload(BaseModel):
    url: Optional[str] = None
    image_url: Optional[str] = None


@app.get("/health", tags=["Status"])
async def health_check():
    """Endpoint de verificação de saúde da API."""
    has_api_key = bool(os.getenv("GEMINI_API_KEY"))
    return {
        "status": "online",
        "service": "Casa Antik Laudo PDF API",
        "gemini_api_configured": has_api_key
    }


@app.post("/gerar-laudo-foto", tags=["Laudos"])
async def gerar_laudo_foto(
    file: UploadFile = File(...),
    file_verso: Optional[UploadFile] = File(None)
):
    """
    Endpoint para geração do Laudo Técnico em PDF a partir de fotos enviadas (Frente e Verso opcional).
    Salva os arquivos na pasta static/uploads/ e envia as fotos para a API do Gemini.
    """
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Por favor, selecione ao menos o arquivo de imagem da frente.")

    try:
        filename = file.filename
        file_path = os.path.join(UPLOAD_DIR, filename)

        # Salva a imagem da frente
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        file_verso_path = None
        if file_verso and file_verso.filename:
            verso_filename = f"verso_{file_verso.filename}"
            file_verso_path = os.path.join(UPLOAD_DIR, verso_filename)
            verso_content = await file_verso.read()
            with open(file_verso_path, "wb") as f:
                f.write(verso_content)

        # Processamento das imagens via Gemini API com hash determinístico
        laudo_json = await gerar_dados_laudo_gemini(
            image_path=file_path,
            image_verso_path=file_verso_path
        )

        # Renderização Jinja2 e conversão em PDF A4
        html_rendered = render_html_laudo(laudo_json)
        pdf_bytes = await convert_html_to_pdf(html_rendered)

        ref_clean = laudo_json.get("referencia", "#ANTK-2026").replace("#", "").replace("/", "-")
        out_filename = f"Laudo_{ref_clean}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{out_filename}"'
            }
        )

    except Exception as e:
        import traceback
        print(f"[main] Erro em /gerar-laudo-foto: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao gerar laudo da foto: {str(e)}")


@app.post("/gerar-laudo", tags=["Laudos"])
async def gerar_laudo(
    url: Optional[str] = Form(None),
    image_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    file_verso: Optional[UploadFile] = File(None)
):
    """
    Endpoint principal para geração do Laudo Técnico em PDF.
    """
    image_bytes = None
    target_url = url or image_url
    image_path = None
    image_verso_path = None

    if file and file.filename:
        filename = file.filename
        image_path = os.path.join(UPLOAD_DIR, filename)
        content = await file.read()
        with open(image_path, "wb") as f:
            f.write(content)

    if file_verso and file_verso.filename:
        verso_filename = f"verso_{file_verso.filename}"
        image_verso_path = os.path.join(UPLOAD_DIR, verso_filename)
        verso_content = await file_verso.read()
        with open(image_verso_path, "wb") as f:
            f.write(verso_content)

    if not image_path and not target_url:
        raise HTTPException(
            status_code=400,
            detail="Por favor, forneça o link de um produto (url) ou faça upload de um arquivo de imagem (file)."
        )

    try:
        # 1. Análise via Gemini API
        laudo_json = await gerar_dados_laudo_gemini(
            image_bytes=image_bytes,
            image_url=target_url,
            image_path=image_path,
            image_verso_path=image_verso_path
        )

        # 2. Renderização do Template HTML com Jinja2
        html_rendered = render_html_laudo(laudo_json)

        # 3. Conversão de HTML em PDF A4
        pdf_bytes = await convert_html_to_pdf(html_rendered)

        ref_clean = laudo_json.get("referencia", "#ANTK-2026").replace("#", "").replace("/", "-")
        filename = f"Laudo_{ref_clean}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except Exception as e:
        print(f"[main] Erro no processamento do laudo: {e}")
        raise HTTPException(status_code=500, detail=f"Erro na geração do laudo: {str(e)}")


@app.post("/analisar-json", tags=["Laudos"])
async def analisar_json(
    url: Optional[str] = Form(None),
    image_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    file_verso: Optional[UploadFile] = File(None)
):
    """Retorna os dados brutos da análise da peça em formato JSON estrito gerado pelo Gemini."""
    image_bytes = None
    target_url = url or image_url
    image_path = None
    image_verso_path = None

    if file and file.filename:
        filename = file.filename
        image_path = os.path.join(UPLOAD_DIR, filename)
        content = await file.read()
        with open(image_path, "wb") as f:
            f.write(content)

    if file_verso and file_verso.filename:
        verso_filename = f"verso_{file_verso.filename}"
        image_verso_path = os.path.join(UPLOAD_DIR, verso_filename)
        verso_content = await file_verso.read()
        with open(image_verso_path, "wb") as f:
            f.write(verso_content)

    data = await gerar_dados_laudo_gemini(
        image_bytes=image_bytes,
        image_url=target_url,
        image_path=image_path,
        image_verso_path=image_verso_path
    )
    return data


@app.post("/preview-laudo", response_class=HTMLResponse, tags=["Preview"])
async def preview_laudo(
    url: Optional[str] = Form(None),
    image_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    file_verso: Optional[UploadFile] = File(None)
):
    """Renderiza a visualização em HTML do laudo no navegador sem converter para PDF."""
    image_bytes = None
    target_url = url or image_url
    image_path = None
    image_verso_path = None

    if file and file.filename:
        filename = file.filename
        image_path = os.path.join(UPLOAD_DIR, filename)
        content = await file.read()
        with open(image_path, "wb") as f:
            f.write(content)

    if file_verso and file_verso.filename:
        verso_filename = f"verso_{file_verso.filename}"
        image_verso_path = os.path.join(UPLOAD_DIR, verso_filename)
        verso_content = await file_verso.read()
        with open(image_verso_path, "wb") as f:
            f.write(verso_content)

    data = await gerar_dados_laudo_gemini(
        image_bytes=image_bytes,
        image_url=target_url,
        image_path=image_path,
        image_verso_path=image_verso_path
    )
    html_rendered = render_html_laudo(data)
    return HTMLResponse(content=html_rendered)


@app.get("/", response_class=HTMLResponse, tags=["UI"])
async def home_interface():
    """Interface interativa de teste para geração de laudos por foto."""
    index_path = os.path.join("templates", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Casa Antik - Gerador de Laudos</h1>")
