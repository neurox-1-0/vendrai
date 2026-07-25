from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, ParseError

import httpx
from defusedxml import ElementTree

from app.config import settings

ALLOWED_SOURCE_HOSTS = {
    "OFAC": {
        "sanctionslistservice.ofac.treas.gov",
        "wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com",
    },
    "UN": {
        "scsanctions.un.org",
        "main.un.org",
        "unsolprodfiles.blob.core.windows.net",
    },
    "EU": {
        "ec.europa.eu",
        "finance.ec.europa.eu",
        "webgate.ec.europa.eu",
    },
}


@dataclass(frozen=True)
class SanctionsRecord:
    external_id: str
    primary_name: str
    aliases: list[str]
    countries: list[str]


@dataclass(frozen=True)
class DownloadedDataset:
    payload: bytes
    sha256: str
    etag: str | None
    version: str


def configured_source_url(source: str) -> str:
    return {
        "OFAC": settings.SANCTIONS_OFAC_URL,
        "UN": settings.SANCTIONS_UN_URL,
        "EU": settings.SANCTIONS_EU_URL,
    }[source]


def validate_source_url(source: str, url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
        or parsed.hostname.lower() not in ALLOWED_SOURCE_HOSTS[source]
    ):
        raise ValueError("SANCTIONS_SOURCE_URL_NOT_APPROVED")


def approved_redirect_url(source: str, current_url: str, location: str) -> str:
    target = urljoin(current_url, location)
    validate_source_url(source, target)
    return target


