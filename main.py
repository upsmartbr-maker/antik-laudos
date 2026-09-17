import os
import io
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Query, Response, Request
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from gemini_service import gerar_dados_laudo_gemini, otimizar_imagem_base64, get_logo_base64
from pdf_service import render_html_laudo, convert_html_to_pdf
import auth_service
import supabase_service

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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Configura templates Jinja2
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Monta o diretório de arquivos estáticos de forma segura
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class URLInputPayload(BaseModel):
    url: Optional[str] = None
    image_url: Optional[str] = None


class UsuarioCreatePayload(BaseModel):
    nome: str
    email: str
    tipo_validade: str = "Meses"
    periodo: Optional[int] = None
    quantidade_validade: Optional[int] = None

    def get_quantidade(self) -> int:
        if self.quantidade_validade is not None and self.quantidade_validade > 0:
            return self.quantidade_validade
        if self.periodo is not None and self.periodo > 0:
            return self.periodo
        return 6


class UsuarioEditPayload(BaseModel):
    nome: Optional[str] = None
    tipo_validade: Optional[str] = "Meses"
    quantidade_validade: Optional[int] = 6
    gerar_nova_senha: Optional[bool] = False


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
    Processamento 100% em memória (buffer/io.BytesIO), compatível com ambientes Serverless (Vercel).
    """
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Por favor, selecione ao menos o arquivo de imagem da frente.")

    try:
        # Lê os bytes das fotos diretamente na memória
        content = await file.read()
        verso_content = None
        verso_mime = None
        if file_verso and file_verso.filename:
            verso_content = await file_verso.read()
            verso_mime = file_verso.content_type

        # Processamento das imagens via Gemini API com hash determinístico diretamente em memória
        laudo_json = await gerar_dados_laudo_gemini(
            image_bytes=content,
            image_mime=file.content_type,
            image_verso_bytes=verso_content,
            image_verso_mime=verso_mime
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
    Endpoint principal para geração do Laudo Técnico em PDF (100% em memória).
    """
    image_bytes = None
    image_mime = None
    image_verso_bytes = None
    image_verso_mime = None
    target_url = url or image_url

    if file and file.filename:
        image_bytes = await file.read()
        image_mime = file.content_type

    if file_verso and file_verso.filename:
        image_verso_bytes = await file_verso.read()
        image_verso_mime = file_verso.content_type

    if not image_bytes and not target_url:
        raise HTTPException(
            status_code=400,
            detail="Por favor, forneça o link de um produto (url) ou faça upload de um arquivo de imagem (file)."
        )

    try:
        # 1. Análise via Gemini API 100% em memória
        laudo_json = await gerar_dados_laudo_gemini(
            image_bytes=image_bytes,
            image_mime=image_mime,
            image_verso_bytes=image_verso_bytes,
            image_verso_mime=image_verso_mime,
            image_url=target_url
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
    """Retorna os dados brutos da análise da peça em formato JSON estrito gerado pelo Gemini (100% em memória)."""
    image_bytes = None
    image_mime = None
    image_verso_bytes = None
    image_verso_mime = None
    target_url = url or image_url

    if file and file.filename:
        image_bytes = await file.read()
        image_mime = file.content_type

    if file_verso and file_verso.filename:
        image_verso_bytes = await file_verso.read()
        image_verso_mime = file_verso.content_type

    data = await gerar_dados_laudo_gemini(
        image_bytes=image_bytes,
        image_mime=image_mime,
        image_verso_bytes=image_verso_bytes,
        image_verso_mime=image_verso_mime,
        image_url=target_url
    )
    return data


@app.post("/preview-laudo", response_class=HTMLResponse, tags=["Preview"])
async def preview_laudo(
    url: Optional[str] = Form(None),
    image_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    file_verso: Optional[UploadFile] = File(None)
):
    """Renderiza a visualização em HTML do laudo no navegador sem converter para PDF (100% em memória)."""
    image_bytes = None
    image_mime = None
    image_verso_bytes = None
    image_verso_mime = None
    target_url = url or image_url

    if file and file.filename:
        image_bytes = await file.read()
        image_mime = file.content_type

    if file_verso and file_verso.filename:
        image_verso_bytes = await file_verso.read()
        image_verso_mime = file_verso.content_type

    data = await gerar_dados_laudo_gemini(
        image_bytes=image_bytes,
        image_mime=image_mime,
        image_verso_bytes=image_verso_bytes,
        image_verso_mime=image_verso_mime,
        image_url=target_url
    )
    html_rendered = render_html_laudo(data)
    return HTMLResponse(content=html_rendered)


@app.get("/", response_class=HTMLResponse, tags=["UI"])
async def home_interface(request: Request):
    """
    Interface principal privada para geração de laudos técnicos Casa Antik.
    Exige autenticação ativa: Administrador ou Usuário com assinatura não expirada.
    """
    user = auth_service.get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # 1. Se for administrador autenticado
    if user.get("role") == "admin":
        user_info = {
            "email": user.get("sub", auth_service.ADMIN_EMAIL_DEFAULT),
            "nome": "Administrador",
            "is_admin": True
        }
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"user": user_info}
        )

    # 2. Se for usuário comum cadastrado, valida assinatura no Supabase / local
    email_user = user.get("sub", "").strip().lower()
    ativo, motivo, user_data = await supabase_service.verificar_usuario_ativo(email_user)
    if not ativo:
        # Sessão expirada ou inválida: remove cookie e redireciona para login com status 303
        response = RedirectResponse(url="/login?erro=expirado", status_code=303)
        response.delete_cookie(key=auth_service.USER_COOKIE_NAME)
        return response

    nome_exibicao = (user_data.get("nome") if user_data else None) or user.get("nome") or email_user
    user_info = {
        "email": email_user,
        "nome": nome_exibicao,
        "is_admin": False
    }

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"user": user_info}
    )


