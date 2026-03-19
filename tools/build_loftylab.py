#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import mimetypes
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from lxml import html as lxml_html


BASE_URL = "https://loftylab.framer.website"
SITE_ID = "6b7njMavWjwSEoT8Enq0Pb"
ROUTES = [
    "/",
    "/about",
    "/works",
    "/contact",
    "/works/one-sip-at-a-time",
    "/works/glow-that-speaks-for-itself",
    "/works/riding-the-trend-wave",
    "/works/move-sweat-repeat",
    "/works/caffeine-made-shareable",
    "/works/taste-that-pops-on-camera",
    "/works/wear-the-energy",
    "/works/your-daily-dose-of-entertainment",
]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_ROOT = PROJECT_ROOT / "assets"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)

REMOTE_URL_RE = re.compile(r"https?://[^\s\"'<>`\\)]+")
RELATIVE_MODULE_RE = re.compile(
    r"""
    (?:from\s*["'](?P<from>[^"']+)["'])
    |
    (?:import\(\s*["'](?P<dynamic>[^"']+)["']\s*\))
    |
    (?:new\s+URL\(\s*["'](?P<newurl>[^"']+)["']\s*,\s*import\.meta\.url\s*\))
    |
    (?:url\(\s*["']?(?P<css>[^"'()]+)["']?\s*\))
    """,
    re.VERBOSE,
)

TEXT_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".mjs",
    ".svg",
    ".txt",
    ".xml",
}

RUNTIME_TEXT_REPLACEMENTS = {
    "siteCanonicalURL:`https://loftylab.framer.website`": "siteCanonicalURL:``",
    "import(`https://framer.com/edit/init.mjs`)": "import(`./edit-init-disabled.mjs`)",
    "e.url.startsWith(`https://fonts.gstatic.com/s/`)?`google`": "e.url.includes(`/assets/fonts/`)?`google`",
}

PAGE_URLS = {urljoin(BASE_URL, route.lstrip("/")) for route in ROUTES}
PAGE_PATHS = {route for route in ROUTES}


@dataclass
class PageRecord:
    remote_url: str
    route: str
    local_path: Path
    html_text: str


@dataclass
class AssetRecord:
    remote_url: str
    local_path: Path
    content_type: str
    raw_bytes: bytes

    @property
    def is_text(self) -> bool:
        suffix = self.local_path.suffix.lower()
        return (
            suffix in TEXT_EXTENSIONS
            or self.content_type.startswith("text/")
            or "javascript" in self.content_type
            or self.content_type.endswith("+xml")
            or self.content_type.endswith("/json")
        )

    def decode(self) -> str:
        charset = "utf-8"
        if "charset=" in self.content_type:
            charset = self.content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
        try:
            return self.raw_bytes.decode(charset)
        except UnicodeDecodeError:
            return self.raw_bytes.decode("utf-8", errors="replace")


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def cleanup_previous_build() -> None:
    for entry in PROJECT_ROOT.iterdir():
        if entry.name == ".git" or entry.name == "tools":
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return s


def normalize_remote_url(raw_url: str, *, base: str | None = None) -> str:
    url = html.unescape(raw_url.strip())
    if url.startswith("//"):
        url = "https:" + url
    if base is not None:
        url = urljoin(base, url)
    url, _fragment = urldefrag(url)
    return url


def route_to_local_path(route: str) -> Path:
    if route == "/":
        return PROJECT_ROOT / "index.html"
    clean = route.strip("/")
    return PROJECT_ROOT / clean / "index.html"


def route_to_public_path(route: str) -> str:
    if route == "/":
        return "./"
    return route.strip("/") + "/"


def build_internal_href(current_route: str, target_route: str) -> str:
    current_public = PurePosixPath(route_to_public_path(current_route))
    target_public = PurePosixPath(route_to_public_path(target_route))
    rel = os.path.relpath(str(target_public), start=str(current_public))
    normalized = rel.replace(os.sep, "/")
    if target_route == "/":
        return normalized if normalized.endswith("/") else normalized + "/"
    if not normalized.endswith("/"):
        normalized += "/"
    return normalized


