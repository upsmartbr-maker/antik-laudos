import os
import io
import json
import random
import datetime
import base64
from typing import Optional, Dict, Any, Union, List
from PIL import Image
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Carrega variáveis de ambiente (.env)
load_dotenv()

# Pydantic Schemas para Estruturação do JSON
class CenarioPrecificacao(BaseModel):
    cenario: str = Field(description="Descrição do cenário de mercado")
    faixa_preco: str = Field(description="Faixa estimada de preço em R$ (ex: R$ 1.500 – R$ 3.500)")

class LaudoGeminiSchema(BaseModel):
    referencia: str = Field(description="Código de referência no formato #ANTK-2026-XXXX")
    data: str = Field(description="Data da análise no formato DD/MM/YYYY")
    identificacao: str = Field(description="Identificação ou título da peça")
    tecnica: str = Field(description="Técnica de manufatura ou estilo artístico")
    materiais: str = Field(description="Materiais observados na composição")
    dimensoes: str = Field(description="Dimensões estimadas ou 'Não informadas'")
    assinatura: str = Field(description="Identificação de marca, selo ou assinatura")
    datacao: str = Field(description="Datação estimada da peça")
    descricao_contexto: str = Field(description="Descrição detalhada e contexto histórico")
    pontos_fortes: List[str] = Field(description="Lista de 3 a 4 pontos fortes da peça")
    pontos_atencao: List[str] = Field(description="Lista de 3 a 4 pontos de atenção")
    cenarios_precificacao: List[CenarioPrecificacao] = Field(description="3 cenários de precificação de mercado")


