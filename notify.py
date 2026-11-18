"""Avisos. Hoje: gera links "clique para conversar" do WhatsApp (você só aperta enviar).
No futuro: troque `send()` por uma integração (WhatsApp Cloud API, Evolution API, ntfy.sh, etc.).
Cada mensagem fica registrada na tabela `outbox`."""
import re, urllib.parse

# DDDs válidos no Brasil (Anatel)
DDDS = {11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35, 37, 38,
        41, 42, 43, 44, 45, 46, 47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68, 69,
        71, 73, 74, 75, 77, 79, 81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 92, 93, 94, 95, 96, 97, 98, 99}


def br_mobile(phone):
    """Celular brasileiro válido para WhatsApp -> '(DD) 9XXXX-XXXX'; senão None.
    Aceita com ou sem +55, espaços, parênteses e traços."""
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 13 and d.startswith("55"):
        d = d[2:]
    if len(d) != 11 or int(d[:2]) not in DDDS or d[2] != "9":
        return None
    return f"({d[:2]}) {d[2:7]}-{d[7:]}"


def clean_phone(phone):
    d = re.sub(r"\D", "", phone or "")
    # 10/11 dígitos = DDD + número (sem o país): acrescenta 55, mesmo se o DDD for 55 (RS)
    if len(d) in (10, 11):
        d = "55" + d
    return d

def whatsapp_link(phone, text):
    d = clean_phone(phone)
    if not d:
        return ""
    return f"https://wa.me/{d}?text={urllib.parse.quote(text)}"

def send(conn, person_id, text):
    """PONTO DE INTEGRAÇÃO FUTURA: aqui entra o envio automático."""
    conn.execute("INSERT INTO outbox(person_id,text) VALUES(?,?)", (person_id, text))
    conn.commit()
