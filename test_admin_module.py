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

    print("\n=== TESTE 8: Edição de Usuário (/admin/usuarios/{id}/editar) ===")
    r_edit = client.post(
        "/admin/usuarios/antiquario@exemplo.com/editar",
        json={
            "nome": "Antiquário Nobre Atualizado",
            "tipo_validade": "Meses",
            "quantidade_validade": 12,
            "gerar_nova_senha": True
        }
    )
    assert r_edit.status_code == 200, f"Falha ao editar: {r_edit.status_code} {r_edit.text}"
    data_edit = r_edit.json()
    assert data_edit["nome"] == "Antiquário Nobre Atualizado"
    assert "senha" in data_edit and data_edit["senha"] is not None
    print(f"✓ Usuário editado com sucesso! Nova senha: {data_edit['senha']}")

    # Edição não autorizada
    r_edit_unauth = anon.post("/admin/usuarios/antiquario@exemplo.com/editar", json={"nome": "Hacker"})
    assert r_edit_unauth.status_code == 401
    print("✓ Edição protegida contra acesso não autenticado (401).")

    print("\n=== TESTE 9: Exclusão de Usuário (/admin/usuarios/{id}/excluir) ===")
    r_del = client.post("/admin/usuarios/antiquario@exemplo.com/excluir")
    assert r_del.status_code == 200, f"Falha ao excluir: {r_del.status_code}"
    print("✓ Usuário excluído com sucesso via POST /excluir.")

    # Exclusão via DELETE
    r_del_method = client.delete("/admin/usuarios/outro@exemplo.com")
    assert r_del_method.status_code == 200, f"Falha ao excluir via DELETE: {r_del_method.status_code}"
    print("✓ Exclusão via DELETE /admin/usuarios/{id} validada com sucesso.")

    # Exclusão não autorizada
    r_del_unauth = anon.post("/admin/usuarios/antiquario@exemplo.com/excluir")
    assert r_del_unauth.status_code == 401
    print("✓ Exclusão protegida contra acesso não autenticado (401).")

    print("\n=== TESTE 10: Logout Admin ===")
    r_logout = client.get("/admin/logout", follow_redirects=False)
    assert r_logout.status_code == 303
    assert r_logout.headers.get("location") == "/admin/login"
    print("✓ Logout administrativo efetuado e redirecionado para o login.")

    print("\n=== TESTE 11: Cadastro de Usuário e Login com Credenciais Geradas ===")
    # 1. Admin cadastra um novo usuário
    admin_auth_client = TestClient(app)
    admin_auth_client.post("/admin/login", data={"email": admin_email, "password": admin_pass})
    
    r_novo_user = admin_auth_client.post(
        "/admin/usuarios",
        json={
            "nome": "Restaurador Antik",
            "email": "restaurador@antik.com.br",
            "tipo_validade": "Dias",
            "periodo": 30
        }
    )
    assert r_novo_user.status_code == 200, f"Falha ao cadastrar: {r_novo_user.text}"
    user_cred = r_novo_user.json()
    user_email = user_cred["email"]
    user_senha = user_cred["senha"]
    print(f"✓ Novo usuário cadastrado: {user_email} com senha gerada {user_senha}")

    # 2. Admin faz logout
    admin_auth_client.get("/admin/logout")

    # 3. Usuário anônimo tenta acessar com senha errada em /admin/login -> deve dar 401
    user_client = TestClient(app)
    r_fail_admin = user_client.post("/admin/login", data={"email": user_email, "password": "senha_errada_123"})
    assert r_fail_admin.status_code == 401, f"Esperado 401 para senha incorreta, obtido {r_fail_admin.status_code}"

    # 4. Usuário tenta login com credenciais corretas na tela /admin/login
    r_login_admin_screen = user_client.post(
        "/admin/login",
        data={"email": user_email, "password": user_senha},
        follow_redirects=False
    )
    assert r_login_admin_screen.status_code == 303, f"Esperado 303, obtido {r_login_admin_screen.status_code}"
    assert r_login_admin_screen.headers.get("location") == "/"
    cookie_user = r_login_admin_screen.cookies.get(auth_service.USER_COOKIE_NAME)
    assert cookie_user is not None, "Cookie de sessão de usuário não gerado no login via /admin/login!"
    print("✓ Sucesso: Usuário cadastrado fez login via /admin/login e foi redirecionado para / com cookie válido.")

    # 5. Usuário acessa / com a sessão gerada
    r_home_ok = user_client.get("/", cookies={auth_service.USER_COOKIE_NAME: cookie_user})
    assert r_home_ok.status_code == 200, f"Esperado 200 em /, obtido {r_home_ok.status_code}"
    assert "user-session-bar" in r_home_ok.text, "Barra de sessão não encontrada no template index.html!"
    assert "Restaurador Antik" in r_home_ok.text or "restaurador@antik.com.br" in r_home_ok.text
    assert "/logout" in r_home_ok.text, "Link de logout /logout não encontrado na interface!"
    print("✓ Sucesso: Usuário autenticado acessou / normalmente com barra de sessão e botão de logout.")

    # 6. Usuário também consegue autenticar pela tela dedicada /login
    user_client_2 = TestClient(app)
    r_login_user_screen = user_client_2.post(
        "/login",
        data={"email": user_email, "password": user_senha},
        follow_redirects=False
    )
    assert r_login_user_screen.status_code == 303, f"Esperado 303, obtido {r_login_user_screen.status_code}"
    assert r_login_user_screen.headers.get("location") == "/"
    print("✓ Sucesso: Usuário cadastrado também consegue logar via /login com sucesso total.")

    print("\n=== TESTE 12: Validação de Proteção Estrita em GET / e Fluxo de Logout ===")
    # 1. Usuário anônimo em GET / -> Redirecionado para /login
    anon_test = TestClient(app)
    r_anon_home = anon_test.get("/", follow_redirects=False)
    assert r_anon_home.status_code == 303
    assert r_anon_home.headers.get("location") == "/login"
    print("✓ Rota raiz GET / bloqueia usuário anônimo e redireciona para /login com status 303.")

    # 2. Administrador autenticado acessa GET / -> 200 OK com badge Admin
    admin_auth_client.post("/admin/login", data={"email": admin_email, "password": admin_pass})
    r_admin_home = admin_auth_client.get("/")
    assert r_admin_home.status_code == 200
    assert "user-session-bar" in r_admin_home.text
    assert "Admin" in r_admin_home.text
    assert "/logout" in r_admin_home.text
    print("✓ Administrador autenticado visualiza GET / com identificador Admin e botão de logout.")

    # 3. Usuário com assinatura expirada tenta acessar GET / -> Bloqueado e redirecionado para /login?erro=expirado
    # Cadastra usuário expirado no passado
    from datetime import date, timedelta
    data_passada = (date.today() - timedelta(days=5)).isoformat()
    supabase_service._USUARIOS_LOCAIS["expirado@antik.com.br"] = {
        "id": "expirado@antik.com.br",
        "nome": "Cliente Expirado",
        "email": "expirado@antik.com.br",
        "senha": "SenhaValida1",
        "senha_plana": "SenhaValida1",
        "tipo_validade": "Dias",
        "quantidade_validade": 1,
        "data_expiracao": data_passada
    }
    supabase_service._salvar_usuarios_locais()

    token_expirado = auth_service.create_user_token(
        email="expirado@antik.com.br",
        nome="Cliente Expirado",
        data_expiracao=data_passada
    )
    r_expired_home = anon_test.get("/", cookies={auth_service.USER_COOKIE_NAME: token_expirado}, follow_redirects=False)
    assert r_expired_home.status_code == 303, f"Esperado 303 para usuário expirado, obtido {r_expired_home.status_code}"
    assert "/assinatura-expirada" in r_expired_home.headers.get("location")
    print("✓ Usuário com período de assinatura expirado é sumariamente bloqueado e redirecionado para /assinatura-expirada.")

    # 4. Teste de GET /logout
    r_get_logout = user_client.get("/logout", follow_redirects=False)
    assert r_get_logout.status_code == 303
    assert r_get_logout.headers.get("location") == "/login"
    print("✓ GET /logout limpa cookies e redireciona para /login.")

    # 5. Teste de POST /logout
    r_post_logout = user_client.post("/logout", follow_redirects=False)
    assert r_post_logout.status_code == 303
    assert r_post_logout.headers.get("location") == "/login"
    print("✓ POST /logout limpa cookies e redireciona para /login.")

    print("\n=== TESTE 13: Auditoria e Blindagem dos Endpoints de Ação & Rotas Públicas ===")
    
    # A) Tentativa de Login com Usuário Expirado -> Redirecionado para /assinatura-expirada
    r_login_exp = anon_test.post(
        "/login",
        data={"email": "expirado@antik.com.br", "password": "SenhaValida1"},
        follow_redirects=False
    )
    assert r_login_exp.status_code == 303, f"Esperado 303, obtido {r_login_exp.status_code}"
    assert "/assinatura-expirada" in r_login_exp.headers.get("location")
    assert "email=expirado" in r_login_exp.headers.get("location")
    print("✓ Login de usuário expirado bloqueado e direcionado para /assinatura-expirada.")

    # B) Chamadas diretas de API aos endpoints de ação SEM autenticação -> 401 Unauthorized
    endpoints_protegidos = ["/gerar-laudo-foto", "/gerar-laudo", "/analisar-json", "/preview-laudo"]
    for ep in endpoints_protegidos:
        r_unauth_api = anon_test.post(ep)
        assert r_unauth_api.status_code == 401, f"Esperado 401 para {ep} sem auth, obtido {r_unauth_api.status_code}"
    print("✓ Todos os endpoints diretos (/gerar-laudo-foto, /gerar-laudo, /analisar-json, /preview-laudo) bloqueiam chamadas sem login com 401.")

    # C) Chamadas diretas de API aos endpoints de ação COM cookie expirado -> 403 Forbidden
    for ep in endpoints_protegidos:
        r_exp_api = anon_test.post(ep, cookies={auth_service.USER_COOKIE_NAME: token_expirado})
        assert r_exp_api.status_code == 403, f"Esperado 403 para {ep} com conta expirada, obtido {r_exp_api.status_code}"
        assert "expirado" in r_exp_api.json().get("detail", "").lower() or "bloqueado" in r_exp_api.json().get("detail", "").lower()
    print("✓ Todos os endpoints diretos bloqueiam usuários expirados em tempo real com status 403 Forbidden.")

    # D) Rotas públicas de validação e QR Code permanecem 100% acessíveis e desprotegidas
    r_val_busca = anon_test.get("/validar")
    assert r_val_busca.status_code == 200, f"Esperado 200 em /validar, obtido {r_val_busca.status_code}"
    assert "Consulta Pública" in r_val_busca.text or "Casa Antik" in r_val_busca.text

    r_val_slash = anon_test.get("/validar/")
    assert r_val_slash.status_code == 200

    r_val_busca_cod = anon_test.get("/validar?codigo=ANTK-TESTE-999")
    assert r_val_busca_cod.status_code == 200

    # /validar/download não exige login (retorna 404 para código inexistente em vez de 401/403)
    r_val_dl = anon_test.get("/validar/download?codigo=ANTK-TESTE-999")
    assert r_val_dl.status_code == 404, f"Esperado 404 (arquivo não encontrado no R2) sem exigir login, obtido {r_val_dl.status_code}"
    print("✓ Rotas públicas /validar e /validar/download permanecem 100% abertas sem exigir login.")

    # E) Tela pública /assinatura-expirada carrega com 200 OK e contém link do WhatsApp
    r_tela_exp = anon_test.get("/assinatura-expirada?email=restaurador@antik.com.br")
    assert r_tela_exp.status_code == 200
    assert "Assinatura de Acesso Encerrada" in r_tela_exp.text
    assert "wa.me" in r_tela_exp.text
    assert "restaurador@antik.com.br" in r_tela_exp.text
    print("✓ Tela /assinatura-expirada exibe dados da conta e botão oficial de WhatsApp.")

    print("\n=======================================================")
    print(" TODOS OS TESTES PASSARAM COM SUCESSO ABSOLUTO! (100%) ")
    print("=======================================================")

if __name__ == "__main__":
    test_admin_flow()
