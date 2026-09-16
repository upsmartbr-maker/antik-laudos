import os
import re
import secrets
import string
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
import httpx

# URL oficial do projeto Supabase para Casa Antik
SUPABASE_URL_DEFAULT = "https://ezpoytaapskzoueplxxq.supabase.co"
TABLE_NAME = "usuarios_antik"


def get_supabase_config() -> tuple[str, str]:
    """Retorna a URL e a chave da API do Supabase a partir das variáveis de ambiente."""
    url = os.getenv("SUPABASE_URL", SUPABASE_URL_DEFAULT).strip().rstrip("/")
    key = os.getenv("SUPABASE_KEY", "").strip()
    return url, key


def is_supabase_configured() -> bool:
    """Verifica se a URL e a Chave do Supabase foram devidamente configuradas."""
    url, key = get_supabase_config()
    return bool(url and key and key != "sua_chave_supabase_aqui")


def gerar_senha_aleatoria(tamanho: int = 10) -> str:
    """
    Gera automaticamente uma senha segura e aleatória de 10 caracteres
    contendo obrigatoriamente letras maiúsculas, minúsculas e números.
    """
    maiusculas = string.ascii_uppercase
    minusculas = string.ascii_lowercase
    numeros = string.digits
    todos_caracteres = maiusculas + minusculas + numeros

    # Garante ao menos 1 maiúscula, 1 minúscula e 1 número
    senha = [
        secrets.choice(maiusculas),
        secrets.choice(minusculas),
        secrets.choice(numeros)
    ]

    # Preenche o restante até atingir o tamanho desejado
    for _ in range(tamanho - len(senha)):
        senha.append(secrets.choice(todos_caracteres))

    # Embaralha de forma criptograficamente segura
    secrets.SystemRandom().shuffle(senha)
    return "".join(senha)


def somar_meses(data_base: date, meses: int) -> date:
    """Soma meses a uma data considerando a variação do número de dias em cada mês."""
    ano = data_base.year + (data_base.month + meses - 1) // 12
    mes = (data_base.month + meses - 1) % 12 + 1
    # Trata dias inválidos para o mês destino (ex: 31 de abril)
    dia = data_base.day
    while dia > 28:
        try:
            return date(ano, mes, dia)
        except ValueError:
            dia -= 1
    return date(ano, mes, dia)


def calcular_data_expiracao(tipo_validade: str, periodo: int, data_inicio: Optional[date] = None) -> date:
    """
    Calcula a data exata de expiração somando os dias ou meses à data atual.
    tipo_validade: 'Dias' ou 'Meses'
    periodo: quantidade inteira positiva (ex: 30 dias, 6 meses)
    """
    if data_inicio is None:
        data_inicio = date.today()

    tipo_norm = (tipo_validade or "").strip().lower()
    if "mes" in tipo_norm:
        return somar_meses(data_inicio, periodo)
    else:
        # Default para dias
        return data_inicio + timedelta(days=periodo)


def get_supabase_headers(key: str) -> dict:
    """Retorna os cabeçalhos padrão para chamadas REST ao PostgREST do Supabase."""
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


