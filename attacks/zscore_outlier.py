"""Z-score. Cinco valores parecidos e um muito fora.

Com menos de 5 tentativas anteriores o peso é zero (cold start).
Na sexta, o desvio estoura e a decisão vai para challenge, com a regra
zscore em reasons. Sozinha ela não nega: o teto dela está na faixa do meio.
"""

import lib

lib.reset_lab()
customer = "cust_zscore"
card = lib.pan("411111")
warm = ["100.00", "110.00", "90.00", "105.00", "95.00"]
for index, amount in enumerate(warm, start=1):
    response = lib.post_payment(
        lib.payment_body(
            amount=amount,
            card=card,
            bin="411111",
            customer_id=customer,
            email="zscore@example.com",
        )
    )
    lib.show(f"histórico {index}", f"amount {amount}", response)
    if response.status_code != 200 or response.json()["decision"] != "approve":
        raise SystemExit(1)

outlier = lib.post_payment(
    lib.payment_body(
        amount="10000.00",
        card=card,
        bin="411111",
        customer_id=customer,
        email="zscore@example.com",
    )
)
lib.show("outlier", "amount 10000.00 depois de cinco compras perto de 100", outlier)
if outlier.status_code != 200 or outlier.json()["decision"] != "challenge":
    print("esperava challenge")
    raise SystemExit(1)
if not any(item["rule"] == "zscore" for item in outlier.json()["reasons"]):
    print(outlier.json()["reasons"])
    raise SystemExit(1)
print("\nz-score entrou no score com cold start respeitado nas cinco primeiras")
