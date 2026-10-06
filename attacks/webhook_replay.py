"""Parte 3. Reenviar o webhook que o mock já assinou.

A primeira entrega (a do mock, ou a nossa se ela ganhar a corrida) pode
capturar. A segunda, com os mesmos bytes, leva 409.
"""

import httpx

import lib

lib.reset_lab()
created = lib.post_payment(lib.payment_body(customer_id="cust_replay"))
lib.show("pagamento que o PSP vai confirmar", "approve esperado", created)
if created.status_code != 200 or created.json()["decision"] != "approve":
    raise SystemExit(1)
payment_id = created.json()["id"]
sent = lib.wait_webhook(payment_id)
print(f"webhook original event body={sent['body']}")

def resend() -> httpx.Response:
    return httpx.post(
        f"{lib.API}/webhooks/psp",
        content=sent["body"].encode(),
        headers={
            "Content-Type": "application/json",
            "X-PSP-Timestamp": sent["timestamp"],
            "X-PSP-Signature": sent["signature"],
        },
        timeout=10,
    )

first = resend()
lib.show("reenvio 1", "os mesmos bytes assinados", first)
second = resend()
lib.show("reenvio 2", "os mesmos bytes de novo", second)
if second.status_code != 409:
    print("o replay não foi rejeitado")
    raise SystemExit(1)
print("\ndefesa: o segundo webhook idêntico foi rejeitado")
