import asyncio
import os
from gemini_service import gerar_dados_laudo_gemini
from pdf_service import render_html_laudo, convert_html_to_pdf

async def main():
    print("==================================================")
    print("   Casa Antik - Teste de Geração de Laudo em PDF")
    print("==================================================")
    
    # Usar a imagem de logo como teste se nenhuma outra estiver disponível
    sample_img_path = os.path.join("static", "Logo Antik.png")
    if not os.path.exists(sample_img_path):
        print("Imagem de teste não encontrada!")
        return

    with open(sample_img_path, "rb") as f:
        img_bytes = f.read()

    print("[1/3] Solicitando análise e dados em JSON estrito...")
    laudo_data = await gerar_dados_laudo_gemini(image_bytes=img_bytes, image_url=None)
    print(f"      Referência gerada: {laudo_data.get('referencia')}")
    print(f"      Identificação: {laudo_data.get('identificacao')}")
    
    print("[2/3] Renderizando template HTML com Jinja2...")
    html_content = render_html_laudo(laudo_data)
    
    with open("test_laudo_preview.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("      HTML de teste salvo em: test_laudo_preview.html")

    print("[3/3] Convertendo HTML para PDF A4 via Playwright...")
    pdf_bytes = await convert_html_to_pdf(html_content)
    
    output_pdf_path = "laudo_gerado_teste.pdf"
    with open(output_pdf_path, "wb") as f:
        f.write(pdf_bytes)
        
    pdf_size_kb = len(pdf_bytes) / 1024
    print(f"[SUCESSO] PDF gerado com {pdf_size_kb:.2f} KB em '{output_pdf_path}'")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())
