"""Parte 4. Sinais forjados.

O cliente manda país US, IP americano e BIN 400000, mas o socket está no
laboratório (tratado como BR) e o PAN realmente começa com 400000.

Ingênuo: acredita no país do JSON e aprova.
Endurecido: ignora país e IP do JSON, deriva o BIN do PAN, vê BR contra US
e desafia. Um segundo caso faz o mesmo com e-mail descartável.
"""

import lib


def once(title: str, body: dict, naive: bool) -> dict:
    response = lib.post_payment(body, naive="signals" if naive else None)
    lib.show(title, f"country={body.get('country')} ip={body['ip']} email={body['email']} bin={body['bin']}", response)
    if response.status_code != 200:
        raise SystemExit(1)
    return response.json()


lib.reset_lab()
geo_body = lib.payment_body(
    card=lib.pan("400000"),
    bin="400000",
    customer_id="cust_forge_geo",
    email="forge@example.com",
    ip="198.51.100.8",
    country="US",
)
naive_geo = once("geo ingênuo", geo_body, naive=True)
if naive_geo["decision"] != "approve":
    print("o modo ingênuo não acreditou no país forjado")
    raise SystemExit(1)

lib.reset_lab()
geo_body["card"] = lib.pan("400000")
hardened_geo = once("geo endurecido", geo_body, naive=False)
if hardened_geo["decision"] != "challenge":
    print("o modo endurecido não desafiou o BIN americano")
    raise SystemExit(1)
if not any(item["rule"] == "geo_bin" for item in hardened_geo["reasons"]):
    print(hardened_geo["reasons"])
    raise SystemExit(1)

lib.reset_lab()
mail_body = lib.payment_body(
    card=lib.pan("411111"),
    bin="411111",
    customer_id="cust_forge_mail",
    email="pessoa@mailinator.com",
    ip="203.0.113.10",
)
naive_mail = once("e-mail ingênuo", mail_body, naive=True)
if naive_mail["decision"] != "approve":
    print("o modo ingênuo pontuou o e-mail descartável")
    raise SystemExit(1)

lib.reset_lab()
mail_body["card"] = lib.pan("411111")
hardened_mail = once("e-mail endurecido", mail_body, naive=False)
if hardened_mail["decision"] != "challenge":
    print("o modo endurecido não desafiou o descartável")
    raise SystemExit(1)
print("\ndefesa: país, IP e e-mail do JSON não são observação")