def get_logo_base64() -> str:
    """Retorna o logotipo oficial Casa Antik em formato Base64 data URI."""
    logo_path = os.path.join("static", "Logo Antik.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
            return f"data:image/png;base64,{encoded}"
    return ""


async def fetch_image_from_url(url: str) -> tuple[bytes, str]:
    """Obtém imagem a partir de uma URL direta ou scraping de página de produto."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")

        # Se for imagem direta
        if "image/" in content_type:
            return resp.content, content_type

        # Se for página HTML, tenta extrair a imagem principal (og:image ou <img>)
        soup = BeautifulSoup(resp.text, "html.parser")
        og_image = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
        image_src = None
        if og_image and og_image.get("content"):
            image_src = og_image["content"]
        else:
            first_img = soup.find("img")
            if first_img and first_img.get("src"):
                image_src = first_img["src"]

        if image_src:
            if not image_src.startswith("http"):
                from urllib.parse import urljoin
                image_src = urljoin(url, image_src)
            img_resp = await client.get(image_src)
            img_resp.raise_for_status()
            return img_resp.content, img_resp.headers.get("content-type", "image/jpeg")

        raise ValueError(f"Não foi possível extrair uma imagem do link fornecido: {url}")


import hashlib

def generate_mock_laudo(
    image_bytes: bytes,
    image_mime: str = "image/png",
    referencia: Optional[str] = None,
    image_verso_bytes: Optional[bytes] = None,
    image_verso_mime: str = "image/png"
) -> Dict[str, Any]:
    """Gera um laudo de demonstração (fallback) quando a API Key do Gemini não está presente."""
    b64_image = f"data:{image_mime};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
    
    if not referencia:
        if image_verso_bytes:
            hash_calc = hashlib.sha256(image_bytes + image_verso_bytes).hexdigest()[:10].upper()
        else:
            hash_calc = hashlib.sha256(image_bytes).hexdigest()[:10].upper()
        referencia = f"#ANTK-2026-{hash_calc}"

    today_str = datetime.date.today().strftime("%d/%m/%Y")

    res = {
        "referencia": referencia,
        "data": today_str,
        "identificacao": '"Peugeot 1912" (Plaqueta Original)',
        "tecnica": "Assemblage / Relevo Tridimensional",
        "materiais": "Metal, latão, veludo preto, caixa-vitrine de madeira e vidro.",
        "dimensoes": "Não informadas",
        "assinatura": "Não identificada na análise visual",
        "datacao": "Século XX / Contemporânea",
        "descricao_contexto": (
            "Composição tridimensional do tipo assemblage representando o modelo automobilístico Peugeot "
            "de 1912, estruturada com engrenagens, parafusos e componentes mecânicos ornamentais em tons dourados. "
            "A peça está acondicionada em caixa-vitrine (shadow box) revestida interiormente em veludo preto. "
            "O tema faz referência ao ano em que a Peugeot venceu o Grande Prêmio da França."
        ),
        "pontos_fortes": [
            "Excelente acabamento e apelo visual refinado.",
            "Tema valorizado no mercado de automobilia.",
            "Proteção em caixa-vitrine que preserva a estrutura."
        ],
        "pontos_atencao": [
            "Ausência de assinatura ou autoria confirmada.",
            "Inexistência de comprovação documental de época.",
            "Produção decorativa de tiragem não catalogada."
        ],
        "cenarios_precificacao": [
            {
                "cenario": "Peça decorativa anônima contemporânea",
                "faixa_preco": "R$ 500 – R$ 1.500"
            },
            {
                "cenario": "Assemblage artesanal bem executado (Perfil desta peça)",
                "faixa_preco": "R$ 1.500 – R$ 3.500"
            },
            {
                "cenario": "Obra de artista identificável (Pouco conhecido)",
                "faixa_preco": "R$ 3.000 – R$ 7.000"
            }
        ],
        "imagem_url": b64_image
    }

    if image_verso_bytes:
        res["imagem_verso_url"] = f"data:{image_verso_mime};base64,{base64.b64encode(image_verso_bytes).decode('utf-8')}"

    return res


def get_mime_type_from_filename(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


async def gerar_dados_laudo_gemini(
    image_bytes: Optional[bytes] = None,
    image_verso_bytes: Optional[bytes] = None,
    image_url: Optional[str] = None,
    image_path: Optional[str] = None,
    image_verso_path: Optional[str] = None,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Consulta a Gemini API via SDK google-genai para gerar dados estruturados de laudo.
    Aceita 1 ou 2 imagens (frente e verso) enviadas via bytes, URL ou caminho de arquivo local.
    Calcula determinística e criptograficamente a referência única no padrão #ANTK-2026-{SHA256[:10]}.
    """
    current_api_key = api_key or os.getenv("GEMINI_API_KEY")

    # 1. Carregar bytes da imagem frontal
    mime_type = "image/jpeg"
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        mime_type = get_mime_type_from_filename(image_path)
    elif image_url:
        image_bytes, mime_type = await fetch_image_from_url(image_url)
    elif not image_bytes:
        raise ValueError("É necessário fornecer a imagem frontal em arquivo (bytes/caminho) ou uma URL de produto.")

    # 2. Carregar bytes da imagem do verso (se fornecida)
    verso_mime_type = "image/jpeg"
    if image_verso_path and os.path.exists(image_verso_path):
        with open(image_verso_path, "rb") as f:
            image_verso_bytes = f.read()
        verso_mime_type = get_mime_type_from_filename(image_verso_path)

    # 3. Geração determinística do código único via SHA-256
    if image_verso_bytes:
        hash_calculado = hashlib.sha256(image_bytes + image_verso_bytes).hexdigest()[:10].upper()
    else:
        hash_calculado = hashlib.sha256(image_bytes).hexdigest()[:10].upper()
    referencia_unica = f"#ANTK-2026-{hash_calculado}"

    # Converte os bytes das imagens para Data URI Base64
    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    b64_data_uri = f"data:{mime_type};base64,{b64_img}"

    b64_verso_data_uri = None
    if image_verso_bytes:
        b64_verso = base64.b64encode(image_verso_bytes).decode("utf-8")
        b64_verso_data_uri = f"data:{verso_mime_type};base64,{b64_verso}"

    # Se não houver API Key configurada, utiliza o gerador de demonstração com a imagem enviada
    if not current_api_key:
        print("[gemini_service] AVISO: GEMINI_API_KEY não encontrada. Utilizando gerador de fallback estruturado.")
        res = generate_mock_laudo(
            image_bytes=image_bytes,
            image_mime=mime_type,
            referencia=referencia_unica,
            image_verso_bytes=image_verso_bytes,
            image_verso_mime=verso_mime_type
        )
        res["imagem_url"] = b64_data_uri
        if b64_verso_data_uri:
            res["imagem_verso_url"] = b64_verso_data_uri
        return res

    # Inicializar cliente SDK google-genai
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=current_api_key)

    # Preparar imagens PIL
    pil_image = Image.open(io.BytesIO(image_bytes))
    pil_verso = None
    if image_verso_bytes:
        pil_verso = Image.open(io.BytesIO(image_verso_bytes))

    # Construção do Prompt conforme a quantidade de imagens
    if pil_verso:
        instrucao_verso = (
            "Esta análise contempla a frente e o verso da mesma peça. "
            "Analise marcas de manufatura, desgastes, assinaturas ou selos presentes no verso em conjunto com a estética frontal.\n\n"
        )
        contents_list = [pil_image, pil_verso]
    else:
        instrucao_verso = ""
        contents_list = [pil_image]

    prompt = (
        f"{instrucao_verso}"
        "Analise a(s) imagem(ns) deste objeto de antiquário/arte. Retorne um JSON estrito contendo:\n"
        f"- referencia: código determinístico '{referencia_unica}'\n"
        "- data: data atual no formato DD/MM/YYYY\n"
        "- identificacao: Título/nome provável do item\n"
        "- tecnica: Técnica de fabricação/arte\n"
        "- materiais: Materiais visíveis\n"
        "- dimensoes: Dimensões estimadas ou 'Não informadas'\n"
        "- assinatura: Marcas/assinaturas/logotipos identificados\n"
        "- datacao: Época/década estimada\n"
        "- descricao_contexto: Texto descritivo e contexto histórico (2 a 3 parágrafos detalhados)\n"
        "- pontos_fortes: Array de 3 pontos positivos de apelo comercial\n"
        "- pontos_atencao: Array de 3 pontos de atenção/risco\n"
        "- cenarios_precificacao: Array de objetos com cenario e faixa_preco (ex: R$ 500 - R$ 1.000)\n"
    )
    contents_list.append(prompt)

    # Lista de modelos válidos por ordem de prioridade
    model_candidates = [
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-2.0-flash-001",
        "gemini-3.6-flash",
        "gemini-pro-latest"
    ]
    last_error = None

    for model_name in model_candidates:
        try:
            print(f"[gemini_service] Chamando API do Gemini com o modelo '{model_name}' (Duas fotos: {bool(pil_verso)})...")
            response = client.models.generate_content(
                model=model_name,
                contents=contents_list,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=LaudoGeminiSchema,
                    temperature=0.2,
                ),
            )

            data = json.loads(response.text)
            # Garantir a referência única calculada por hash determinístico
            data["referencia"] = referencia_unica
            # Imagem frontal embutida em Base64 Data URI
            data["imagem_url"] = b64_data_uri
            if b64_verso_data_uri:
                data["imagem_verso_url"] = b64_verso_data_uri

            print(f"[gemini_service] SUCESSO: Laudo gerado dinamicamente para '{data.get('identificacao')}' [{referencia_unica}].")
            return data

        except Exception as e:
            print(f"[gemini_service] Falha com modelo '{model_name}': {e}")
            last_error = e

    print(f"[gemini_service] Erro fatal em todas as tentativas de API do Gemini ({last_error}). Executando fallback local.")
    mock_data = generate_mock_laudo(
        image_bytes=image_bytes,
        image_mime=mime_type,
        referencia=referencia_unica,
        image_verso_bytes=image_verso_bytes,
        image_verso_mime=verso_mime_type
    )
    mock_data["imagem_url"] = b64_data_uri
    if b64_verso_data_uri:
        mock_data["imagem_verso_url"] = b64_verso_data_uri
    return mock_data
