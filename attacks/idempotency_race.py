"""Parte 4. Duas requisições ao mesmo tempo, mesma Idempotency-Key.

Sem a trava: várias threads passam do GET antes do SET e cada uma cobra.
Com a trava: SET NX, um dono só, os outros esperam a mesma resposta.
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

    label = "sem trava" if naive else "com trava"
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
            print("sem a trava, as duas requisições não furaram a idempotência")
            raise SystemExit(1)
    elif len(ids) != 1 or charges != 1:
        print("com a trava, passou mais de uma cobrança")
        raise SystemExit(1)


lib.reset_lab()
burst(naive=True)
lib.reset_lab()
burst(naive=False)
print("\ndefesa: a mesma rajada, com SET NX, cobra uma vez")
