import asyncio
from fastapi.testclient import TestClient
from main import app
import auth_service
import supabase_service

client = TestClient(app)

def test_admin_flow():
    print("=== TESTE 0: GET /admin e /admin/ redirecionam para /admin/login ===")
    r_admin = client.get("/admin", follow_redirects=False)
    assert r_admin.status_code == 303, f"Esperado 303, obtido {r_admin.status_code}"
    assert r_admin.headers.get("location") == "/admin/login"

    r_admin_slash = client.get("/admin/", follow_redirects=False)
    assert r_admin_slash.status_code == 303, f"Esperado 303, obtido {r_admin_slash.status_code}"
    assert r_admin_slash.headers.get("location") == "/admin/login"
    print("✓ GET /admin e /admin/ redirecionam com 303 para /admin/login.")

    print("\n=== TESTE 1: GET /admin/login sem autenticação ===")
    r = client.get("/admin/login")
    assert r.status_code == 200, f"Esperado 200, obtido {r.status_code}"
    assert "Casa Antik" in r.text
    assert "E-mail Administrativo" in r.text
    print("✓ GET /admin/login retornou 200 OK com formulário Casa Antik.")

    print("\n=== TESTE 2: POST /admin/login com credenciais inválidas ===")
    r = client.post("/admin/login", data={"email": "errado@email.com", "password": "senhaerrada"})
    assert r.status_code == 401, f"Esperado 401, obtido {r.status_code}"
    assert "E-mail ou senha incorretos" in r.text
    print("✓ Rejeitou credenciais incorretas com status 401.")

    print("\n=== TESTE 3: POST /admin/login com credenciais corretas ===")
    admin_email, admin_pass = auth_service.get_admin_credentials()
    r = client.post("/admin/login", data={"email": admin_email, "password": admin_pass}, follow_redirects=False)
    assert r.status_code == 303, f"Esperado 303 Redirect, obtido {r.status_code}"
    assert r.headers.get("location") == "/admin/dashboard"
    cookie = r.cookies.get(auth_service.COOKIE_NAME)
    assert cookie is not None, "Cookie de sessão não foi gerado!"
    print(f"✓ Autenticação com sucesso! Redirecionado para /admin/dashboard com cookie {auth_service.COOKIE_NAME}.")

    print("\n=== TESTE 4: GET /admin/dashboard desprotegido vs autenticado ===")
    # Sem cookie em cliente anônimo
    anon_client = TestClient(app)
    r_unauth = anon_client.get("/admin/dashboard", follow_redirects=False)
    assert r_unauth.status_code == 303, f"Esperado 303, obtido {r_unauth.status_code}"
    assert r_unauth.headers.get("location") == "/admin/login"
    print("✓ Acesso não autenticado a /admin/dashboard redirecionou para /admin/login.")

    # Com cookie
    r_auth = anon_client.get("/admin/dashboard", cookies={auth_service.COOKIE_NAME: cookie})
    assert r_auth.status_code == 200, f"Esperado 200, obtido {r_auth.status_code}"
    assert "Painel Administrativo" in r_auth.text
    assert "Cadastrar Novo Usuário" in r_auth.text
    assert "Copiar Acesso" in r_auth.text
    print("✓ Acesso autenticado a /admin/dashboard exibiu o painel com sucesso.")

    print("\n=== TESTE 5: POST /admin/usuarios (Cadastro e Geração de Credenciais) ===")
    # Sem cookie -> 401
    r_no_auth = anon_client.post("/admin/usuarios", json={
        "nome": "Cliente Teste",
        "email": "cliente@teste.com",
        "tipo_validade": "Meses",
        "periodo": 6
    })
    assert r_no_auth.status_code == 401, f"Esperado 401, obtido {r_no_auth.status_code}"
    print("✓ Endpoint /admin/usuarios protegido contra acesso não autorizado.")

    # Com cookie -> Cadastra
    r_cad = client.post(
        "/admin/usuarios",
        json={
            "nome": "Cliente Premium Antik",
            "email": "antiquario@exemplo.com",
            "tipo_validade": "Meses",
            "periodo": 6
        }
    )
    assert r_cad.status_code == 200, f"Esperado 200, obtido {r_cad.status_code}: {r_cad.text}"
    dados = r_cad.json()
    assert dados["email"] == "antiquario@exemplo.com"
    assert len(dados["senha"]) == 10, f"Senha gerada deve ter 10 caracteres! Obtido: {dados['senha']}"
    assert any(c.isupper() for c in dados["senha"]), "Senha deve ter maiúsculas"
    assert any(c.islower() for c in dados["senha"]), "Senha deve ter minúsculas"
    assert any(c.isdigit() for c in dados["senha"]), "Senha deve ter números"
    assert "data_expiracao" in dados
    print(f"✓ Usuário cadastrado! Senha gerada: {dados['senha']} (10 caracteres seguros), Validade: {dados['data_expiracao']}")

    print("\n=== TESTE 6: Normalização de credenciais com espaços e maiúsculas ===")
    r_norm = client.post(
        "/admin/login",
        data={"email": f"  {admin_email.upper()}  ", "password": f"  {admin_pass}  "},
        follow_redirects=False
    )
    assert r_norm.status_code == 303, f"Esperado 303 com normalização, obtido {r_norm.status_code}"
    print("✓ Normalização .strip().lower() e .strip() validada com sucesso.")

    print("\n=== TESTE 7: Rotas de Usuário Comum (/login, /logout, /) ===")
    anon = TestClient(app)
    # / redireciona para /login se não autenticado
    r_home_anon = anon.get("/", follow_redirects=False)
    assert r_home_anon.status_code == 303
    assert r_home_anon.headers.get("location") == "/login"
    print("✓ Acesso a / sem autenticação redireciona para /login.")

    # /login carrega tela
    r_login_page = anon.get("/login")
    assert r_login_page.status_code == 200
    assert "Casa Antik" in r_login_page.text
    assert "E-mail de Acesso" in r_login_page.text
    print("✓ GET /login carregou a tela de login de usuários com sucesso.")

    # Usuário comum não acessa dashboard de admin
    user_token = auth_service.create_user_token("cliente@teste.com", "Cliente Teste")
    r_user_dashboard = anon.get("/admin/dashboard", cookies={auth_service.USER_COOKIE_NAME: user_token}, follow_redirects=False)
    assert r_user_dashboard.status_code == 303
    assert r_user_dashboard.headers.get("location") == "/admin/login"
    print("✓ Usuário comum impedido de acessar /admin/dashboard (separação de rotas garantida).")

    # Logout geral
    r_user_logout = anon.get("/logout", follow_redirects=False)
    assert r_user_logout.status_code == 303
    assert r_user_logout.headers.get("location") == "/login"
    print("✓ GET /logout redirecionou para /login.")

    print("\n=== TESTE 8: Logout Admin ===")
    r_logout = client.get("/admin/logout", follow_redirects=False)
    assert r_logout.status_code == 303
    assert r_logout.headers.get("location") == "/admin/login"
    print("✓ Logout administrativo efetuado e redirecionado para o login.")

    print("\n=======================================================")
    print(" TODOS OS TESTES PASSARAM COM SUCESSO ABSOLUTO! (100%) ")
    print("=======================================================")

if __name__ == "__main__":
    test_admin_flow()
