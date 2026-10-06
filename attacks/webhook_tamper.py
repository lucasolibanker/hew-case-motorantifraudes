"""Parte 3. Trocar o amount e guardar a assinatura antiga.

O MAC é do corpo cru. Um dígito a mais no amount_cents muda os bytes e a
assinatura deixa de bater. A resposta é 401, a mesma de um timestamp velho,
para não contar ao atacante qual checagem falhou.
"""

import re

import httpx

import lib

lib.reset_lab()
created = lib.post_payment(lib.payment_body(customer_id="cust_tamper"))
lib.show("pagamento legítimo", "approve esperado", created)
if created.status_code != 200 or created.json()["decision"] != "approve":
    raise SystemExit(1)
sent = lib.wait_webhook(created.json()["id"])
original = sent["body"].encode()
if b'"amount_cents":' not in original:
    print("corpo inesperado:", sent["body"])
    raise SystemExit(1)
tampered = re.sub(br'"amount_cents":\d+', b'"amount_cents":1', original, count=1)
print(f"corpo original: {original.decode()}")
print(f"corpo alterado: {tampered.decode()}")
response = httpx.post(
    f"{lib.API}/webhooks/psp",
    content=tampered,
    headers={
        "Content-Type": "application/json",
        "X-PSP-Timestamp": sent["timestamp"],
        "X-PSP-Signature": sent["signature"],
    },
    timeout=10,
)
lib.show("tamper", "amount alterado, assinatura antiga", response)
if response.status_code != 401:
    print("o corpo alterado não foi rejeitado")
    raise SystemExit(1)
print("\ndefesa: assinatura antiga não valida o corpo novo")