async def download_official_dataset(source: str, url: str) -> DownloadedDataset:
    validate_source_url(source, url)
    payload = bytearray()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60, connect=10),
        follow_redirects=False,
    ) as client:
        current_url = url
        for _redirect_count in range(6):
            async with client.stream(
                "GET",
                current_url,
                headers={"Accept": "application/xml,text/xml"},
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("SANCTIONS_REDIRECT_LOCATION_MISSING")
                    current_url = approved_redirect_url(
                        source,
                        current_url,
                        location,
                    )
                    continue
                response.raise_for_status()
                declared_size = int(
                    response.headers.get("content-length", "0") or "0"
                )
                if declared_size > settings.SANCTIONS_DOWNLOAD_MAX_BYTES:
                    raise ValueError("SANCTIONS_DOWNLOAD_TOO_LARGE")
                async for chunk in response.aiter_bytes():
                    payload.extend(chunk)
                    if len(payload) > settings.SANCTIONS_DOWNLOAD_MAX_BYTES:
                        raise ValueError("SANCTIONS_DOWNLOAD_TOO_LARGE")
                etag = response.headers.get("etag")
                version = (
                    response.headers.get("last-modified")
                    or etag
                    or hashlib.sha256(payload).hexdigest()[:16]
                )
                break
        else:
            raise ValueError("SANCTIONS_REDIRECT_LIMIT_EXCEEDED")
    if not payload:
        raise ValueError("SANCTIONS_DOWNLOAD_EMPTY")
    return DownloadedDataset(
        payload=bytes(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        etag=etag,
        version=version[:80],
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].upper()


def _text(element: Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def _children(element: Element, name: str) -> list[Element]:
    wanted = name.upper()
    return [child for child in element.iter() if _local_name(child.tag) == wanted]


def _first(element: Element, *names: str) -> str:
    for name in names:
        nodes = _children(element, name)
        for node in nodes:
            value = _text(node)
            if value:
                return value
    return ""


def _unique(values: list[str], primary: str = "") -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = " ".join(value.split())
        key = cleaned.casefold()
        if cleaned and key not in seen and cleaned.casefold() != primary.casefold():
            seen.add(key)
            result.append(cleaned)
    return result


def _parse_ofac(root: Element) -> list[SanctionsRecord]:
    records: list[SanctionsRecord] = []
    for entry in _children(root, "sdnEntry"):
        external_id = _first(entry, "uid")
        first = _first(entry, "firstName")
        last = _first(entry, "lastName")
        primary = " ".join(part for part in (first, last) if part).strip()
        aliases = []
        for alias in _children(entry, "aka"):
            alias_first = _first(alias, "firstName")
            alias_last = _first(alias, "lastName")
            aliases.append(
                " ".join(part for part in (alias_first, alias_last) if part)
            )
        countries = [_text(node) for node in _children(entry, "country")]
        if external_id and primary:
            records.append(
                SanctionsRecord(
                    external_id=external_id,
                    primary_name=primary,
                    aliases=_unique(aliases, primary),
                    countries=_unique(countries),
                )
            )
    return records


def _parse_un(root: Element) -> list[SanctionsRecord]:
    records: list[SanctionsRecord] = []
    for entry_name in ("INDIVIDUAL", "ENTITY"):
        for entry in _children(root, entry_name):
            external_id = _first(entry, "REFERENCE_NUMBER", "DATAID")
            if entry_name == "INDIVIDUAL":
                primary = " ".join(
                    filter(
                        None,
                        (
                            _first(entry, "FIRST_NAME"),
                            _first(entry, "SECOND_NAME"),
                            _first(entry, "THIRD_NAME"),
                            _first(entry, "FOURTH_NAME"),
                        ),
                    )
                )
                alias_nodes = _children(entry, "INDIVIDUAL_ALIAS")
            else:
                primary = _first(entry, "FIRST_NAME")
                alias_nodes = _children(entry, "ENTITY_ALIAS")
            aliases = [_first(alias, "ALIAS_NAME") for alias in alias_nodes]
            countries = [
                _text(node)
                for name in ("NATIONALITY", "COUNTRY")
                for node in _children(entry, name)
            ]
            if external_id and primary:
                records.append(
                    SanctionsRecord(
                        external_id=external_id,
                        primary_name=primary,
                        aliases=_unique(aliases, primary),
                        countries=_unique(countries),
                    )
                )
    return records


def _parse_eu(root: Element) -> list[SanctionsRecord]:
    records: list[SanctionsRecord] = []
    for entry in _children(root, "sanctionsEntity"):
        external_id = (
            entry.attrib.get("logicalId")
            or entry.attrib.get("euReferenceNumber")
            or _first(entry, "logicalId", "euReferenceNumber")
        )
        names = []
        for alias in _children(entry, "nameAlias"):
            names.append(
                alias.attrib.get("wholeName")
                or _first(alias, "wholeName", "firstName", "name")
            )
        primary = next((name for name in names if name), "")
        countries = []
        for node_name in ("citizenship", "address"):
            for node in _children(entry, node_name):
                countries.append(
                    node.attrib.get("countryDescription")
                    or node.attrib.get("countryIso2Code")
                    or _first(node, "countryDescription", "countryIso2Code")
                )
        if external_id and primary:
            records.append(
                SanctionsRecord(
                    external_id=external_id,
                    primary_name=primary,
                    aliases=_unique(names[1:], primary),
                    countries=_unique(countries),
                )
            )
    return records


def parse_official_dataset(source: str, payload: bytes) -> list[SanctionsRecord]:
    if b"<!DOCTYPE" in payload[:4096].upper():
        raise ValueError("SANCTIONS_XML_DOCTYPE_FORBIDDEN")
    try:
        root = ElementTree.fromstring(payload)
    except ParseError as exc:
        raise ValueError("SANCTIONS_XML_INVALID") from exc
    records = {
        "OFAC": _parse_ofac,
        "UN": _parse_un,
        "EU": _parse_eu,
    }[source](root)
    if not records:
        raise ValueError("SANCTIONS_DATASET_EMPTY")
    external_ids = [record.external_id for record in records]
    if len(external_ids) != len(set(external_ids)):
        raise ValueError("SANCTIONS_EXTERNAL_ID_DUPLICATE")
    return records
