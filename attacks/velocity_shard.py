"""Parte 4. O mesmo cartão em vários IPs.

O mesmo cartão, valor normal, um IP e um e-mail novos a cada request.
Sem o controle: cada chave fica em 1, abaixo do limite, tudo aprova.
Com o controle: o fingerprint do cartão é global. Trocar IP não zera a conta.
"""

import lib


def run(naive: bool) -> None:
    limit = int(lib.rules()["velocity"]["max_attempts_per_card"])
    total = limit + 2
    card = lib.pan("510510")
    decisions = []
    label = "sem controle" if naive else "com controle"
    for index in range(1, total + 1):
        body = lib.payment_body(
            card=card,
            bin="510510",
            customer_id="cust_shard",
            email=f"shard{index}@example.com",
            ip=f"192.0.2.{index}",
        )
        # 192.0.2.0/24 é documentação (TEST-NET-1), não está na tabela e não
        # é rede privada. País desconhecido não dispara geo. O teste é o velocity.
        response = lib.post_payment(body, naive="velocity" if naive else None)
        lib.show(
            f"velocity {label} {index}/{total}",
            f"mesmo cartão, ip {body['ip']}, email {body['email']}",
            response,
        )
        if response.status_code != 200:
            raise SystemExit(1)
        decisions.append(response.json())
    if naive:
        if any(item["decision"] != "approve" for item in decisions):
            print("sem o controle, barrou uma tentativa que deveria passar")
            raise SystemExit(1)
        return
    if decisions[0]["decision"] != "approve":
        print("a primeira tentativa, com o controle, já não aprovou:", decisions[0])
        raise SystemExit(1)
    last = decisions[-1]
    if last["decision"] != "deny":
        print("a rajada, com o controle, não negou")
        raise SystemExit(1)
    if not any(item["rule"] == "velocity" for item in last["reasons"]):
        print("negou por outra regra:", last["reasons"])
        raise SystemExit(1)


lib.reset_lab()
run(naive=True)
lib.reset_lab()
run(naive=False)
print("\ndefesa: IP e e-mail novos não apagam a conta do cartão")
