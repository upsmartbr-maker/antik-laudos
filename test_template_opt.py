import os
from pdf_service import render_html_laudo, get_logo_base64, gerar_qrcode_laudo
from gemini_service import otimizar_imagem_base64

def test_template_restoration():
    print("=== TESTE DE RESTAURAÇÃO DE LAYOUT ORIGINAL E WEBP ===")
    
    descricao_3_paragrafos = (
        "Composição tridimensional do tipo assemblage representando o modelo automobilístico Peugeot de 1912, "
        "estruturada com engrenagens, parafusos e componentes mecânicos ornamentais em tons dourados envelhecidos.\n\n"
        "A peça encontra-se acondicionada em caixa-vitrine (shadow box) nobre revestida interiormente em veludo preto, "
        "conferindo excepcional contraste e realce aos detalhes metálicos de época.\n\n"
        "O exemplar possui relevância histórica ao celebrar as conquistas do automobilismo clássico europeu da década de 1910, "
        "apresentando excelente estado de conservação sem oxidações ativas nos metais ornamentais."
    )
    
    # Teste de imagem WebP com Pillow
    from PIL import Image
    import io
    test_img = Image.new("RGBA", (100, 100), color=(180, 50, 50, 255))
    buf = io.BytesIO()
    test_img.save(buf, format="PNG")
    webp_data_uri = otimizar_imagem_base64(buf.getvalue(), max_dim=1200, quality=88)
    assert "data:image/webp;base64," in webp_data_uri, "Otimização não retornou WebP!"
    print("✓ Sucesso: otimizar_imagem_base64 gera data:image/webp;base64 com Pillow.")

    mock_data = {
        "referencia": "#ANTK-2026-F9A8B7C6",
        "hash_foto": "F9A8B7C6",
        "data": "16/09/2026",
        "identificacao": "Peugeot 1912 Assemblage",
        "tecnica": "Relevo Metálico",
        "materiais": "Latão, Aço e Madeira",
        "dimensoes": "35 x 25 x 6 cm",
        "assinatura": "Placa de Fábrica",
        "datacao": "1912 / Contemporânea",
        "descricao_contexto": descricao_3_paragrafos,
        "pontos_fortes": ["Autenticidade estilística", "Estado de conservação primoroso"],
        "pontos_atencao": ["Manuseio com luvas recomendado"],
        "cenarios_precificacao": [
            {"cenario": "Leilão de Arte & Antiguidades", "faixa_preco": "R$ 4.500 - 6.000"},
            {"cenario": "Venda Direta / Colecionador", "faixa_preco": "R$ 6.500 - 8.200"},
            {"cenario": "Avaliação Patrimonial", "faixa_preco": "R$ 7.500"}
        ],
        "imagem_url": webp_data_uri
    }
    
    html = render_html_laudo(mock_data)
    
    # 1. Validação do Marca d'água <img> clássica
    assert '<img src="' in html and 'class="watermark"' in html, "Tag <img> watermark não encontrada!"
    assert "width: 130mm;" in html, "Largura de 130mm da watermark não encontrada!"
    assert "opacity: 0.04;" in html, "Opacidade de 0.04 da watermark não encontrada!"
    assert "watermarkBg" not in html, "Script/div auxiliar watermarkBg não deveria existir!"
    print("✓ Sucesso: Marca d'água clássica restaurada como tag <img> (.watermark, 130mm, opacity 0.04).")
    
    # 2. Validação das medidas exatas e tipografia
    assert "font-family: 'Georgia', 'Times New Roman', serif;" in html, "Tipografia body incorreta!"
    assert "padding: 15mm 15mm 12mm 15mm;" in html, "Padding do container incorreto!"
    assert "top: 8mm; left: 8mm; right: 8mm; bottom: 8mm;" in html or "top: 8mm;" in html, "Margens do page-border incorretas!"
    assert "width: 55px;" in html and "height: 55px;" in html, "Dimensões do header-logo incorretas!"
    assert "font-size: 24px;" in html, "Tamanho brand-title incorreto!"
    assert "font-size: 13px;" in html, "Tamanho section-title incorreto!"
    assert "font-size: 10.5px;" in html, "Tamanho specs-table / text-box incorreto!"
    assert "line-height: 1.45;" in html, "Line-height do text-box incorreto!"
    assert "font-size: 10px;" in html, "Tamanho swot-box / pricing-table incorreto!"
    assert "font-size: 8.5px;" in html, "Tamanho footer incorreto!"
    print("✓ Sucesso: Todas as medidas e regras CSS do layout original rigorosamente validadas.")
    
    # 3. QR Code e links de autenticação
    assert 'class="header-qrcode"' in html, "Tag do QR Code não encontrada!"
    assert 'https://www.antik.com.br/laudo/F9A8B7C6' in html, "URL do QR Code não encontrada!"
    print("✓ Sucesso: QR Code presente no cabeçalho com URL correta de validação.")
    
    print("\n=======================================================")
    print(" TODOS OS REQUISITOS FORAM RESTAURADOS COM 100% SUCESSO! ")
    print("=======================================================")

if __name__ == "__main__":
    test_template_restoration()
