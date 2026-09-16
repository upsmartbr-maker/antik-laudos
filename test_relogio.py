import asyncio
import json
from gemini_service import gerar_dados_laudo_gemini
from pdf_service import render_html_laudo, convert_html_to_pdf

async def run_test():
    url = "https://images.unsplash.com/photo-1509042239860-f550ce710b93?w=600"
    print("[1] Solicitando analise do relogio ao Gemini...")
    res = await gerar_dados_laudo_gemini(image_url=url)
    print("[2] RESPOSTA DO GEMINI:")
    print(" - Identificacao:", res.get("identificacao"))
    print(" - Tecnica:", res.get("tecnica"))
    print(" - Materiais:", res.get("materiais"))
    print(" - Datacao:", res.get("datacao"))
    print(" - Descricao:", res.get("descricao_contexto"))
    print(" - Pontos Fortes:", res.get("pontos_fortes"))
    print(" - Pontos de Atencao:", res.get("pontos_atencao"))
    print(" - Precificacao:", res.get("cenarios_precificacao"))
    
    print("[3] Renderizando HTML com Jinja2...")
    html = render_html_laudo(res)
    
    print("[4] Convertendo para PDF...")
    pdf = await convert_html_to_pdf(html)
    with open("laudo_relogio_teste.pdf", "wb") as f:
        f.write(pdf)
    print("[SUCESSO] laudo_relogio_teste.pdf gerado com sucesso!")

if __name__ == "__main__":
    asyncio.run(run_test())