def compute_asset_path(remote_url: str, content_type: str) -> Path:
    parsed = urlparse(remote_url)
    host = parsed.netloc
    path = parsed.path or "/asset"
    suffix = PurePosixPath(path).suffix

    if host == "vidplay.io" and path.startswith("/stream/"):
        stem = PurePosixPath(path).name or f"video-{short_hash(remote_url)}"
        return ASSETS_ROOT / "media" / f"{stem}.mp4"

    if not suffix:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) or ""
        suffix = guessed

    base_name = PurePosixPath(path).name or f"asset{suffix}"
    if suffix and not base_name.endswith(suffix):
        base_name += suffix

    stem = Path(base_name).stem or "asset"
    final_name = f"{stem}{suffix}" if suffix else stem
    if parsed.query:
        final_name = f"{stem}-{short_hash(remote_url)}{suffix}"

    if host == "framerusercontent.com":
        raw_parts = [segment for segment in path.split("/") if segment]
        if raw_parts[:1] == ["sites"] and len(raw_parts) >= 2:
            directory = ASSETS_ROOT / "framer" / "sites" / raw_parts[1]
        elif raw_parts:
            directory = ASSETS_ROOT / "framer" / raw_parts[0]
        else:
            directory = ASSETS_ROOT / "framer" / "misc"
    elif host == "fonts.gstatic.com":
        directory = ASSETS_ROOT / "fonts"
    else:
        directory = ASSETS_ROOT / "external" / host.replace(".", "-")

    directory.mkdir(parents=True, exist_ok=True)
    return directory / final_name


def extract_allowed_absolute_urls(text: str) -> set[str]:
    allowed: set[str] = set()
    for match in REMOTE_URL_RE.finditer(text):
        candidate = normalize_remote_url(match.group(0))
        parsed = urlparse(candidate)
        if parsed.netloc == "framerusercontent.com" and parsed.path not in {"", "/"}:
            allowed.add(candidate)
        elif parsed.netloc == "fonts.gstatic.com" and PurePosixPath(parsed.path).suffix in {
            ".otf",
            ".ttf",
            ".woff",
            ".woff2",
        }:
            allowed.add(candidate)
        elif parsed.netloc == "vidplay.io" and parsed.path.startswith("/stream/"):
            allowed.add(candidate)
    return allowed


def extract_relative_dependencies(text: str, base_url: str) -> set[str]:
    found: set[str] = set()
    for match in RELATIVE_MODULE_RE.finditer(text):
        candidate = next(group for group in match.groups() if group)
        if candidate.startswith(("data:", "mailto:", "tel:", "#")):
            continue
        if candidate.startswith(("http://", "https://", "//")):
            continue
        if candidate.startswith(("./", "../")):
            found.add(normalize_remote_url(candidate, base=base_url))
    return found


def fetch_pages(http: requests.Session) -> list[PageRecord]:
    pages: list[PageRecord] = []
    for route in ROUTES:
        remote_url = normalize_remote_url(route, base=BASE_URL)
        print(f"[page] {remote_url}", flush=True)
        response = http.get(remote_url, timeout=60)
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        pages.append(
            PageRecord(
                remote_url=remote_url,
                route=route,
                local_path=route_to_local_path(route),
                html_text=response.text,
            )
        )
    return pages


def discover_assets(http: requests.Session, pages: Iterable[PageRecord]) -> dict[str, AssetRecord]:
    queue: list[str] = []
    seen: set[str] = set()
    assets: dict[str, AssetRecord] = {}

    for page in pages:
        queue.extend(sorted(extract_allowed_absolute_urls(page.html_text)))

    while queue:
        remote_url = queue.pop(0)
        if remote_url in seen:
            continue
        seen.add(remote_url)

        if len(seen) % 20 == 1:
            print(f"[asset {len(seen)}] {remote_url}", flush=True)
        response = http.get(remote_url, timeout=120)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
        local_path = compute_asset_path(remote_url, content_type)
        record = AssetRecord(
            remote_url=remote_url,
            local_path=local_path,
            content_type=content_type,
            raw_bytes=response.content,
        )
        assets[remote_url] = record

        if record.is_text:
            text = record.decode()
            queue.extend(sorted(extract_allowed_absolute_urls(text)))
            queue.extend(sorted(extract_relative_dependencies(text, remote_url)))

    return assets


