import os
from fastapi.testclient import TestClient
from main import app

def test_interactive_flow():
    print("==================================================")
    print("  Casa Antik - Teste de Fluxo Interativo / Preview & PDF")
    print("==================================================")

    client = TestClient(app)
    test_img = os.path.join("static", "Logo Antik.png")
    assert os.path.exists(test_img), "Imagem de teste ausente"

    # Validação de segurança: chamada não autenticada bloqueada
    resp_unauth = client.post("/preview-laudo")
    assert resp_unauth.status_code == 401, "Deve exigir autenticação (401)"

    # Autentica para o teste operacional
    import auth_service
    admin_email, admin_pass = auth_service.get_admin_credentials()
    client.post("/admin/login", data={"email": admin_email, "password": admin_pass})

    # 1. Teste da rota /preview-laudo (HTML Response)
    print("[1/2] Testando POST /preview-laudo com UploadFile autenticado...")
    with open(test_img, "rb") as f:
        resp_preview = client.post(
            "/preview-laudo",
            files={"file": ("foto_preview_test.png", f, "image/png")}
        )

    print(f"      Status Preview: {resp_preview.status_code}")
    assert resp_preview.status_code == 200
    assert "text/html" in resp_preview.headers.get("content-type")
    assert "Casa Antik" in resp_preview.text
    print("      [SUCESSO] Rota /preview-laudo retornou o HTML renderizado corretamente.")

    # 2. Teste da rota /gerar-laudo-foto (PDF Response)
    print("[2/2] Testando POST /gerar-laudo-foto com UploadFile...")
    with open(test_img, "rb") as f:
        resp_pdf = client.post(
            "/gerar-laudo-foto",
            files={"file": ("foto_pdf_test.png", f, "image/png")}
        )

    print(f"      Status PDF: {resp_pdf.status_code}")
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers.get("content-type") == "application/pdf"
    print(f"      [SUCESSO] PDF gerado via Playwright com {len(resp_pdf.content)/1024:.2f} KB.")

    print("==================================================")

if __name__ == "__main__":
    test_interactive_flow()
