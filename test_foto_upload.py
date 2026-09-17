import asyncio
import os
from fastapi.testclient import TestClient
from main import app

def test_upload_foto_endpoint():
    print("==================================================")
    print("  Casa Antik - Teste de Endpoint /gerar-laudo-foto")
    print("==================================================")
    
    client = TestClient(app)
    
    # Validação de segurança: chamada não autenticada bloqueada
    resp_unauth = client.post("/gerar-laudo-foto")
    assert resp_unauth.status_code == 401, "Endpoint /gerar-laudo-foto deve exigir autenticação (401)"

    # Autentica como Administrador
    import auth_service
    admin_email, admin_pass = auth_service.get_admin_credentials()
    client.post("/admin/login", data={"email": admin_email, "password": admin_pass})

    # Usar imagem estática de teste
    test_img = os.path.join("static", "Logo Antik.png")
    assert os.path.exists(test_img), "Imagem estática de teste não encontrada"

    with open(test_img, "rb") as f:
        response = client.post(
            "/gerar-laudo-foto",
            files={"file": ("foto_teste.png", f, "image/png")}
        )

    print(f"Status Code: {response.status_code}")
    print(f"Content-Type: {response.headers.get('content-type')}")
    print(f"Content-Disposition: {response.headers.get('content-disposition')}")
    
    assert response.status_code == 200
    assert response.headers.get("content-type") == "application/pdf"
    
    pdf_size_kb = len(response.content) / 1024
    output_pdf = "laudo_upload_foto_teste.pdf"
    with open(output_pdf, "wb") as f:
        f.write(response.content)

    print(f"[SUCESSO] PDF do upload gerado com {pdf_size_kb:.2f} KB em '{output_pdf}'")
    print("==================================================")

if __name__ == "__main__":
    test_upload_foto_endpoint()
