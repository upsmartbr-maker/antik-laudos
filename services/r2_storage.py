import os
from typing import Optional
import boto3
from botocore.config import Config
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()


def get_s3_client():
    """Retorna um cliente S3 configurado para o Cloudflare R2."""
    return boto3.client(
        's3',
        endpoint_url=os.getenv('R2_ENDPOINT_URL'),
        aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
        config=Config(signature_version='s3v4'),
        region_name='auto'
    )


def upload_laudo_r2(conteudo_html: str, codigo_ref: str) -> str:
    """
    Realiza o upload do HTML gerado para o bucket do Cloudflare R2.
    Retorna a URL pública do laudo armazenado.
    """
    s3 = get_s3_client()
    bucket = os.getenv('R2_BUCKET_NAME', 'antik-laudos')
    
    # Higieniza o código removendo caracteres inválidos para nomes de arquivos
    codigo_limpo = codigo_ref.strip().lstrip('#').replace('/', '-')
    key = f"laudos/{codigo_limpo}.html"
    
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=conteudo_html.encode('utf-8'),
        ContentType='text/html; charset=utf-8'
    )
    
    public_url = (os.getenv('R2_PUBLIC_URL') or '').rstrip('/')
    return f"{public_url}/{key}"


def verificar_laudo_existe(codigo_ref: str) -> bool:
    """Verifica no Cloudflare R2 se o laudo referente ao código especificado existe."""
    s3 = get_s3_client()
    bucket = os.getenv('R2_BUCKET_NAME', 'antik-laudos')
    
    codigo_limpo = codigo_ref.strip().lstrip('#').replace('/', '-')
    key = f"laudos/{codigo_limpo}.html"
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def obter_laudo_r2(codigo_ref: str) -> Optional[bytes]:
    """Obtém o conteúdo binário do laudo armazenado no R2."""
    s3 = get_s3_client()
    bucket = os.getenv('R2_BUCKET_NAME', 'antik-laudos')
    
    codigo_limpo = codigo_ref.strip().lstrip('#').replace('/', '-')
    key = f"laudos/{codigo_limpo}.html"
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        return response['Body'].read()
    except Exception:
        return None
