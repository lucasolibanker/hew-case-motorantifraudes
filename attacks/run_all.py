"""Roda a Parte 3 e a Parte 4 em sequência. Cada script zera o laboratório."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    "double_charge.py",
    "webhook_replay.py",
    "webhook_tamper.py",
    "card_testing.py",
    "idempotency_race.py",
    "challenge_abuse.py",
    "velocity_shard.py",
    "forged_signals.py",
    "zscore_outlier.py",
]


def main() -> int:
    for name in SCRIPTS:
        path = Path(__file__).resolve().parent / name
        print(f"\n########## {name} ##########", flush=True)
        completed = subprocess.run([sys.executable, str(path)], cwd=ROOT)
        if completed.returncode != 0:
            print(f"{name} falhou com código {completed.returncode}")
            return completed.returncode
    print("\ntodos os scripts passaram")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