# ==============================================================================
# AUTENTICAÇÃO DE USUÁRIOS (GERADOR DE LAUDOS)
# ==============================================================================

@app.get("/login", response_class=HTMLResponse, tags=["Autenticação"])
@app.get("/login/", response_class=HTMLResponse, tags=["Autenticação"])
async def user_login_page(request: Request, erro: Optional[str] = None):
    """Exibe a tela de login para usuários clientes e antiquários."""
    user = auth_service.get_current_user(request)
    if user and not erro:
        return RedirectResponse(url="/", status_code=303)

    msg_erro = None
    if erro == "expirado":
        msg_erro = "Sua assinatura ou período de acesso expirou. Entre em contato com a administração."

    return templates.TemplateResponse(request=request, name="login.html", context={"erro": msg_erro})


@app.post("/login", tags=["Autenticação"])
@app.post("/login/", tags=["Autenticação"])
async def user_login_action(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    """Autentica o usuário consultando a tabela usuarios_antik do Supabase."""
    email_limpo = (email or "").strip().lower()
    senha_limpa = (password or "").strip()

    # Caso seja o administrador efetuando login pela rota comum
    if auth_service.verify_admin_credentials(email_limpo, senha_limpa):
        token = auth_service.create_admin_token(email_limpo)
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key=auth_service.COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=auth_service.SESSION_DURATION_SECONDS,
            samesite="lax",
            secure=False
        )
        return response

    # Consulta e autentica contra a tabela usuarios_antik do Supabase
    sucesso, msg, user_data = await supabase_service.autenticar_usuario_supabase(email_limpo, senha_limpa)
    if not sucesso:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"erro": msg},
            status_code=401
        )

    # Emite cookie de sessão para o usuário
    user_token = auth_service.create_user_token(
        email=email_limpo,
        nome=user_data.get("nome", "") if user_data else "",
        data_expiracao=user_data.get("data_expiracao", "") if user_data else ""
    )
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=auth_service.USER_COOKIE_NAME,
        value=user_token,
        httponly=True,
        max_age=auth_service.SESSION_DURATION_SECONDS,
        samesite="lax",
        secure=False
    )
    return response


