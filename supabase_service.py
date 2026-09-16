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
                # Formata datas para exibição amigável
                hoje = date.today()
                for u in usuarios:
                    # Data de expiração
                    dt_exp = u.get("data_expiracao")
                    if dt_exp:
                        try:
                            # Trata YYYY-MM-DD ou ISO
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
                # Caso a coluna criado_em não exista, tenta sem ordenação específica
                rest_url_fallback = f"{url}/rest/v1/{TABLE_NAME}?select=*"
                resp_fb = await client.get(rest_url_fallback, headers=headers)
                if resp_fb.status_code == 200:
                    return resp_fb.json()
    except Exception as e:
        print(f"[Supabase] Erro ao listar usuários: {e}")
        return []

    return []
