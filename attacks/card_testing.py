"""Parte 3. Card testing: vários cartões, valor baixo, mesmo IP.

No fresco, as primeiras passam. Quando o BIN junta cartões demais (e o
valor baixo se acumula), a resposta vira deny. O velocity por IP entra
junto se a rajada passar de 5 cartões distintos.
"""

import lib

lib.reset_lab()
limit = int(lib.rules()["card_testing"]["max_distinct_cards_per_bin"])
total = limit + 2
denied = False
for index in range(1, total + 1):
    body = lib.payment_body(
        amount="1.00",
        card=lib.pan("411111"),
        bin="411111",
        customer_id="cust_card_test",
        email=f"card{index}@example.com",
    )
    response = lib.post_payment(body)
    lib.show(f"card testing {index}/{total}", f"valor 1.00 cartão novo BIN 411111", response)
    if response.status_code != 200:
        raise SystemExit(1)
    decision = response.json()["decision"]
    if decision == "deny":
        denied = True
        names = {item["rule"] for item in response.json()["reasons"]}
        if "card_testing" not in names and "velocity" not in names:
            print("negou sem a regra esperada:", response.text)
            raise SystemExit(1)

if not denied:
    print("a rajada inteira passou; o gatilho não disparou")
    raise SystemExit(1)
print("\ndefesa: a rajada passou a ser negada")