@app.get("/logout", tags=["Autenticação"])
@app.post("/logout", tags=["Autenticação"])
async def user_logout():
    """Encerra a sessão do usuário ou administrador e redireciona para a tela de login."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key=auth_service.USER_COOKIE_NAME)
    response.delete_cookie(key=auth_service.COOKIE_NAME)
    return response


# ==============================================================================
# ÁREA ADMINISTRATIVA & GESTÃO DE USUÁRIOS (SUPABASE)
# ==============================================================================

@app.get("/admin", tags=["Admin"])
@app.get("/admin/", tags=["Admin"])
async def admin_redirect():
    """Redireciona o acesso de /admin para /admin/login."""
    return RedirectResponse(url="/admin/login", status_code=303)


@app.get("/admin/login", response_class=HTMLResponse, tags=["Admin"])
@app.get("/admin/login/", response_class=HTMLResponse, tags=["Admin"])
async def admin_login_page(request: Request):
    """Exibe a tela de login administrativo com estética clássica Casa Antik."""
    admin = auth_service.get_current_admin(request)
    if admin:
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return templates.TemplateResponse(request=request, name="admin_login.html", context={"erro": None})


@app.post("/admin/login", tags=["Admin"])
@app.post("/admin/login/", tags=["Admin"])
async def admin_login_action(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    """
    Autentica o administrador (redirecionando para o painel /admin/dashboard)
    ou usuário cadastrado (redirecionando para o gerador de laudos /).
    """
    email_limpo = (email or "").strip().lower()
    senha_limpa = (password or "").strip()

    # 1. Se for o administrador principal
    if auth_service.verify_admin_credentials(email_limpo, senha_limpa):
        token = auth_service.create_admin_token(email_limpo)
        response = RedirectResponse(url="/admin/dashboard", status_code=303)
        response.set_cookie(
            key=auth_service.COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=auth_service.SESSION_DURATION_SECONDS,
            samesite="lax",
            secure=False  # Permite funcionamento tanto em desenvolvimento (HTTP) quanto em produção (HTTPS)
        )
        return response

    # 2. Se for um usuário comum cadastrado acessando pela tela de login
    sucesso, msg, user_data = await supabase_service.autenticar_usuario_supabase(email_limpo, senha_limpa)
    if sucesso:
        user_token = auth_service.create_user_token(
            email=email_limpo,
            nome=user_data.get("nome", "") if user_data else "",
            data_expiracao=user_data.get("data_expiracao", "") if user_data else ""
        )
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key=auth_service.USER_COOKIE_NAME,
            value=user_token,
            httponly=True,
            max_age=auth_service.SESSION_DURATION_SECONDS,
            samesite="lax",
            secure=False
        )
        return response

    # 3. Caso não seja admin nem usuário válido (ou expirado)
    erro_msg = msg if (msg and "expirado" in msg.lower()) else "E-mail ou senha incorretos."
    return templates.TemplateResponse(
        request=request,
        name="admin_login.html",
        context={"erro": erro_msg},
        status_code=401
    )


@app.get("/admin/logout", tags=["Admin"])
async def admin_logout():
    """Encerra a sessão do administrador e remove o cookie de autenticação."""
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(key=auth_service.COOKIE_NAME)
    return response


@app.get("/admin/dashboard", response_class=HTMLResponse, tags=["Admin"])
async def admin_dashboard(request: Request):
    """
    Painel administrativo protegido.
    Redireciona para /admin/login caso a sessão não seja válida.
    """
    admin = auth_service.get_current_admin(request)
    if not admin:
        return RedirectResponse(url="/admin/login", status_code=303)

    usuarios = await supabase_service.listar_usuarios_supabase()
    supabase_configured = supabase_service.is_supabase_configured()

    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={
            "admin_email": admin.get("sub", auth_service.ADMIN_EMAIL_DEFAULT),
            "usuarios": usuarios,
            "supabase_configured": supabase_configured
        }
    )


@app.post("/admin/usuarios", tags=["Admin"])
async def criar_usuario_admin(
    request: Request,
    payload: UsuarioCreatePayload
):
    """
    Endpoint administrativo para cadastrar novo usuário:
    - Gera senha aleatória e segura de 10 dígitos (maiúsculas, minúsculas, números).
    - Calcula data de expiração somando dias ou meses.
    - Persiste na tabela usuarios_antik do Supabase.
    """
    admin = auth_service.get_current_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="Sessão não autorizada ou expirada.")

    try:
        quantidade = payload.get_quantidade()
        resultado = await supabase_service.cadastrar_usuario_supabase(
            nome=payload.nome,
            email=payload.email,
            tipo_validade=payload.tipo_validade,
            periodo=quantidade,
            quantidade_validade=quantidade
        )
        return resultado
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao cadastrar usuário: {str(e)}")


@app.get("/admin/api/usuarios", tags=["Admin"])
async def api_listar_usuarios(request: Request):
    """Retorna os usuários cadastrados em formato JSON."""
    admin = auth_service.get_current_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="Sessão não autorizada.")

    usuarios = await supabase_service.listar_usuarios_supabase()
    return usuarios


@app.post("/admin/usuarios/{id}/editar", tags=["Admin"])
async def editar_usuario_admin(
    id: str,
    payload: UsuarioEditPayload,
    request: Request
):
    """Atualiza dados do usuário no Supabase e opcionalmente gera nova senha."""
    admin = auth_service.get_current_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="Sessão não autorizada.")

    try:
        resultado = await supabase_service.editar_usuario_supabase(
            identificador=id,
            nome=payload.nome,
            tipo_validade=payload.tipo_validade,
            quantidade_validade=payload.quantidade_validade,
            gerar_nova_senha=bool(payload.gerar_nova_senha)
        )
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar usuário: {str(e)}")


@app.delete("/admin/usuarios/{id}", tags=["Admin"])
@app.post("/admin/usuarios/{id}/excluir", tags=["Admin"])
async def excluir_usuario_admin(
    id: str,
    request: Request
):
    """Remove um usuário cadastrado no Supabase."""
    admin = auth_service.get_current_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="Sessão não autorizada.")

    try:
        sucesso = await supabase_service.excluir_usuario_supabase(identificador=id)
        return {"sucesso": sucesso, "mensagem": "Usuário removido com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover usuário: {str(e)}")