async def cadastrar_usuario_supabase(
    nome: str,
    email: str,
    tipo_validade: str,
    periodo: int = 6,
    quantidade_validade: Optional[int] = None
) -> Dict[str, Any]:
    """
    Gera senha de 10 caracteres, calcula expiração e persiste no Supabase.
    Retorna o dicionário completo do usuário cadastrado.
    """
    url, key = get_supabase_config()
    
    # Validações básicas
    nome = (nome or "").strip()
    email = (email or "").strip().lower()
    
    qtd = quantidade_validade if (quantidade_validade is not None and quantidade_validade > 0) else periodo
    if not nome:
        raise ValueError("O nome do usuário é obrigatório.")
    if not email or "@" not in email:
        raise ValueError("Um endereço de email válido é obrigatório.")
    if qtd <= 0:
        raise ValueError("O período de validade deve ser maior que zero.")

    # 1. Geração de senha e cálculo da data de expiração
    senha_gerada = gerar_senha_aleatoria(10)
    data_exp = calcular_data_expiracao(tipo_validade, qtd)
    data_exp_str = data_exp.strftime("%Y-%m-%d")
    data_exp_formatada = data_exp.strftime("%d/%m/%Y")
    data_expiracao_iso = data_exp.isoformat()

    tipo_val_formatado = "Meses" if "mes" in (tipo_validade or "").lower() else "Dias"

    # Payload alinhado com as colunas do Supabase com senha e senha_plana
    payload = {
        "nome": nome,
        "email": email,
        "senha": senha_gerada,
        "senha_plana": senha_gerada,
        "tipo_validade": tipo_val_formatado,
        "quantidade_validade": qtd,
        "data_expiracao": data_expiracao_iso
    }

    # 2. Persistência no Supabase via REST API ou Supabase SDK
    if not is_supabase_configured():
        # Retorna os dados gerados com aviso para ambiente local sem chave
        return {
            **payload,
            "periodo": qtd,
            "data_expiracao_formatada": data_exp_formatada,
            "aviso_supabase": "SUPABASE_KEY não configurada no .env. Dados gerados localmente para validação."
        }

    # Tentativa com REST API direta (httpx)
    rest_url = f"{url}/rest/v1/{TABLE_NAME}"
    headers = get_supabase_headers(key)

    payload_tentativa = dict(payload)

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(rest_url, headers=headers, json=payload_tentativa)

        # Se der erro de e-mail duplicado (409 Conflict ou código 23505), realiza UPDATE (Upsert)
        if resp.status_code == 409 or (resp.status_code == 400 and ("23505" in resp.text or "duplicate" in resp.text.lower() or "unique" in resp.text.lower())):
            patch_url = f"{url}/rest/v1/{TABLE_NAME}?email=eq.{email}"
            patch_payload = dict(payload_tentativa)
            resp_patch = await client.patch(patch_url, headers=headers, json=patch_payload)

            tentativas = 0
            while resp_patch.status_code == 400 and tentativas < 4 and ("pgrst204" in resp_patch.text.lower() or "column" in resp_patch.text.lower()):
                tentativas += 1
                match = re.search(r"Could not find the '([^']+)' column", resp_patch.text, re.IGNORECASE)
                if match:
                    coluna_faltante = match.group(1)
                    if coluna_faltante in patch_payload:
                        del patch_payload[coluna_faltante]
                        resp_patch = await client.patch(patch_url, headers=headers, json=patch_payload)
                        continue
                break

            if resp_patch.status_code in (200, 204):
                return {
                    **payload,
                    "periodo": qtd,
                    "data_expiracao_formatada": data_exp_formatada,
                    "atualizado": True,
                    "mensagem": "Cadastro já existente atualizado com nova senha e período renovado com sucesso!"
                }
        
        # Se der erro 400 com PGRST204 (coluna não encontrada no cache de schema),
        # remove a coluna não existente e retenta de forma adaptativa
        tentativas = 0
        while resp.status_code == 400 and tentativas < 4 and ("pgrst204" in resp.text.lower() or "column" in resp.text.lower()):
            tentativas += 1
            match = re.search(r"Could not find the '([^']+)' column", resp.text, re.IGNORECASE)
            if match:
                coluna_faltante = match.group(1)
                if coluna_faltante in payload_tentativa:
                    del payload_tentativa[coluna_faltante]
                    resp = await client.post(rest_url, headers=headers, json=payload_tentativa)
                    # Verifica novamente se deu duplicidade no retry
                    if resp.status_code == 409 or (resp.status_code == 400 and "23505" in resp.text):
                        patch_url = f"{url}/rest/v1/{TABLE_NAME}?email=eq.{email}"
                        resp_patch = await client.patch(patch_url, headers=headers, json=payload_tentativa)
                        if resp_patch.status_code in (200, 204):
                            return {
                                **payload,
                                "periodo": qtd,
                                "data_expiracao_formatada": data_exp_formatada,
                                "atualizado": True
                            }
                    continue
            break

        if resp.status_code in (200, 201):
            dados_retornados = resp.json()
            if isinstance(dados_retornados, list) and len(dados_retornados) > 0:
                item = dados_retornados[0]
                item["senha"] = senha_gerada  # Garante retorno da senha gerada
                item["data_expiracao_formatada"] = data_exp_formatada
                return item
            return {**payload, "periodo": qtd, "data_expiracao_formatada": data_exp_formatada}

        raise Exception(f"Erro ao salvar no Supabase ({resp.status_code}): {resp.text}")


