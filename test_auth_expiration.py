import asyncio
from datetime import datetime, timedelta, timezone, date
from fastapi.testclient import TestClient
from main import app
import auth_service
import supabase_service

client = TestClient(app)

def test_utc_timezone_boundary():
    print("=== TESTE A: Consistência de Fuso Horário e Limites UTC ===")
    agora_utc = datetime.now(timezone.utc)
    
    # 1. Conta vencida há 1 segundo -> deve acusar expirado
    dt_passado = agora_utc - timedelta(seconds=1)
    parsed_passado = supabase_service.parse_expiration_datetime_utc(dt_passado.isoformat())
    assert parsed_passado is not None
    assert parsed_passado.tzinfo == timezone.utc
    assert parsed_passado < agora_utc, "Deveria acusar expirado para 1 segundo atrás"

    # 2. Conta com validade futura de 10 segundos -> ativa
    dt_futuro = agora_utc + timedelta(seconds=10)
    parsed_futuro = supabase_service.parse_expiration_datetime_utc(dt_futuro.isoformat())
    assert parsed_futuro is not None
    assert parsed_futuro > agora_utc, "Deveria acusar ativo para 10 segundos à frente"

    # 3. String de data pura YYYY-MM-DD -> deve ser calibrada para 23:59:59 UTC
    hoje_str = agora_utc.strftime("%Y-%m-%d")
    parsed_hoje = supabase_service.parse_expiration_datetime_utc(hoje_str)
    assert parsed_hoje.hour == 23 and parsed_hoje.minute == 59 and parsed_hoje.second == 59
    assert parsed_hoje.tzinfo == timezone.utc
    print("✓ Validação rigorosa de UTC (TIMESTAMPTZ) e limite de fim de dia 23:59:59 UTC aprovada.")


def test_column_aliases():
    print("\n=== TESTE B: Suporte a Múltiplos Nomes de Coluna do Supabase ===")
    agora_utc = datetime.now(timezone.utc)
    data_futura = (agora_utc + timedelta(days=30)).isoformat()
    data_passada = (agora_utc - timedelta(days=2)).isoformat()

    aliases = ["data_expiracao", "validade", "expira_em", "expires_at", "expiration_date"]
    for alias in aliases:
        user_valido = {"email": f"teste_{alias}@antik.com.br", alias: data_futura}
        ativo, motivo, _ = supabase_service.usuario_esta_ativo_e_valido(user_valido)
        assert ativo is True, f"Falha no alias {alias} válido: {motivo}"

        user_expirado = {"email": f"teste_{alias}_exp@antik.com.br", alias: data_passada}
        ativo_exp, motivo_exp, _ = supabase_service.usuario_esta_ativo_e_valido(user_expirado)
        assert ativo_exp is False, f"Falha no alias {alias} expirado: {motivo_exp}"
        assert "expirado" in motivo_exp.lower()

    print("✓ Suporte pleno e verificado para todos os nomes de coluna de expiração do Supabase.")


def test_status_flags():
    print("\n=== TESTE C: Bloqueio por Flags Administrativas (ativo=False, status='inativo') ===")
    agora_utc = datetime.now(timezone.utc)
    data_futura = (agora_utc + timedelta(days=30)).isoformat()

    # Usuário com data futura mas ativo = False
    u_inativo = {"email": "desativado@antik.com.br", "data_expiracao": data_futura, "ativo": False}
    ativo, motivo, _ = supabase_service.usuario_esta_ativo_e_valido(u_inativo)
    assert ativo is False
    assert "desativada" in motivo.lower()

    # Usuário com data futura mas status = 'bloqueado'
    u_bloq = {"email": "bloqueado@antik.com.br", "data_expiracao": data_futura, "status": "bloqueado"}
    ativo_b, motivo_b, _ = supabase_service.usuario_esta_ativo_e_valido(u_bloq)
    assert ativo_b is False
    assert "suspensa" in motivo_b.lower() or "inativa" in motivo_b.lower()
    print("✓ Flags de status ('ativo', 'status') respeitadas com bloqueio imediato.")


def test_realtime_cache_and_expiration():
    print("\n=== TESTE D: Invalidação de Cache e Verificação em Tempo Real ===")
    email = "tempo_real@antik.com.br"
    agora_utc = datetime.now(timezone.utc)
    
    # 1. Cria usuário ativo
    supabase_service._USUARIOS_LOCAIS[email] = {
        "id": email,
        "email": email,
        "senha": "SenhaValida1",
        "data_expiracao": (agora_utc + timedelta(days=5)).isoformat()
    }
    supabase_service._salvar_usuarios_locais()
    supabase_service._limpar_cache_usuario(email)

    ativo, _, _ = asyncio.run(supabase_service.verificar_usuario_ativo(email))
    assert ativo is True

    # 2. Atualiza para expirado e verifica se cache ou checagem reflete
    supabase_service._USUARIOS_LOCAIS[email]["data_expiracao"] = (agora_utc - timedelta(days=1)).isoformat()
    supabase_service._salvar_usuarios_locais()
    supabase_service._limpar_cache_usuario(email)

    ativo_apos, motivo_apos, _ = asyncio.run(supabase_service.verificar_usuario_ativo(email))
    assert ativo_apos is False
    assert "expirado" in motivo_apos.lower()
    print("✓ Invalidação e renovação de cache em tempo real operando com perfeição.")


if __name__ == "__main__":
    test_utc_timezone_boundary()
    test_column_aliases()
    test_status_flags()
    test_realtime_cache_and_expiration()
    print("\n=======================================================")
    print("  SUÍTE DE SEGURANÇA E TIMESTAMPTZ CONCLUÍDA COM 100%! ")
    print("=======================================================")
