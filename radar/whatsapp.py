import json
import os
import re
import urllib.error
import urllib.request


def enabled():
    return os.getenv("RADAR_MODO_WHATSAPP") == "1"


def configuration():
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "")
    recipient = os.getenv("WHATSAPP_DESTINO", "").removeprefix("+")
    token = os.getenv("WHATSAPP_TOKEN", "")
    template = os.getenv("WHATSAPP_MODELO", "radar_shopee_diario")
    version = os.getenv("WHATSAPP_GRAPH_VERSION", "v27.0")
    if not (re.fullmatch(r"[0-9]+", phone_id) and re.fullmatch(r"[1-9][0-9]{7,14}", recipient)
            and token and not any(char.isspace() for char in token)
            and re.fullmatch(r"[a-z0-9_]+", template) and re.fullmatch(r"v[0-9]+\.[0-9]+", version)):
        raise ValueError("Complete a configuração do WhatsApp no arquivo .env e reinicie o Radar.")
    return phone_id, recipient, token, template, version


def send(links):
    phone_id, recipient, token, template, version = configuration()
    if len(links) != 3:
        raise ValueError("O modelo do WhatsApp precisa de três links.")
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": "pt_BR"},
            "components": [{"type": "body", "parameters": [
                {"type": "text", "text": link} for link in links
            ]}],
        },
    }
    request = urllib.request.Request(
        f"https://graph.facebook.com/{version}/{phone_id}/messages",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            message_id = json.load(response)["messages"][0]["id"]
        if not isinstance(message_id, str) or not message_id:
            raise ValueError()
        return message_id
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"A Meta respondeu com HTTP {error.code}. Confira o token, o remetente e o modelo aprovado.") from None
    except (OSError, ValueError, TypeError, IndexError, KeyError):
        raise RuntimeError("A Meta não confirmou o envio. Confira o WhatsApp antes de tentar novamente.") from None
