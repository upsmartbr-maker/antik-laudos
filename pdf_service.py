import os
import io
import base64
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
import qrcode

def get_logo_base64() -> str:
    """Carrega a imagem estática do logo e converte em data URI base64 otimizado com Pillow (< 10 KB)."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(base_dir, "static", "Logo Antik.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            from gemini_service import otimizar_imagem_base64
            return otimizar_imagem_base64(f.read(), max_dim=250, quality=80)
    return ""

def gerar_qrcode_laudo(hash_foto: str) -> str:
    """Gera um QR Code em Data URI base64 direcionando para a URL de validação do laudo."""
    target_url = f"https://www.antik.com.br/laudo/{hash_foto}"
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=1,
        )
        qr.add_data(target_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#2A2322", back_color="#FFFFFF")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{encoded}"
    except Exception as e:
        print(f"[pdf_service] Erro ao gerar QR Code: {e}")
        return ""

def render_html_laudo(data: Dict[str, Any]) -> str:
    """Renderiza o template HTML do laudo usando Jinja2."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(base_dir, "templates")
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template("laudo_template.html")
    
    logo_b64 = data.get("logo_base64") or get_logo_base64()
    
    ref = data.get("referencia", "#ANTK-2026-0000")
    hash_foto = data.get("hash_foto")
    if not hash_foto:
        hash_foto = ref.replace("#ANTK-2026-", "").replace("#", "") or "ANTK2026"
        
    qrcode_b64 = data.get("qrcode_base64") or gerar_qrcode_laudo(hash_foto)

    html_content = template.render(
        referencia=ref,
        hash_foto=hash_foto,
        qrcode_base64=qrcode_b64,
        data=data.get("data", ""),
        identificacao=data.get("identificacao", ""),
        tecnica=data.get("tecnica", ""),
        materiais=data.get("materiais", ""),
        dimensoes=data.get("dimensoes", "Não informadas"),
        assinatura=data.get("assinatura", ""),
        datacao=data.get("datacao", ""),
        descricao_contexto=data.get("descricao_contexto", ""),
        pontos_fortes=data.get("pontos_fortes", []),
        pontos_atencao=data.get("pontos_atencao", []),
        cenarios_precificacao=data.get("cenarios_precificacao", []),
        imagem_url=data.get("imagem_url", ""),
        imagem_verso_url=data.get("imagem_verso_url", ""),
        logo_base64=logo_b64
    )
    
    return html_content

async def convert_html_to_pdf(html_content: str) -> bytes:
    """
    Converte o HTML renderizado em PDF A4 de página única com fidelidade visual impecável.
    Utiliza Playwright (Headless Chromium) para suporte total a CSS @page e print-color-adjust.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            page = await browser.new_page()
            
            # Carrega o HTML com domcontentloaded e timeout estrito de 5s
            await page.set_content(html_content, wait_until="domcontentloaded", timeout=5000)
            
            # Gera o PDF em formato A4 sem margens extras para respeitar o CSS
            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"}
            )
            
            await browser.close()
            return pdf_bytes
            
    except Exception as e:
        print(f"[pdf_service] Erro ao gerar PDF com Playwright: {e}. Tentando fallback leve com xhtml2pdf...")
        try:
            import io
            from xhtml2pdf import pisa
            pdf_buffer = io.BytesIO()
            pisa_status = pisa.CreatePDF(html_content, dest=pdf_buffer)
            if pisa_status.err:
                raise RuntimeError(f"Erro no pisa/xhtml2pdf: {pisa_status.err}")
            return pdf_buffer.getvalue()
        except Exception as xhtml_err:
            raise RuntimeError(f"Falha na geração do PDF (Playwright: {e} | xhtml2pdf: {xhtml_err})")