async def editar_usuario_supabase(
    identificador: str,
    nome: Optional[str] = None,
    tipo_validade: Optional[str] = None,
    quantidade_validade: Optional[int] = None,
    gerar_nova_senha: bool = False
) -> Dict[str, Any]:
    """
    Atualiza um usuário existente no Supabase.
    Permite atualizar nome, período de acesso e opcionalmente gerar nova senha.
    """
    url, key = get_supabase_config()
    headers = get_supabase_headers(key)
    
    update_data: Dict[str, Any] = {}
    if nome:
        update_data["nome"] = nome.strip()
    
    nova_senha = None
    if gerar_nova_senha:
        nova_senha = gerar_senha_aleatoria(10)
        update_data["senha"] = nova_senha
        update_data["senha_plana"] = nova_senha

    data_exp_formatada = None
    if tipo_validade and quantidade_validade and quantidade_validade > 0:
        tipo_val_formatado = "Meses" if "mes" in tipo_validade.lower() else "Dias"
        update_data["tipo_validade"] = tipo_val_formatado
        update_data["quantidade_validade"] = quantidade_validade
        data_exp = calcular_data_expiracao(tipo_validade, quantidade_validade)
        data_exp_str = data_exp.strftime("%Y-%m-%d")
        data_exp_formatada = data_exp.strftime("%d/%m/%Y")
        update_data["data_expiracao"] = data_exp.isoformat()

    if not is_supabase_configured():
        return {
            "id": identificador,
            **update_data,
            "senha": nova_senha,
            "data_expiracao_formatada": data_exp_formatada,
            "aviso_supabase": "SUPABASE_KEY não configurada no .env. Simulado localmente."
        }

    filtro = f"id=eq.{identificador}" if not "@" in str(identificador) else f"email=eq.{identificador}"
    rest_url = f"{url}/rest/v1/{TABLE_NAME}?{filtro}"

    payload_tentativa = dict(update_data)

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.patch(rest_url, headers=headers, json=payload_tentativa)

        # Adaptação para colunas que possam não existir no schema
        tentativas = 0
        while resp.status_code == 400 and tentativas < 4 and ("pgrst204" in resp.text.lower() or "column" in resp.text.lower()):
            tentativas += 1
            match = re.search(r"Could not find the '([^']+)' column", resp.text, re.IGNORECASE)
            if match:
                coluna_faltante = match.group(1)
                if coluna_faltante in payload_tentativa:
                    del payload_tentativa[coluna_faltante]
                    resp = await client.patch(rest_url, headers=headers, json=payload_tentativa)
                    continue
            break

        if resp.status_code in (200, 204):
            # Tenta buscar os dados completos atualizados
            resp_get = await client.get(rest_url, headers=headers)
            if resp_get.status_code == 200 and resp_get.json():
                user_atualizado = resp_get.json()[0]
                if nova_senha:
                    user_atualizado["senha"] = nova_senha
                if data_exp_formatada:
                    user_atualizado["data_expiracao_formatada"] = data_exp_formatada
                return user_atualizado

            return {
                "id": identificador,
                **update_data,
                "senha": nova_senha,
                "data_expiracao_formatada": data_exp_formatada
            }

        raise Exception(f"Erro ao atualizar usuário no Supabase ({resp.status_code}): {resp.text}")


async def excluir_usuario_supabase(identificador: str) -> bool:
    """
    Remove um usuário da tabela usuarios_antik no Supabase.
    """
    url, key = get_supabase_config()
    if not is_supabase_configured():
        return True

    headers = get_supabase_headers(key)
    filtro = f"id=eq.{identificador}" if not "@" in str(identificador) else f"email=eq.{identificador}"
    rest_url = f"{url}/rest/v1/{TABLE_NAME}?{filtro}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.delete(rest_url, headers=headers)
        if resp.status_code in (200, 204):
            return True
        # Fallback: se identificador for email e a rota falhou, tenta filtro por email
        if "@" in str(identificador):
            resp_email = await client.delete(f"{url}/rest/v1/{TABLE_NAME}?email=eq.{identificador}", headers=headers)
            if resp_email.status_code in (200, 204):
                return True

        raise Exception(f"Erro ao excluir usuário no Supabase ({resp.status_code}): {resp.text}")


