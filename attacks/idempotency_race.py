"""Parte 4. Corrida na Idempotency-Key.

Ingênuo: várias threads passam do GET antes do SET e cada uma cobra.
Endurecido: SET NX, um dono só, os outros esperam a mesma resposta.
"""

import threading

import lib

THREADS = 5


def burst(naive: bool) -> None:
    key = "idem-corrida-0001"
    body = lib.payment_body(customer_id="cust_race", email="race@example.com")
    barrier = threading.Barrier(THREADS)
    results = []

    def worker() -> None:
        barrier.wait(timeout=5)
        results.append(lib.post_payment(body, key=key, naive="idempotency" if naive else None, timeout=30))

    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    label = "ingênuo" if naive else "endurecido"
    ids = set()
    for index, response in enumerate(results, start=1):
        lib.show(f"corrida {label} thread {index}", f"chave {key}", response)
        if response.status_code != 200:
            raise SystemExit(1)
        ids.add(response.json()["id"])
    charges = lib.charge_count(ids)
    print(f"ids distintos: {len(ids)} | cobranças no mock: {charges}")
    if naive:
        if len(ids) < 2 and charges < 2:
            print("a corrida ingênua não furou a idempotência")
            raise SystemExit(1)
    elif len(ids) != 1 or charges != 1:
        print("a versão endurecida deixou passar mais de uma cobrança")
        raise SystemExit(1)


lib.reset_lab()
burst(naive=True)
lib.reset_lab()
burst(naive=False)
print("\ndefesa: a mesma rajada, com SET NX, cobra uma vez")
