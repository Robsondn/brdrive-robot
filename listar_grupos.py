"""
Lista todos os grupos onde o bot está adicionado.
Rode após adicionar o bot nos grupos do Feishu.
"""

import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

APP_ID     = os.getenv("FEISHU_APP_ID",     "")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
BASE_URL   = "https://open.feishu.cn/open-apis"


def get_token():
    resp = requests.post(f"{BASE_URL}/auth/v3/tenant_access_token/internal",
                         json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
    return resp.json()["tenant_access_token"]


def listar_grupos():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/im/v1/chats?page_size=50", headers=headers, timeout=10)
    data = resp.json()

    if data.get("code") != 0:
        print(f"❌ Erro: {data}")
        return

    grupos = data.get("data", {}).get("items", [])
    if not grupos:
        print("⚠️  Nenhum grupo encontrado. Verifique se o bot foi adicionado nos grupos.")
        return

    print(f"\n{'='*60}")
    print(f"  Grupos onde o bot está ({len(grupos)} encontrado(s))")
    print(f"{'='*60}")
    for g in grupos:
        print(f"\n  Nome:    {g.get('name', '—')}")
        print(f"  Chat ID: {g.get('chat_id', '—')}")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    listar_grupos()
