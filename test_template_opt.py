import os
from pdf_service import render_html_laudo, get_logo_base64, gerar_qrcode_laudo

def test_template_optimizations():
    print("=== TESTE DE OTIMIZAÇÕES DO TEMPLATE DE LAUDO ===")
    
    descricao_3_paragrafos = (
        "Composição tridimensional do tipo assemblage representando o modelo automobilístico Peugeot de 1912, "
        "estruturada com engrenagens, parafusos e componentes mecânicos ornamentais em tons dourados envelhecidos.\n\n"
        "A peça encontra-se acondicionada em caixa-vitrine (shadow box) nobre revestida interiormente em veludo preto, "
        "conferindo excepcional contraste e realce aos detalhes metálicos de época.\n\n"
        "O exemplar possui relevância histórica ao celebrar as conquistas do automobilismo clássico europeu da década de 1910, "
        "apresentando excelente estado de conservação sem oxidações ativas nos metais ornamentais."
    )
    
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
        "imagem_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    }
    
    html = render_html_laudo(mock_data)
    
    # 1. Validação de remoção de base64 duplicado do logo
    logo_b64 = get_logo_base64()
    count_logo_in_html = html.count(logo_b64)
    print(f"Ocorrências do Base64 do logotipo no HTML: {count_logo_in_html}")
    assert count_logo_in_html == 1, f"Esperado exatamente 1 ocorrência do Base64 no HTML, obtido {count_logo_in_html}!"
    assert '<img src="{{ logo_base64 }}" class="watermark"' not in html
    assert '<img' not in html.split('class="watermark"')[0][-30:] if 'class="watermark"' in html else True
    print("✓ Sucesso: Base64 do logotipo não está duplicado! Apenas 1 ocorrência presente.")
    
    # 2. Validação do QR Code
    assert 'class="header-qrcode"' in html, "Tag do QR Code não encontrada!"
    assert 'https://www.antik.com.br/laudo/F9A8B7C6' in html, "URL do QR Code não encontrada!"
    assert 'data:image/png;base64,' in html, "QR Code base64 não gerado!"
    print("✓ Sucesso: QR Code presente no cabeçalho com URL correta de autenticação.")
    
    # 3. Validação de Padding e Fonte
    assert "padding: 10mm 12mm 10mm 12mm;" in html, "Padding A4 incorreto!"
    assert "Baskerville" in html, "Fallback de fonte serif não encontrado!"
    assert "Times New Roman" in html, "Fallback Times New Roman não encontrado!"
    print("✓ Sucesso: Padding A4 de 10mm 12mm e fallbacks de fontes devidamente configurados.")
    
    print("\n=======================================================")
    print(" TODOS OS REQUISITOS DO TEMPLATE FORAM ATENDIDOS 100%! ")
    print("=======================================================")

if __name__ == "__main__":
    test_template_optimizations()
