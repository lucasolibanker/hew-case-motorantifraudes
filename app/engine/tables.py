"""Tabelas locais de BIN, IP e e-mail descartável.

Não há chamada externa. O laboratório precisa funcionar offline, e um
enriquecimento de IP em tempo de request seria outro ponto de falha e
outro lugar para o cliente mentir (se a gente mandasse o IP que ele digitou).
"""

from __future__ import annotations

import csv
import ipaddress
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Tables:
    bins: dict[str, str]
    ips: dict[str, str]
    disposable: set[str]
    local_country: str

    def country_for_bin(self, bin6: str) -> str | None:
        return self.bins.get(bin6)

    def country_for_ip(self, ip: str) -> str | None:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return None
        # Loopback e rede privada (o gateway do Docker, a máquina local)
        # não estão num GeoIP público. No laboratório eles valem o país
        # configurado, para um pagamento honesto feito daqui não nascer
        # em challenge. Em produção isto seria o GeoIP do IP do socket,
        # e a rede do proxy só entraria se o hop fosse confiável.
        if addr.is_loopback or addr.is_private:
            return self.local_country
        return self.ips.get(ip)

    def is_disposable(self, email: str) -> bool:
        domain = email.rsplit("@", 1)[-1].lower()
        return domain in self.disposable


def load_tables(
    bins_path: str,
    ips_path: str,
    disposable_path: str,
    local_country: str,
) -> Tables:
    return Tables(
        bins=_read_map(bins_path, "bin", "country"),
        ips=_read_map(ips_path, "ip", "country"),
        disposable=_read_domains(disposable_path),
        local_country=local_country.upper(),
    )


def _read_map(path: str, key_col: str, value_col: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            mapping[row[key_col].strip()] = row[value_col].strip().upper()
    return mapping


def _read_domains(path: str) -> set[str]:
    domains: set[str] = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        cleaned = line.split("#", 1)[0].strip().lower()
        if cleaned:
            domains.add(cleaned)
    return domains
