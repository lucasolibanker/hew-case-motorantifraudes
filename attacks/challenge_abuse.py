"""Parte 4. Abuso do challenge.

O score médio (BIN dos EUA visto do laboratório, que conta como BR) cai
em challenge. Com o controle desligado, qualquer código aprova, e repetir cobra de
novo. Com o controle ligado, o código errado leva 401, o certo funciona uma vez,
e a repetição leva 409.
"""

import lib


def challenged(tag: str) -> dict:
    body = lib.payment_body(
        card=lib.pan("400000"),
        bin="400000",
        customer_id=f"cust_ch_{tag}",
        email=f"{tag}@example.com",
        ip="198.51.100.8",
    )
    response = lib.post_payment(body)
    lib.show(f"pagamento {tag}", "BIN 400000 (US) a partir do laboratório (BR)", response)
    if response.status_code != 200 or response.json()["decision"] != "challenge":
        print("esperava challenge")
        raise SystemExit(1)
    return response.json()


lib.reset_lab()
naive_payment = challenged("naive")
wrong = lib.post_json(
    f"/payments/{naive_payment['id']}/verify",
    {"code": "000000"},
    headers={"X-Naive-Controls": "challenge"},
)
lib.show("verify sem controle", "código 000000, que não é o OTP", wrong)
if wrong.status_code != 200:
    raise SystemExit(1)
again = lib.post_json(
    f"/payments/{naive_payment['id']}/verify",
    {"code": "000000"},
    headers={"X-Naive-Controls": "challenge"},
)
lib.show("verify sem controle de novo", "mesmo código, segunda cobrança", again)
if again.status_code != 200:
    raise SystemExit(1)
naive_charges = lib.charge_count({naive_payment["id"]})
print(f"cobranças com o controle desligado: {naive_charges}")
if naive_charges < 2:
    print("com o controle desligado, não cobrou duas vezes")
    raise SystemExit(1)

fechado = challenged("fechado")
bad = lib.post_json(f"/payments/{fechado['id']}/verify", {"code": "000000"})
lib.show("verify com controle, código errado", "código 000000", bad)
if bad.status_code != 401:
    raise SystemExit(1)
otp = fechado.get("otp_demo")
if not otp:
    print("EXPOSE_OTP está desligado; o script precisa do otp_demo para a perna legítima")
    raise SystemExit(1)
good = lib.post_json(f"/payments/{fechado['id']}/verify", {"code": otp})
lib.show("verify com controle, código certo", "OTP emitido para este id", good)
if good.status_code != 200:
    raise SystemExit(1)
replay = lib.post_json(f"/payments/{fechado['id']}/verify", {"code": otp})
lib.show("verify com controle, repetido", "mesmo OTP outra vez", replay)
if replay.status_code != 409:
    raise SystemExit(1)
fechadas = lib.charge_count({fechado["id"]})
print(f"cobranças com o controle ligado: {fechadas}")
if fechadas != 1:
    raise SystemExit(1)
print("\ndefesa: OTP certo, uma vez, amarrado ao id")
