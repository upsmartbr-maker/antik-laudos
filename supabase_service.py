import os
import re
import json
import time
import secrets
import string
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any, Union
import httpx

# URL oficial do projeto Supabase para Casa Antik
SUPABASE_URL_DEFAULT = "https://ezpoytaapskzoueplxxq.supabase.co"
TABLE_NAME = "usuarios_antik"

# Armazenamento em memória com persistência local de fallback
_USUARIOS_LOCAIS: Dict[str, Dict[str, Any]] = {}
LOCAL_STORAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usuarios_locais.json")

# Cache em memória para verificação rápida de usuário ativo (TTL em segundos)
_CACHE_STATUS_USUARIOS: Dict[str, tuple[float, bool, str, Optional[Dict[str, Any]]]] = {}
CACHE_TTL_SEGUNDOS = 30


def _carregar_usuarios_locais() -> Dict[str, Dict[str, Any]]:
    """Carrega os usuários armazenados localmente do arquivo usuarios_locais.json."""
    global _USUARIOS_LOCAIS
    if os.path.exists(LOCAL_STORAGE_FILE):
        try:
            with open(LOCAL_STORAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    _USUARIOS_LOCAIS.update(data)
        except Exception as e:
            print(f"[Supabase] Erro ao carregar usuarios_locais.json: {e}")
    return _USUARIOS_LOCAIS


def _salvar_usuarios_locais() -> None:
    """Persiste os usuários locais em disco para não perder dados entre reinicializações."""
    try:
        with open(LOCAL_STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(_USUARIOS_LOCAIS, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Supabase] Erro ao salvar usuarios_locais.json: {e}")


def _limpar_cache_usuario(identificador: Optional[str] = None) -> None:
    """Invalida o cache de verificação de usuário ativo."""
    global _CACHE_STATUS_USUARIOS
    if not identificador:
        _CACHE_STATUS_USUARIOS.clear()
        return
    id_clean = str(identificador).strip().lower()
    chaves_para_remover = [k for k in _CACHE_STATUS_USUARIOS if k == id_clean]
    for k in chaves_para_remover:
        _CACHE_STATUS_USUARIOS.pop(k, None)


# Inicializa o carregamento dos usuários locais ao carregar o módulo
_carregar_usuarios_locais()


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

    senha = [
        secrets.choice(maiusculas),
        secrets.choice(minusculas),
        secrets.choice(numeros)
    ]

    for _ in range(tamanho - len(senha)):
        senha.append(secrets.choice(todos_caracteres))

    secrets.SystemRandom().shuffle(senha)
    return "".join(senha)


def somar_meses(data_base: date, meses: int) -> date:
    """Soma meses a uma data considerando a variação do número de dias em cada mês."""
    ano = data_base.year + (data_base.month + meses - 1) // 12
    mes = (data_base.month + meses - 1) % 12 + 1
    dia = data_base.day
    while dia > 28:
        try:
            return date(ano, mes, dia)
        except ValueError:
            dia -= 1
    return date(ano, mes, dia)


def parse_expiration_datetime_utc(data_exp_val: Any) -> Optional[datetime]:
    """
    Converte com máxima robustez qualquer valor de expiração para um datetime com tzinfo=timezone.utc.
    Aceita:
    - datetime (com ou sem tz)
    - date
    - strings ISO 8601 (ex: '2026-09-17T23:59:59+00:00', '2026-09-17T23:59:59Z')
    - strings de data simples (ex: '2026-09-17' ou '17/09/2026')
    """
    if data_exp_val is None:
        return None

    if isinstance(data_exp_val, datetime):
        if data_exp_val.tzinfo is None:
            return data_exp_val.replace(tzinfo=timezone.utc)
        return data_exp_val.astimezone(timezone.utc)

    if isinstance(data_exp_val, date):
        # Converte para fim do dia em UTC
        return datetime(data_exp_val.year, data_exp_val.month, data_exp_val.day, 23, 59, 59, tzinfo=timezone.utc)

    val_str = str(data_exp_val).strip()
    if not val_str or val_str.lower() in ("none", "null", "indefinida", ""):
        return None

    # Se for apenas data YYYY-MM-DD sem horário -> calibra para o fim do dia em UTC
    match_ymd = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", val_str)
    if match_ymd:
        y, m, d = int(match_ymd.group(1)), int(match_ymd.group(2)), int(match_ymd.group(3))
        return datetime(y, m, d, 23, 59, 59, tzinfo=timezone.utc)

    # Se for formato brasileiro DD/MM/YYYY sem horário -> calibra para o fim do dia em UTC
    match_dmy = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", val_str)
    if match_dmy:
        d, m, y = int(match_dmy.group(1)), int(match_dmy.group(2)), int(match_dmy.group(3))
        return datetime(y, m, d, 23, 59, 59, tzinfo=timezone.utc)

    # Normaliza sufixo 'Z' para '+00:00' para compatibilidade com Python fromisoformat
    val_norm = val_str
    if val_norm.endswith("Z"):
        val_norm = val_norm[:-1] + "+00:00"

    # Tentativa com ISO format completo com horário e fuso
    try:
        dt = datetime.fromisoformat(val_norm)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    return None


def extrair_data_expiracao_usuario(user_data: Dict[str, Any]) -> tuple[Optional[datetime], Optional[str]]:
    """
    Localiza o valor de expiração aceitando variações de nomenclatura de schema do Supabase:
    'data_expiracao', 'validade', 'expira_em', 'expires_at', 'expiration_date'.
    Retorna (datetime_utc, data_formatada_ptbr).
    """
    campos = ["data_expiracao", "validade", "expira_em", "expires_at", "expiration_date"]
    for campo in campos:
        val = user_data.get(campo)
        if val:
            dt_utc = parse_expiration_datetime_utc(val)
            if dt_utc:
                return dt_utc, dt_utc.strftime("%d/%m/%Y")

    return None, None


def usuario_esta_ativo_e_valido(user_data: Dict[str, Any]) -> tuple[bool, str, Optional[datetime]]:
    """
    Verifica de forma unificada e estrita se o usuário está ativo:
    1. Verifica flags de desativação / status (ex: ativo = false ou status = 'inativo'/'bloqueado').
    2. Valida se a data de expiração não foi ultrapassada em relação ao fuso horário UTC (datetime.now(timezone.utc)).
    Retorna (ativo: bool, motivo: str, dt_exp_utc: Optional[datetime]).
    """
    # 1. Checagem de flags explícitas
    ativo_flag = user_data.get("ativo")
    if ativo_flag is False:
        return False, "Conta desativada pela administração.", None

    status_flag = str(user_data.get("status") or "").strip().lower()
    if status_flag in ("inativo", "bloqueado", "cancelado", "expirado", "desativado", "suspenso"):
        return False, "Conta suspensa ou inativa.", None

    # 2. Checagem de expiração temporal padronizada em UTC
    dt_exp, _ = extrair_data_expiracao_usuario(user_data)
    if dt_exp:
        agora_utc = datetime.now(timezone.utc)
        if dt_exp < agora_utc:
            return False, "Assinatura ou período de acesso expirado.", dt_exp

    return True, "Usuário ativo.", dt_exp


def calcular_data_expiracao_utc(
    tipo_validade: str,
    periodo: int,
    data_inicio: Optional[Union[datetime, date]] = None
) -> datetime:
    """
    Calcula a data/hora exata de expiração somando os dias ou meses à data atual,
    com fuso horário UTC padronizado e limite de expiração calibrado para 23:59:59 UTC do último dia.
    """
    if data_inicio is None:
        base_utc = datetime.now(timezone.utc)
    elif isinstance(data_inicio, datetime):
        if data_inicio.tzinfo is None:
            base_utc = data_inicio.replace(tzinfo=timezone.utc)
        else:
            base_utc = data_inicio.astimezone(timezone.utc)
    elif isinstance(data_inicio, date):
        base_utc = datetime(data_inicio.year, data_inicio.month, data_inicio.day, tzinfo=timezone.utc)
    else:
        base_utc = datetime.now(timezone.utc)

    tipo_norm = (tipo_validade or "").strip().lower()
    if "mes" in tipo_norm:
        dt_fim = somar_meses(base_utc.date(), periodo)
        return datetime(dt_fim.year, dt_fim.month, dt_fim.day, 23, 59, 59, tzinfo=timezone.utc)
    else:
        dt_fim = (base_utc + timedelta(days=periodo)).date()
        return datetime(dt_fim.year, dt_fim.month, dt_fim.day, 23, 59, 59, tzinfo=timezone.utc)


def calcular_data_expiracao(tipo_validade: str, periodo: int, data_inicio: Optional[Any] = None) -> date:
    """Retorna o date correspondente ao cálculo UTC (compatibilidade reversa)."""
    return calcular_data_expiracao_utc(tipo_validade, periodo, data_inicio).date()


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
    Gera senha de 10 caracteres, calcula expiração UTC (TIMESTAMPTZ) e persiste no Supabase.
    Retorna o dicionário completo do usuário cadastrado.
    """
    url, key = get_supabase_config()
    
    nome = (nome or "").strip()
    email = (email or "").strip().lower()
    
    qtd = quantidade_validade if (quantidade_validade is not None and quantidade_validade > 0) else periodo
    if not nome:
        raise ValueError("O nome do usuário é obrigatório.")
    if not email or "@" not in email:
        raise ValueError("Um endereço de email válido é obrigatório.")
    if qtd <= 0:
        raise ValueError("O período de validade deve ser maior que zero.")

    # 1. Geração de senha e cálculo da data de expiração em UTC
    senha_gerada = gerar_senha_aleatoria(10)
    data_exp_dt = calcular_data_expiracao_utc(tipo_validade, qtd)
    data_exp_str = data_exp_dt.strftime("%Y-%m-%d")
    data_exp_formatada = data_exp_dt.strftime("%d/%m/%Y")
    data_expiracao_iso = data_exp_dt.isoformat()

    tipo_val_formatado = "Meses" if "mes" in (tipo_validade or "").lower() else "Dias"

    # Payload alinhado com as colunas do Supabase com TIMESTAMPTZ padronizado
    payload = {
        "nome": nome,
        "email": email,
        "senha": senha_gerada,
        "senha_plana": senha_gerada,
        "tipo_validade": tipo_val_formatado,
        "quantidade_validade": qtd,
        "data_expiracao": data_expiracao_iso
    }

    # 2. Persistência local imediata
    user_local_record = {
        "id": email,
        **payload,
        "periodo": qtd,
        "data_expiracao_formatada": data_exp_formatada,
        "criado_em": datetime.now(timezone.utc).isoformat()
    }
    _USUARIOS_LOCAIS[email] = user_local_record
    _salvar_usuarios_locais()
    _limpar_cache_usuario(email)

    if not is_supabase_configured():
        return {
            **user_local_record,
            "aviso_supabase": "SUPABASE_KEY não configurada no .env. Dados salvos localmente."
        }

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
                user_local_record["atualizado"] = True
                _USUARIOS_LOCAIS[email] = user_local_record
                _salvar_usuarios_locais()
                _limpar_cache_usuario(email)
                return {
                    **user_local_record,
                    "atualizado": True,
                    "mensagem": "Cadastro já existente atualizado com nova senha e período renovado com sucesso!"
                }
        
        # Adaptação para PGRST204 (colunas não existentes no cache de schema)
        tentativas = 0
        while resp.status_code == 400 and tentativas < 4 and ("pgrst204" in resp.text.lower() or "column" in resp.text.lower()):
            tentativas += 1
            match = re.search(r"Could not find the '([^']+)' column", resp.text, re.IGNORECASE)
            if match:
                coluna_faltante = match.group(1)
                if coluna_faltante in payload_tentativa:
                    del payload_tentativa[coluna_faltante]
                    resp = await client.post(rest_url, headers=headers, json=payload_tentativa)
                    if resp.status_code == 409 or (resp.status_code == 400 and "23505" in resp.text):
                        patch_url = f"{url}/rest/v1/{TABLE_NAME}?email=eq.{email}"
                        resp_patch = await client.patch(patch_url, headers=headers, json=payload_tentativa)
                        if resp_patch.status_code in (200, 204):
                            user_local_record["atualizado"] = True
                            _USUARIOS_LOCAIS[email] = user_local_record
                            _salvar_usuarios_locais()
                            _limpar_cache_usuario(email)
                            return {
                                **user_local_record,
                                "atualizado": True
                            }
                    continue
            break

        if resp.status_code in (200, 201):
            dados_retornados = resp.json()
            if isinstance(dados_retornados, list) and len(dados_retornados) > 0:
                item = dados_retornados[0]
                item["senha"] = senha_gerada
                item["senha_plana"] = senha_gerada
                item["data_expiracao_formatada"] = data_exp_formatada
                _USUARIOS_LOCAIS[email] = item
                _salvar_usuarios_locais()
                _limpar_cache_usuario(email)
                return item
            return user_local_record

        print(f"[Supabase] Aviso ao salvar no Supabase ({resp.status_code}): {resp.text}")
        return user_local_record


async def editar_usuario_supabase(
    identificador: str,
    nome: Optional[str] = None,
    tipo_validade: Optional[str] = None,
    quantidade_validade: Optional[int] = None,
    gerar_nova_senha: bool = False
) -> Dict[str, Any]:
    """
    Atualiza um usuário existente no Supabase com data de expiração padronizada em UTC.
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
        data_exp_dt = calcular_data_expiracao_utc(tipo_validade, quantidade_validade)
        data_exp_formatada = data_exp_dt.strftime("%d/%m/%Y")
        update_data["data_expiracao"] = data_exp_dt.isoformat()

    _carregar_usuarios_locais()
    local_key = None
    for k, v in _USUARIOS_LOCAIS.items():
        if (str(k).strip().lower() == str(identificador).strip().lower() or 
            str(v.get("id", "")).strip().lower() == str(identificador).strip().lower() or 
            str(v.get("email", "")).strip().lower() == str(identificador).strip().lower()):
            local_key = k
            break

    if local_key:
        _USUARIOS_LOCAIS[local_key].update(update_data)
        if nova_senha:
            _USUARIOS_LOCAIS[local_key]["senha"] = nova_senha
            _USUARIOS_LOCAIS[local_key]["senha_plana"] = nova_senha
        if data_exp_formatada:
            _USUARIOS_LOCAIS[local_key]["data_expiracao_formatada"] = data_exp_formatada
        _salvar_usuarios_locais()

    _limpar_cache_usuario(identificador)
    if local_key:
        _limpar_cache_usuario(local_key)

    if not is_supabase_configured():
        return {
            "id": identificador,
            **update_data,
            "senha": nova_senha,
            "data_expiracao_formatada": data_exp_formatada,
            "aviso_supabase": "SUPABASE_KEY não configurada no .env. Atualizado localmente."
        }

    filtro = f"id=eq.{identificador}" if not "@" in str(identificador) else f"email=eq.{identificador}"
    rest_url = f"{url}/rest/v1/{TABLE_NAME}?{filtro}"
    payload_tentativa = dict(update_data)

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.patch(rest_url, headers=headers, json=payload_tentativa)

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
            resp_get = await client.get(rest_url, headers=headers)
            if resp_get.status_code == 200 and resp_get.json():
                user_atualizado = resp_get.json()[0]
                if nova_senha:
                    user_atualizado["senha"] = nova_senha
                    user_atualizado["senha_plana"] = nova_senha
                if data_exp_formatada:
                    user_atualizado["data_expiracao_formatada"] = data_exp_formatada
                if local_key:
                    _USUARIOS_LOCAIS[local_key] = user_atualizado
                    _salvar_usuarios_locais()
                return user_atualizado

            return {
                "id": identificador,
                **update_data,
                "senha": nova_senha,
                "data_expiracao_formatada": data_exp_formatada
            }

        print(f"[Supabase] Erro ao atualizar no Supabase ({resp.status_code}): {resp.text}")
        return {
            "id": identificador,
            **update_data,
            "senha": nova_senha,
            "data_expiracao_formatada": data_exp_formatada
        }


async def excluir_usuario_supabase(identificador: str) -> bool:
    """
    Remove um usuário da tabela usuarios_antik no Supabase e do armazenamento local.
    """
    _carregar_usuarios_locais()
    chaves_para_remover = [
        k for k, v in _USUARIOS_LOCAIS.items()
        if (str(k).strip().lower() == str(identificador).strip().lower() or 
            str(v.get("id", "")).strip().lower() == str(identificador).strip().lower() or 
            str(v.get("email", "")).strip().lower() == str(identificador).strip().lower())
    ]
    for k in chaves_para_remover:
        del _USUARIOS_LOCAIS[k]
        _limpar_cache_usuario(k)
    if chaves_para_remover:
        _salvar_usuarios_locais()

    _limpar_cache_usuario(identificador)

    url, key = get_supabase_config()
    if not is_supabase_configured():
        return True

    headers = get_supabase_headers(key)
    filtro = f"id=eq.{identificador}" if not "@" in str(identificador) else f"email=eq.{identificador}"
    rest_url = f"{url}/rest/v1/{TABLE_NAME}?{filtro}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(rest_url, headers=headers)
            if resp.status_code in (200, 204):
                return True
            if "@" in str(identificador):
                resp_email = await client.delete(f"{url}/rest/v1/{TABLE_NAME}?email=eq.{identificador}", headers=headers)
                if resp_email.status_code in (200, 204):
                    return True
    except Exception as e:
        print(f"[Supabase] Erro ao excluir no Supabase: {e}")

    return True


async def listar_usuarios_supabase() -> List[Dict[str, Any]]:
    """
    Busca todos os usuários cadastrados no Supabase e mescla com armazenamento local.
    Calcula status 'expirado' comparando a data UTC com datetime.now(timezone.utc).
    """
    _carregar_usuarios_locais()
    usuarios_map: Dict[str, Dict[str, Any]] = {}
    agora_utc = datetime.now(timezone.utc)

    if is_supabase_configured():
        url, key = get_supabase_config()
        rest_url = f"{url}/rest/v1/{TABLE_NAME}?select=*&order=criado_em.desc"
        headers = get_supabase_headers(key)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(rest_url, headers=headers)
                if resp.status_code == 400 and "order" in resp.text:
                    resp = await client.get(f"{url}/rest/v1/{TABLE_NAME}?select=*", headers=headers)

                if resp.status_code == 200:
                    for u in resp.json():
                        email_u = str(u.get("email", "")).strip().lower()
                        if not u.get("id"):
                            u["id"] = email_u or u.get("email")

                        u["tipo_validade"] = u.get("tipo_validade") or "Meses"
                        u["quantidade_validade"] = u.get("quantidade_validade") or u.get("periodo") or 6

                        dt_exp, dt_fmt = extrair_data_expiracao_usuario(u)
                        if dt_exp:
                            u["data_expiracao_formatada"] = dt_fmt or dt_exp.strftime("%d/%m/%Y")
                            u["expirado"] = dt_exp < agora_utc
                        else:
                            u["data_expiracao_formatada"] = "Indefinida"
                            u["expirado"] = False

                        dt_cria = u.get("criado_em") or u.get("created_at")
                        dt_cria_utc = parse_expiration_datetime_utc(dt_cria)
                        if dt_cria_utc:
                            u["data_criacao_formatada"] = dt_cria_utc.strftime("%d/%m/%Y %H:%M")
                        else:
                            u["data_criacao_formatada"] = str(dt_cria or "-")[:16]

                        usuarios_map[email_u or str(u["id"])] = u
        except Exception as e:
            print(f"[Supabase] Erro ao listar usuários do Supabase: {e}")

    for k, v in _USUARIOS_LOCAIS.items():
        email_v = str(v.get("email", k)).strip().lower()
        if email_v not in usuarios_map:
            u = dict(v)
            if not u.get("id"):
                u["id"] = email_v

            dt_exp, dt_fmt = extrair_data_expiracao_usuario(u)
            if dt_exp:
                u["data_expiracao_formatada"] = dt_fmt or dt_exp.strftime("%d/%m/%Y")
                u["expirado"] = dt_exp < agora_utc
            else:
                u["data_expiracao_formatada"] = "Indefinida"
                u["expirado"] = False

            dt_cria = u.get("criado_em") or u.get("created_at")
            dt_cria_utc = parse_expiration_datetime_utc(dt_cria)
            if dt_cria_utc:
                u["data_criacao_formatada"] = dt_cria_utc.strftime("%d/%m/%Y %H:%M")
            else:
                u["data_criacao_formatada"] = str(dt_cria or "-")[:16]

            usuarios_map[email_v] = u

    return list(usuarios_map.values())


async def autenticar_usuario_supabase(email: str, senha: str) -> tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Autentica um usuário cadastrado:
    1. Normaliza e-mail com .strip().lower() e senha com .strip()
    2. Consulta o Supabase (se configurado) ou armazenamento local
    3. Valida se a senha corresponde ao campo salvo (senha, senha_plana, password, senha_hash)
    4. Verifica se a conta está ativa e se data_expiracao não expirou em UTC padronizado
    """
    email_limpo = (email or "").strip().lower()
    senha_limpa = (senha or "").strip()

    if not email_limpo or not senha_limpa:
        return False, "Por favor, preencha o e-mail e a senha.", None

    # 1. Consulta no Supabase se configurado
    if is_supabase_configured():
        url, key = get_supabase_config()
        headers = get_supabase_headers(key)
        filtros = [f"email=ilike.{email_limpo}", f"email=eq.{email_limpo}"]
        for filtro in filtros:
            rest_url = f"{url}/rest/v1/{TABLE_NAME}?{filtro}&select=*"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(rest_url, headers=headers)
                    if resp.status_code == 200:
                        usuarios = resp.json()
                        if usuarios and isinstance(usuarios, list) and len(usuarios) > 0:
                            user_data = usuarios[0]
                            senha_salva = str(
                                user_data.get("senha") or 
                                user_data.get("senha_plana") or 
                                user_data.get("password") or 
                                user_data.get("senha_hash") or 
                                ""
                            ).strip()

                            if senha_salva and senha_limpa == senha_salva:
                                # Validação unificada de expiração e status ativo
                                ativo, motivo, _ = usuario_esta_ativo_e_valido(user_data)
                                if not ativo:
                                    return False, motivo, user_data

                                return True, "Login realizado com sucesso.", user_data
                            else:
                                return False, "E-mail ou senha incorretos.", None
            except Exception as e:
                print(f"[Supabase Login] Exceção na requisição Supabase: {e}")

    # 2. Fallback para Armazenamento Local (_USUARIOS_LOCAIS)
    _carregar_usuarios_locais()
    user_local = None
    for k, v in _USUARIOS_LOCAIS.items():
        if (str(k).strip().lower() == email_limpo or 
            str(v.get("email", "")).strip().lower() == email_limpo):
            user_local = v
            break

    if user_local:
        senha_salva = str(
            user_local.get("senha") or 
            user_local.get("senha_plana") or 
            user_local.get("password") or 
            ""
        ).strip()

        if senha_salva and senha_limpa == senha_salva:
            ativo, motivo, _ = usuario_esta_ativo_e_valido(user_local)
            if not ativo:
                return False, motivo, user_local

            return True, "Login realizado com sucesso.", user_local
        else:
            return False, "E-mail ou senha incorretos.", None

    return False, "E-mail ou senha incorretos.", None


async def verificar_usuario_ativo(
    email: str,
    forcar_atualizacao: bool = False
) -> tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Verifica se um usuário com o e-mail informado existe e está com a assinatura/período de acesso ativo.
    Utiliza cache em memória de 30 segundos para otimizar chamadas sucessivas sem sobrecarregar a API REST.
    Retorna (ativo: bool, mensagem: str, dados_usuario: Optional[Dict]).
    """
    email_limpo = (email or "").strip().lower()
    if not email_limpo:
        return False, "E-mail não fornecido.", None

    # Checa cache em memória
    agora_ts = time.time()
    if not forcar_atualizacao and email_limpo in _CACHE_STATUS_USUARIOS:
        cached_ts, cached_ativo, cached_motivo, cached_data = _CACHE_STATUS_USUARIOS[email_limpo]
        if agora_ts - cached_ts < CACHE_TTL_SEGUNDOS:
            return cached_ativo, cached_motivo, cached_data

    # 1. Consulta no Supabase se configurado
    if is_supabase_configured():
        url, key = get_supabase_config()
        headers = get_supabase_headers(key)
        for filtro in [f"email=ilike.{email_limpo}", f"email=eq.{email_limpo}"]:
            rest_url = f"{url}/rest/v1/{TABLE_NAME}?{filtro}&select=*"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(rest_url, headers=headers)
                    if resp.status_code == 200:
                        usuarios = resp.json()
                        if usuarios and isinstance(usuarios, list) and len(usuarios) > 0:
                            user_data = usuarios[0]
                            ativo, motivo, _ = usuario_esta_ativo_e_valido(user_data)
                            _CACHE_STATUS_USUARIOS[email_limpo] = (agora_ts, ativo, motivo, user_data)
                            return ativo, motivo, user_data
            except Exception as e:
                print(f"[Supabase] Erro ao verificar usuário ativo no Supabase: {e}")

    # 2. Fallback no Armazenamento Local (_USUARIOS_LOCAIS)
    _carregar_usuarios_locais()
    user_local = None
    for k, v in _USUARIOS_LOCAIS.items():
        if (str(k).strip().lower() == email_limpo or 
            str(v.get("email", "")).strip().lower() == email_limpo):
            user_local = v
            break

    if user_local:
        ativo, motivo, _ = usuario_esta_ativo_e_valido(user_local)
        _CACHE_STATUS_USUARIOS[email_limpo] = (agora_ts, ativo, motivo, user_local)
        return ativo, motivo, user_local

    resultado = (False, "Usuário não encontrado.", None)
    _CACHE_STATUS_USUARIOS[email_limpo] = (agora_ts, False, "Usuário não encontrado.", None)
    return resultado
