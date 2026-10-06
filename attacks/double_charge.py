"""Parte 3. Duas chamadas seguidas com a mesma Idempotency-Key.

A segunda devolve o mesmo id e o mock não vê uma segunda cobrança.
Isto é o caso sequencial. A corrida (as duas ao mesmo tempo) está na Parte 4.
"""

import lib

lib.reset_lab()
key = "idem-sequencial-0001"
body = lib.payment_body(customer_id="cust_idem")
first = lib.post_payment(body, key=key)
lib.show("primeira cobrança", f"Idempotency-Key {key}", first)
second = lib.post_payment(body, key=key)
lib.show("repetição sequencial", f"mesma chave {key}", second)
if first.status_code != 200 or second.status_code != 200:
    raise SystemExit(1)
if first.json()["id"] != second.json()["id"]:
    print("as duas respostas têm ids diferentes")
    raise SystemExit(1)
if first.json()["decision"] != "approve":
    print("o pagamento limpo não aprovou:", first.text)
    raise SystemExit(1)
count = lib.charge_count({first.json()["id"]})
print(f"cobranças no mock para esse id: {count}")
if count != 1:
    raise SystemExit(1)
print("\ndefesa: uma chave, uma cobrança")