async def listar_usuarios_supabase() -> List[Dict[str, Any]]:
    """
    Busca todos os usuários já cadastrados na tabela usuarios_antik do Supabase.
    """
    url, key = get_supabase_config()
    if not is_supabase_configured():
        return []

    rest_url = f"{url}/rest/v1/{TABLE_NAME}?select=*&order=criado_em.desc"
    headers = get_supabase_headers(key)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(rest_url, headers=headers)
            if resp.status_code == 200:
                usuarios = resp.json()
                hoje = date.today()
                for u in usuarios:
                    # Garante um identificador válido
                    if not u.get("id"):
                        u["id"] = u.get("email")

                    # Garante campos para edição
                    u["tipo_validade"] = u.get("tipo_validade") or "Meses"
                    u["quantidade_validade"] = u.get("quantidade_validade") or u.get("periodo") or 6

                    # Data de expiração
                    dt_exp = u.get("data_expiracao")
                    if dt_exp:
                        try:
                            data_obj = datetime.fromisoformat(str(dt_exp).replace("Z", "+00:00")).date() if "T" in str(dt_exp) else datetime.strptime(str(dt_exp)[:10], "%Y-%m-%d").date()
                            u["data_expiracao_formatada"] = data_obj.strftime("%d/%m/%Y")
                            u["expirado"] = data_obj < hoje
                        except Exception:
                            u["data_expiracao_formatada"] = str(dt_exp)
                            u["expirado"] = False
                    else:
                        u["data_expiracao_formatada"] = "Indefinida"
                        u["expirado"] = False

                    # Data de criação
                    dt_cria = u.get("criado_em") or u.get("created_at")
                    if dt_cria:
                        try:
                            cria_obj = datetime.fromisoformat(str(dt_cria).replace("Z", "+00:00"))
                            u["data_criacao_formatada"] = cria_obj.strftime("%d/%m/%Y %H:%M")
                        except Exception:
                            u["data_criacao_formatada"] = str(dt_cria)[:16]
                    else:
                        u["data_criacao_formatada"] = "-"

                return usuarios
            elif resp.status_code == 400 and "order" in resp.text:
                rest_url_fallback = f"{url}/rest/v1/{TABLE_NAME}?select=*"
                resp_fb = await client.get(rest_url_fallback, headers=headers)
                if resp_fb.status_code == 200:
                    usuarios = resp_fb.json()
                    for u in usuarios:
                        if not u.get("id"):
                            u["id"] = u.get("email")
                        u["tipo_validade"] = u.get("tipo_validade") or "Meses"
                        u["quantidade_validade"] = u.get("quantidade_validade") or u.get("periodo") or 6
                    return usuarios
    except Exception as e:
        print(f"[Supabase] Erro ao listar usuários: {e}")
        return []

    return []


async def autenticar_usuario_supabase(email: str, senha: str) -> tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Autentica um usuário cadastrado na tabela usuarios_antik:
    1. Normaliza e-mail com .strip().lower() e senha com .strip()
    2. Consulta o Supabase com filtro .eq("email", email_limpo)
    3. Valida se a senha corresponde ao campo salvo (senha ou senha_plana)
    4. Verifica se data_expiracao não expirou em relação à data atual
    """
    email_limpo = (email or "").strip().lower()
    senha_limpa = (senha or "").strip()

    if not email_limpo or not senha_limpa:
        return False, "Por favor, preencha o e-mail e a senha.", None

    url, key = get_supabase_config()
    if not is_supabase_configured():
        # Caso em desenvolvimento local sem chave do Supabase configurada
        return False, "Configuração do Supabase não encontrada no servidor (.env).", None

    rest_url = f"{url}/rest/v1/{TABLE_NAME}?email=eq.{email_limpo}&select=*"
    headers = get_supabase_headers(key)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(rest_url, headers=headers)
            if resp.status_code != 200:
                print(f"[Supabase Login] Erro na consulta ({resp.status_code}): {resp.text}")
                return False, "Erro ao consultar credenciais no banco de dados.", None

            usuarios = resp.json()
            if not usuarios or not isinstance(usuarios, list) or len(usuarios) == 0:
                return False, "E-mail ou senha incorretos.", None

            user_data = usuarios[0]

            # Validação da senha salva (senha ou senha_plana)
            senha_salva = str(user_data.get("senha") or user_data.get("senha_plana") or "").strip()
            if not senha_salva or senha_limpa != senha_salva:
                return False, "E-mail ou senha incorretos.", None

            # Validação da data de validade (data_expiracao)
            data_exp = user_data.get("data_expiracao")
            if data_exp:
                try:
                    hoje = date.today()
                    if "T" in str(data_exp):
                        dt_exp = datetime.fromisoformat(str(data_exp).replace("Z", "+00:00")).date()
                    else:
                        dt_exp = datetime.strptime(str(data_exp)[:10], "%Y-%m-%d").date()

                    if dt_exp < hoje:
                        return False, "Assinatura ou período de acesso expirado.", user_data
                except Exception as e:
                    print(f"[Supabase Login] Erro ao parsear data_expiracao: {e}")

            # Usuário autenticado com sucesso
            return True, "Login realizado com sucesso.", user_data

    except Exception as e:
        print(f"[Supabase Login] Exceção durante autenticação: {e}")
        return False, f"Falha na comunicação com o servidor de autenticação: {str(e)}", None
