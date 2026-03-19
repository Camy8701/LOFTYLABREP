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
from urllib.parse import parse_qs, urljoin, urldefrag, urlparse

import requests
from lxml import html as lxml_html


BASE_URL = "https://loftylab.framer.website"
SITE_ID = "6b7njMavWjwSEoT8Enq0Pb"
BRAND_REPLACEMENTS = {
    "LOFTY LAB": "LYNCK Studio",
    "Lofty Lab": "LYNCK Studio",
    "loftylab@email.com": "lynckstudio@support.com",
    "loftylab@support.com": "lynckstudio@support.com",
}
LOGO_COMPONENT_RULE_OLD = (
    "`.framer-30Q4Y { -webkit-mask: ${w}; aspect-ratio: 2.3225806451612905; "
    "background-color: var(--token-0e3df59a-d2bd-4221-885a-76d4a23fa9fa, #030f2e); "
    "mask: ${w}; width: 72px; }`"
)
LOGO_COMPONENT_RULE_NEW = (
    "`.framer-30Q4Y { align-items: flex-start; display: flex; flex-direction: column; "
    "gap: 0px; height: 100%; justify-content: center; width: 100%; }`,"
    "`.framer-30Q4Y::before { content: \"LYNCK\"; color: "
    "var(--token-0e3df59a-d2bd-4221-885a-76d4a23fa9fa, #030f2e); font-family: "
    "\"Inter Display\", \"Inter Display Placeholder\", sans-serif; font-size: 14px; "
    "font-style: normal; font-weight: 900; letter-spacing: -0.08em; line-height: 0.82; "
    "text-transform: uppercase; }`,"
    "`.framer-30Q4Y::after { content: \"Studio\"; color: "
    "var(--token-0e3df59a-d2bd-4221-885a-76d4a23fa9fa, #030f2e); font-family: "
    "\"Inter Display\", \"Inter Display Placeholder\", sans-serif; font-size: 12px; "
    "font-style: normal; font-weight: 800; letter-spacing: -0.06em; line-height: 0.88; "
    "margin-top: -1px; text-transform: none; }`"
)
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
FRAMER_ASSET_REFERENCE_RE = re.compile(r"data:framer/asset-reference,(?P<asset>[^\s\"'<>`]+)")
RELATIVE_MODULE_RE = re.compile(
    r"""
    (?:from\s*["'`](?P<from>[^"'`]+)["'`])
    |
    (?:import\(\s*["'`](?P<dynamic>[^"'`]+)["'`]\s*\))
    |
    (?:new\s+URL\(\s*["'`](?P<newurl>[^"'`]+)["'`]\s*,\s*import\.meta\.url\s*\))
    |
    (?:url\(\s*["'`]?(?P<css>[^"'`()]+)["'`]?\s*\))
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

CMS_RANGE_RESPONSE_REPLACEMENTS = (
    (
        "let u=await o.arrayBuffer(),l=new Uint8Array(u);if(l.length!==i)throw Error(\"Request failed: Unexpected response length\");let h=new tT,c=0;for(let t of r){let e=t.to-t.from,r=c+e,n=l.subarray(c,r);h.write(t.from,n),c=r;}return e.map(t=>h.read(t.from,t.to-t.from));",
        "let u=await o.arrayBuffer(),l=new Uint8Array(u);if(l.length!==i){let n=r.reduce((t,e)=>Math.max(t,e.to),0);if(l.length<n)throw Error(\"Request failed: Unexpected response length\");return e.map(t=>l.slice(t.from,t.to));}let h=new tT,c=0;for(let t of r){let e=t.to-t.from,r=c+e,n=l.subarray(c,r);h.write(t.from,n),c=r;}return e.map(t=>h.read(t.from,t.to-t.from));",
    ),
    (
        "let c=await s.arrayBuffer(),l=new Uint8Array(c);if(l.length!==i)throw Error(`Request failed: Unexpected response length`);let u=new $e,d=0;for(let e of n){let t=e.to-e.from,n=d+t,r=l.subarray(d,n);u.write(e.from,r),d=n}return t.map(e=>u.read(e.from,e.to-e.from))",
        "let c=await s.arrayBuffer(),l=new Uint8Array(c);if(l.length!==i){let r=n.reduce((e,t)=>Math.max(e,t.to),0);if(l.length<r)throw Error(`Request failed: Unexpected response length`);return t.map(e=>l.slice(e.from,e.to))}let u=new $e,d=0;for(let e of n){let t=e.to-e.from,n=d+t,r=l.subarray(d,n);u.write(e.from,r),d=n}return t.map(e=>u.read(e.from,e.to-e.from))",
    ),
)

LOCAL_FRAMER_CMS_RELATIVE_BASE_RE = re.compile(
    r"""
    new\ URL\(
        (?P<asset>["'`]\./[^"'`]+\.framercms["'`])
        \s*,\s*
        (?P<base>["'`]\.\./[^"'`]+["'`])
    \)\.href\.replace\(
        ["'`]/modules/["'`]
        \s*,\s*
        ["'`]/cms/["'`]
    \)
    """,
    re.VERBOSE,
)

LOCAL_FRAMER_CMS_IMPORT_META_RE = re.compile(
    r"""
    new\ URL\(
        (?P<asset>["'`]\./[^"'`]+\.framercms["'`])
        \s*,\s*
        import\.meta\.url
    \)\.href\.replace\(
        ["'`]/modules/["'`]
        \s*,\s*
        ["'`]/cms/["'`]
    \)
    """,
    re.VERBOSE,
)

MODULE_IMAGE_SRC_RE = re.compile(
    r"(?P<key>\bsrc)\s*:\s*`(?P<path>\.\./\.\./images/[^`]+)`"
)

MODULE_IMAGE_SRCSET_RE = re.compile(
    r"(?P<key>\bsrcSet)\s*:\s*`(?P<entries>\.\./\.\./images/[^`]+)`"
)

MODULE_TEMPLATE_CSS_URL_RE = re.compile(
    r"`(?P<prefix>[^`$]*?)url\((?P<url_quote>['\"]?)(?P<path>(?:\.\./)+(?:images|media)/[^'\"`)]+)(?P=url_quote)\)(?P<suffix>[^`$]*?)`"
)

MODULE_ASSET_VALUE_RE = re.compile(
    r"(?P<prefix>(?::|\?\?|\|\||\?|=|,|\[)\s*)(?P<quote>[\"'`])(?P<path>(?:\.\./)+(?:images|media)/[^\"'`\s)]+)(?P=quote)"
)

SOURCE_MAP_COMMENT_RE = re.compile(
    r"(?:\n?//# sourceMappingURL=[^\n]+)|(?:/\*# sourceMappingURL=.*?\*/\s*)",
    re.DOTALL,
)

SNIPPETS_MODULE_RE = re.compile(
    r"loadSnippetsModule:new\s+[A-Za-z0-9_$]+\(\(\)=>import\(`\./(?P<filename>[^`]+)`\)\)"
)

NOT_FOUND_PAGE_RE = re.compile(
    r"notFoundPage:[A-Za-z0-9_$]+\(\(\)=>import\(`\./(?P<filename>[^`]+)`\)\)"
)

BADGE_MODULE_RE = re.compile(
    r"__framer-badge-container`\),[^\n]*?import\(`\./(?P<filename>[^`]+)`\)"
)

COLLECTION_UTILS_RE = re.compile(
    r"(?P<collection_id>[A-Za-z0-9_]+):async\(\)=>\(await import\(`\./(?P<filename>[^`]+)`\)\)\?\.utils"
)

BADGE_HYDRATION_RE = re.compile(
    r"sr&&u\(\(\)=>\{C\(document\.getElementById\(`__framer-badge-container`\),w\(y,\{\},w\(ee\(\(\)=>import\(`\./[^`]+`\)\)\)\)\)\}\)"
)

EMPTY_SNIPPETS_MODULE = """const emptySnippets = {
  bodyStart: [],
  bodyEnd: [],
  headStart: [],
  headEnd: [],
};

export async function getSnippets() {
  return emptySnippets;
}

export const snippetsSorting = {
  bodyStart: [],
  bodyEnd: [],
  headStart: [],
  headEnd: [],
};

export default { getSnippets, snippetsSorting };
"""

BADGE_DISABLED_MODULE = """export default function FramerBadge() {
  return null;
}
"""

NOT_FOUND_MODULE = """export default function NotFoundPage() {
  return "Page not found";
}

export const queryParamNames = [];
"""

EMPTY_FONT_METADATA_MODULE = "export default {};\n"

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


def extract_framer_asset_reference_urls(text: str) -> set[str]:
    found: set[str] = set()
    for match in FRAMER_ASSET_REFERENCE_RE.finditer(text):
        asset = html.unescape(match.group("asset").strip())
        if not asset:
            continue
        found.add(normalize_remote_url(asset, base="https://framerusercontent.com/images/"))
    return found


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


def strip_source_map_comments(text: str) -> str:
    return SOURCE_MAP_COMMENT_RE.sub("", text)


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
        queue.extend(sorted(extract_framer_asset_reference_urls(page.html_text)))

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
            queue.extend(sorted(extract_framer_asset_reference_urls(text)))
            queue.extend(sorted(extract_relative_dependencies(text, remote_url)))

    return assets


def replace_url_tokens(text: str, current_file: Path, target_map: dict[str, Path]) -> str:
    for remote_url, target_path in sorted(target_map.items(), key=lambda item: len(item[0]), reverse=True):
        relative = os.path.relpath(target_path, start=current_file.parent).replace(os.sep, "/")
        for source in {remote_url, remote_url.replace("&", "&amp;")}:
            text = text.replace(source, relative)
    return text


def apply_brand_replacements(text: str) -> str:
    for source, target in BRAND_REPLACEMENTS.items():
        text = text.replace(source, target)
    return text


def framer_image_alias_name(remote_url: str) -> str | None:
    parsed = urlparse(remote_url)
    if parsed.netloc != "framerusercontent.com":
        return None
    parts = [segment for segment in parsed.path.split("/") if segment]
    if parts[:1] != ["images"]:
        return None
    return PurePosixPath(parsed.path).name or None


def framer_image_alias_score(remote_url: str) -> tuple[int, int, int, int]:
    parsed = urlparse(remote_url)
    query = parse_qs(parsed.query)

    def query_int(name: str) -> int:
        raw = query.get(name, ["0"])[0]
        try:
            return int(raw)
        except ValueError:
            return 0

    width = query_int("width")
    height = query_int("height")
    scale_down_to = query_int("scale-down-to")
    area = width * height
    return (area, scale_down_to, max(width, height), len(parsed.query))


def write_framer_image_aliases(assets: dict[str, AssetRecord]) -> None:
    best_records: dict[str, tuple[tuple[int, int, int, int], AssetRecord]] = {}

    for record in assets.values():
        alias_name = framer_image_alias_name(record.remote_url)
        if not alias_name:
            continue

        score = framer_image_alias_score(record.remote_url)
        current = best_records.get(alias_name)
        if current is None or score > current[0]:
            best_records[alias_name] = (score, record)

    for alias_name, (_score, record) in best_records.items():
        alias_path = ASSETS_ROOT / "framer" / "images" / alias_name
        if alias_path == record.local_path:
            continue
        alias_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(record.local_path, alias_path)


def rewrite_module_image_sources(text: str) -> str:
    text = MODULE_IMAGE_SRC_RE.sub(
        lambda match: (
            f"{match.group('key')}:"
            f"new URL(`{match.group('path')}`,import.meta.url).href"
        ),
        text,
    )

    def replace_srcset(match: re.Match[str]) -> str:
        parts: list[str] = []
        for entry in match.group("entries").split(","):
            item = entry.strip()
            if not item:
                continue
            image_path, _separator, descriptor = item.partition(" ")
            expression = f"new URL(`{image_path}`,import.meta.url).href"
            if descriptor:
                expression += f"+` {descriptor}`"
            parts.append(expression)
        return f"{match.group('key')}:[{','.join(parts)}].join(`,`)"

    return MODULE_IMAGE_SRCSET_RE.sub(replace_srcset, text)


def rewrite_module_asset_values(text: str) -> str:
    text = MODULE_TEMPLATE_CSS_URL_RE.sub(
        lambda match: (
            f"`{match.group('prefix')}"
            f"url(${{new URL(`{match.group('path')}`,import.meta.url).href}})"
            f"{match.group('suffix')}`"
        ),
        text,
    )
    return MODULE_ASSET_VALUE_RE.sub(
        lambda match: (
            f"{match.group('prefix')}"
            f"new URL(`{match.group('path')}`,import.meta.url).href"
        ),
        text,
    )


def rewrite_logo_component(text: str) -> str:
    if LOGO_COMPONENT_RULE_OLD not in text:
        return text
    return text.replace(LOGO_COMPONENT_RULE_OLD, LOGO_COMPONENT_RULE_NEW)


def postprocess_runtime_text(text: str, current_file: Path) -> str:
    for source, replacement in RUNTIME_TEXT_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    for source, replacement in CMS_RANGE_RESPONSE_REPLACEMENTS:
        text = text.replace(source, replacement)
    text = LOCAL_FRAMER_CMS_RELATIVE_BASE_RE.sub(
        lambda match: (
            f"new URL({match.group('asset')},"
            f"new URL({match.group('base')},import.meta.url)).href"
        ),
        text,
    )
    text = LOCAL_FRAMER_CMS_IMPORT_META_RE.sub(
        lambda match: f"new URL({match.group('asset')},import.meta.url).href",
        text,
    )
    if current_file.suffix in {".js", ".mjs"}:
        text = BADGE_HYDRATION_RE.sub("sr&&u(()=>{})", text)
        text = rewrite_module_image_sources(text)
        text = rewrite_module_asset_values(text)
        text = rewrite_logo_component(text)
    if current_file.suffix in {".css", ".js", ".mjs"}:
        text = strip_source_map_comments(text)
    return text


def ensure_local_runtime_nodes(doc: lxml_html.HtmlElement) -> None:
    existing = doc.xpath("//*[@id='__framer-badge-container']")
    if existing:
        container = existing[0]
        for child in list(container):
            container.remove(child)
        container.text = None
        return
    bodies = doc.xpath("//body")
    if not bodies:
        return
    badge_container = lxml_html.Element("div")
    badge_container.set("id", "__framer-badge-container")
    bodies[0].append(badge_container)


def build_collection_utils_wrapper(site_bundle_dir: Path, collection_id: str) -> str:
    target = next(
        (
            candidate
            for candidate in sorted(site_bundle_dir.glob(f"{collection_id}*.mjs"))
            if candidate.name != f"{collection_id}.mjs"
        ),
        None,
    )
    if target is None:
        return """export const utils = {
  async getSlugByRecordId() {
    return undefined;
  },
  async getRecordIdBySlug() {
    return undefined;
  },
};

export default { utils };
"""
    return f"""import * as collectionModule from "./{target.name}";

const exportedUtils = Object.values(collectionModule).find(
  (value) =>
    value &&
    typeof value.getSlugByRecordId === "function" &&
    typeof value.getRecordIdBySlug === "function",
);

export const utils = exportedUtils ?? {{
  async getSlugByRecordId() {{
    return undefined;
  }},
  async getRecordIdBySlug() {{
    return undefined;
  }},
}};

export default {{ utils }};
"""


def write_runtime_support_modules(site_bundle_dir: Path) -> None:
    script_main = next(iter(sorted(site_bundle_dir.glob("script_main*.mjs"))), None)
    if script_main is None:
        return

    script_text = script_main.read_text(encoding="utf-8")

    snippet_match = SNIPPETS_MODULE_RE.search(script_text)
    if snippet_match:
        (site_bundle_dir / snippet_match.group("filename")).write_text(
            EMPTY_SNIPPETS_MODULE,
            encoding="utf-8",
        )

    badge_match = BADGE_MODULE_RE.search(script_text)
    if badge_match:
        (site_bundle_dir / badge_match.group("filename")).write_text(
            BADGE_DISABLED_MODULE,
            encoding="utf-8",
        )

    not_found_match = NOT_FOUND_PAGE_RE.search(script_text)
    if not_found_match:
        not_found_path = site_bundle_dir / not_found_match.group("filename")
        if not not_found_path.exists():
            not_found_path.write_text(NOT_FOUND_MODULE, encoding="utf-8")

    for match in COLLECTION_UTILS_RE.finditer(script_text):
        collection_utils_path = site_bundle_dir / match.group("filename")
        if collection_utils_path.exists():
            continue
        collection_utils_path.write_text(
            build_collection_utils_wrapper(site_bundle_dir, match.group("collection_id")),
            encoding="utf-8",
        )

    for site_module in sorted(site_bundle_dir.glob("*.mjs")):
        text = site_module.read_text(encoding="utf-8")
        for match in RELATIVE_MODULE_RE.finditer(text):
            candidate = next(group for group in match.groups() if group)
            if not candidate.startswith("./") or not candidate.endswith(".mjs"):
                continue
            module_path = site_bundle_dir / candidate[2:]
            if module_path.exists():
                continue
            module_name = module_path.name
            if module_name.startswith(("google-", "fontshare-", "framer-font-")):
                module_path.write_text(EMPTY_FONT_METADATA_MODULE, encoding="utf-8")


def prune_framer_nodes(doc: lxml_html.HtmlElement) -> None:
    xpaths = [
        "//script[contains(., 'framer.com/edit/init.mjs')]",
        "//script[starts-with(@src, 'https://events.framer.com/')]",
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
    ensure_local_runtime_nodes(doc)

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
    return apply_brand_replacements(replace_url_tokens(rendered, page.local_path, asset_map))


def write_build(pages: Iterable[PageRecord], assets: dict[str, AssetRecord]) -> None:
    asset_path_map = {remote_url: record.local_path for remote_url, record in assets.items()}

    for page in pages:
        page.local_path.parent.mkdir(parents=True, exist_ok=True)
        page.local_path.write_text(rewrite_page(page, asset_path_map), encoding="utf-8")

    for record in assets.values():
        record.local_path.parent.mkdir(parents=True, exist_ok=True)
        if record.is_text:
            rewritten = replace_url_tokens(record.decode(), record.local_path, asset_path_map)
            rewritten = postprocess_runtime_text(rewritten, record.local_path)
            rewritten = apply_brand_replacements(rewritten)
            record.local_path.write_text(rewritten, encoding="utf-8")
        else:
            record.local_path.write_bytes(record.raw_bytes)

    write_framer_image_aliases(assets)

    site_bundle_dir = ASSETS_ROOT / "framer" / "sites" / SITE_ID
    if site_bundle_dir.exists():
        (site_bundle_dir / "edit-init-disabled.mjs").write_text(
            "export function createEditorBar() { return () => null; }\n",
            encoding="utf-8",
        )
        write_runtime_support_modules(site_bundle_dir)

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