def replace_url_tokens(text: str, current_file: Path, target_map: dict[str, Path]) -> str:
    for remote_url, target_path in sorted(target_map.items(), key=lambda item: len(item[0]), reverse=True):
        relative = os.path.relpath(target_path, start=current_file.parent).replace(os.sep, "/")
        for source in {remote_url, remote_url.replace("&", "&amp;")}:
            text = text.replace(source, relative)
    return text


def postprocess_runtime_text(text: str) -> str:
    for source, replacement in RUNTIME_TEXT_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    return text


def prune_framer_nodes(doc: lxml_html.HtmlElement) -> None:
    xpaths = [
        "//script[contains(., 'framer.com/edit/init.mjs')]",
        "//script[starts-with(@src, 'https://events.framer.com/')]",
        "//*[@id='__framer-badge-container']",
        "//link[@rel='canonical']",
        "//link[@rel='preconnect' and contains(@href, 'fonts.gstatic.com')]",
        "//meta[@name='framer-search-index']",
        "//meta[@name='framer-search-index-fallback']",
        "//meta[@property='og:url']",
    ]
    for xpath in xpaths:
        for node in doc.xpath(xpath):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)


def rewrite_page(page: PageRecord, asset_map: dict[str, Path]) -> str:
    doc = lxml_html.fromstring(page.html_text)
    prune_framer_nodes(doc)

    for element in doc.xpath("//*[@href]"):
        href = element.get("href")
        if not href:
            continue

        normalized = normalize_remote_url(href, base=page.remote_url)
        parsed = urlparse(normalized)

        if href.startswith(("#", "mailto:", "tel:")):
            continue

        if parsed.netloc == "loftylab.framer.website" and parsed.path in PAGE_PATHS:
            element.set("href", build_internal_href(page.route, parsed.path or "/"))
            continue

        if href.startswith(("./", "../")):
            candidate = normalize_remote_url(href, base=page.remote_url)
            parsed_candidate = urlparse(candidate)
            if parsed_candidate.netloc == "loftylab.framer.website" and parsed_candidate.path in PAGE_PATHS:
                element.set("href", build_internal_href(page.route, parsed_candidate.path or "/"))

    rendered = lxml_html.tostring(
        doc,
        encoding="unicode",
        doctype="<!doctype html>",
        method="html",
    )
    return replace_url_tokens(rendered, page.local_path, asset_map)


def write_build(pages: Iterable[PageRecord], assets: dict[str, AssetRecord]) -> None:
    asset_path_map = {remote_url: record.local_path for remote_url, record in assets.items()}

    for page in pages:
        page.local_path.parent.mkdir(parents=True, exist_ok=True)
        page.local_path.write_text(rewrite_page(page, asset_path_map), encoding="utf-8")

    for record in assets.values():
        record.local_path.parent.mkdir(parents=True, exist_ok=True)
        if record.is_text:
            rewritten = replace_url_tokens(record.decode(), record.local_path, asset_path_map)
            rewritten = postprocess_runtime_text(rewritten)
            record.local_path.write_text(rewritten, encoding="utf-8")
        else:
            record.local_path.write_bytes(record.raw_bytes)

    site_bundle_dir = ASSETS_ROOT / "framer" / "sites" / SITE_ID
    if site_bundle_dir.exists():
        (site_bundle_dir / "edit-init-disabled.mjs").write_text(
            "export async function createEditorBar() { return () => null; }\n",
            encoding="utf-8",
        )

    (PROJECT_ROOT / ".nojekyll").write_text("", encoding="utf-8")
    home_page = PROJECT_ROOT / "index.html"
    if home_page.exists():
        shutil.copyfile(home_page, PROJECT_ROOT / "404.html")


def main() -> None:
    cleanup_previous_build()
    http = session()
    pages = fetch_pages(http)
    assets = discover_assets(http, pages)
    write_build(pages, assets)
    print(f"Built {len(pages)} pages and {len(assets)} local assets into {PROJECT_ROOT}")


if __name__ == "__main__":
    main()
