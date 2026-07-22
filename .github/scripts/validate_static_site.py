#!/usr/bin/env python3
"""쌍칼 아카이브 정적 배포 파일의 구조, 링크, SEO 기본 품질을 검사한다."""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_URL = "https://ssangkalweb.github.io/ssangkal-archive/"
PUBLIC_PATH = urlparse(PUBLIC_URL).path.rstrip("/")
REQUIRED_FILES = (
    "index.html", "style.css", "script.js", "404.html", "robots.txt",
    "sitemap.xml", "favicon.svg", ".gitattributes", ".nojekyll",
    ".github/scripts/validate_static_site.py", ".github/workflows/quality-checks.yml",
    "life/index.html", "life/workers-compensation-aftercare.html",
)
EXCLUDED_HTML_PARTS = {".git", ".github"}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_lang = ""
        self.title_parts: list[str] = []
        self.in_title = False
        self.meta: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.ids: set[str] = set()
        self.h1_count = 0
        self.main_count = 0
        self.article_count = 0
        self.times: list[dict[str, str]] = []
        self.skip_links: list[str] = []
        self.json_ld_documents: list[str] = []
        self._json_ld_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "html":
            self.html_lang = values.get("lang", "")
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            self.meta.append(values)
        elif tag == "link":
            self.links.append(values)
        elif tag == "script":
            self.scripts.append(values)
            if values.get("type", "").lower() == "application/ld+json":
                self._json_ld_parts = []
        elif tag == "img":
            self.images.append(values)
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "main":
            self.main_count += 1
        elif tag == "article":
            self.article_count += 1
        elif tag == "time":
            self.times.append(values)
        elif tag == "a":
            self.links.append(values)
            if "skip-link" in values.get("class", "").split():
                self.skip_links.append(values.get("href", ""))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "script" and self._json_ld_parts is not None:
            self.json_ld_documents.append("".join(self._json_ld_parts))
            self._json_ld_parts = None

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self._json_ld_parts is not None:
            self._json_ld_parts.append(data)

    @property
    def title(self) -> str:
        return "".join(self.title_parts).strip()


def parse_page(path: Path) -> PageParser:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def meta_value(page: PageParser, key: str, value: str) -> str:
    return next((item.get("content", "").strip() for item in page.meta
                 if item.get(key, "").lower() == value.lower()), "")


def canonical_value(page: PageParser) -> str:
    return next((item.get("href", "").strip() for item in page.links
                 if "canonical" in item.get("rel", "").lower().split()), "")


def local_target(page_path: Path, href: str) -> tuple[Path, str] | None:
    """내부 링크를 실제 로컬 파일과 앵커로 변환한다."""
    parsed = urlparse(href)
    if parsed.scheme in {"http", "https", "mailto", "tel"} or parsed.netloc:
        return None
    clean_path = unquote(parsed.path)
    if clean_path.startswith(PUBLIC_PATH + "/") or clean_path == PUBLIC_PATH:
        clean_path = clean_path[len(PUBLIC_PATH):].lstrip("/")
        target = ROOT / clean_path
    elif clean_path.startswith("/"):
        return None
    elif not clean_path:
        target = page_path
    else:
        target = page_path.parent / clean_path
    if clean_path.endswith("/") or (parsed.path and parsed.path.endswith("/")):
        target /= "index.html"
    return target.resolve(), unquote(parsed.fragment)


def public_url_for(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix()
    if relative == "index.html":
        return PUBLIC_URL
    if relative.endswith("/index.html"):
        return PUBLIC_URL + relative[:-10]
    return PUBLIC_URL + relative


def structured_types(value: object) -> set[str]:
    if isinstance(value, dict):
        node_type = value.get("@type")
        types = {node_type} if isinstance(node_type, str) else set(node_type or [])
        if "@graph" in value:
            for node in value["@graph"]:
                types.update(structured_types(node))
        return types
    if isinstance(value, list):
        result: set[str] = set()
        for node in value:
            result.update(structured_types(node))
        return result
    return set()


def check_page(path: Path, page: PageParser, pages: dict[Path, PageParser], errors: list[str]) -> None:
    label = path.relative_to(ROOT).as_posix()
    if page.html_lang != "ko":
        errors.append(f'{label}: lang 속성은 "ko"여야 합니다.')
    if not page.title:
        errors.append(f"{label}: title이 없습니다.")
    if not meta_value(page, "name", "description"):
        errors.append(f"{label}: meta description이 없습니다.")
    if not meta_value(page, "name", "viewport"):
        errors.append(f"{label}: viewport가 없습니다.")
    if not canonical_value(page):
        errors.append(f"{label}: canonical 링크가 없습니다.")
    if page.h1_count != 1:
        errors.append(f"{label}: h1은 정확히 하나여야 합니다. 현재: {page.h1_count}")
    if page.main_count != 1:
        errors.append(f"{label}: main은 정확히 하나여야 합니다. 현재: {page.main_count}")
    if not page.skip_links:
        errors.append(f"{label}: skip link가 없습니다.")
    if not any("icon" in item.get("rel", "").lower().split() for item in page.links):
        errors.append(f"{label}: favicon 링크가 없습니다.")
    for image in page.images:
        if "alt" not in image:
            errors.append(f"{label}: 이미지에 alt가 없습니다: {image.get('src', '(src 없음)')}")
    for script in page.scripts:
        if script.get("src") and "defer" not in script:
            errors.append(f"{label}: 외부 script에 defer가 없습니다: {script['src']}")

    for link in page.links:
        if "href" not in link:
            continue
        href = link["href"].strip()
        if not href:
            errors.append(f"{label}: 빈 href가 있습니다.")
            continue
        if href.lower().startswith("javascript:"):
            errors.append(f"{label}: javascript: 링크가 있습니다: {href}")
        if link.get("target", "").lower() == "_blank":
            rel = set(link.get("rel", "").lower().split())
            if not {"noopener", "noreferrer"}.issubset(rel):
                errors.append(f"{label}: 새 탭 링크에 noopener noreferrer가 없습니다: {href}")
        target_info = local_target(path, href)
        if target_info is None:
            continue
        target, fragment = target_info
        if not target.is_file():
            errors.append(f"{label}: 내부 링크 대상 파일이 없습니다: {href}")
        elif fragment and target.suffix.lower() == ".html":
            target_page = pages.get(target) or parse_page(target)
            if fragment not in target_page.ids:
                errors.append(f"{label}: 내부 앵커 대상이 없습니다: {href}")

    if page.skip_links:
        for href in page.skip_links:
            target_info = local_target(path, href)
            if target_info and target_info[1] not in page.ids:
                errors.append(f"{label}: skip link 대상이 없습니다: {href}")

    is_article = path.parent.name == "life" and path.name != "index.html"
    if is_article:
        if page.article_count < 1:
            errors.append(f"{label}: article 요소가 없습니다.")
        if not page.times or any(not item.get("datetime") for item in page.times):
            errors.append(f"{label}: 모든 time 요소에 datetime이 필요합니다.")
        json_types: set[str] = set()
        for document in page.json_ld_documents:
            try:
                json_types.update(structured_types(json.loads(document)))
            except json.JSONDecodeError as exc:
                errors.append(f"{label}: JSON-LD 형식이 올바르지 않습니다: {exc}")
        if "Article" not in json_types:
            errors.append(f"{label}: JSON-LD Article이 없습니다.")


def main() -> int:
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"필수 파일이 없습니다: {relative}")
    if errors:
        return report(errors)

    html_paths = sorted(
        path.resolve() for path in ROOT.rglob("*.html")
        if not EXCLUDED_HTML_PARTS.intersection(path.relative_to(ROOT).parts)
    )
    pages = {path: parse_page(path) for path in html_paths}
    for path, page in pages.items():
        check_page(path, page, pages, errors)

    try:
        favicon_root = ET.parse(ROOT / "favicon.svg").getroot()
        if favicon_root.tag != "{http://www.w3.org/2000/svg}svg":
            errors.append("favicon.svg의 루트 요소가 SVG가 아닙니다.")
        if any(node.tag.endswith("script") for node in favicon_root.iter()):
            errors.append("favicon.svg에 script 요소가 있습니다.")
    except ET.ParseError as exc:
        errors.append(f"favicon.svg XML 형식이 올바르지 않습니다: {exc}")

    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
    if "User-agent: *" not in robots or "Allow: /" not in robots:
        errors.append("robots.txt의 기본 크롤링 지시가 올바르지 않습니다.")
    if f"Sitemap: {PUBLIC_URL}sitemap.xml" not in robots:
        errors.append("robots.txt의 sitemap 주소가 올바르지 않습니다.")

    sitemap_locations: set[str] = set()
    try:
        sitemap_root = ET.parse(ROOT / "sitemap.xml").getroot()
        namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        sitemap_locations = {node.text.strip() for node in sitemap_root.findall("sm:url/sm:loc", namespace) if node.text}
    except ET.ParseError as exc:
        errors.append(f"sitemap.xml XML 형식이 올바르지 않습니다: {exc}")

    public_pages = {public_url_for(path) for path in html_paths if path.name != "404.html"}
    for missing in sorted(public_pages - sitemap_locations):
        errors.append(f"sitemap.xml에 실제 공개 페이지가 없습니다: {missing}")
    for extra in sorted(sitemap_locations - public_pages):
        errors.append(f"sitemap.xml에 존재하지 않는 로컬 페이지가 있습니다: {extra}")

    source_paths = html_paths + [ROOT / name for name in ("style.css", "script.js", "robots.txt", "sitemap.xml")]
    sensitive_patterns = {
        "주민등록번호 형태": re.compile(r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)"),
        "휴대전화번호 형태": re.compile(r"(?<!\d)01[016789][-. ]?\d{3,4}[-. ]?\d{4}(?!\d)"),
        "계좌번호 표기": re.compile(r"(?:계좌(?:번호)?|account)\s*[:：]?\s*\d{2,6}(?:-\d{2,6}){2,4}", re.IGNORECASE),
    }
    for path in source_paths:
        text = path.read_text(encoding="utf-8")
        label = path.relative_to(ROOT).as_posix()
        if re.search(r"(?:https?://)?(?:localhost|127\.0\.0\.1)(?::\d+)?", text, re.IGNORECASE):
            errors.append(f"{label}: 금지된 localhost 링크가 있습니다.")
        for pattern_name, pattern in sensitive_patterns.items():
            if pattern.search(text):
                errors.append(f"{label}: 민감정보로 보이는 {pattern_name}가 있습니다.")

    index = pages[(ROOT / "index.html").resolve()]
    if canonical_value(index) != PUBLIC_URL:
        errors.append("index.html canonical 주소가 공개 주소와 다릅니다.")
    if meta_value(index, "property", "og:url") != PUBLIC_URL:
        errors.append("index.html Open Graph URL이 공개 주소와 다릅니다.")
    return report(errors)


def report(errors: list[str]) -> int:
    if errors:
        print("정적 사이트 검사 실패:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("정적 사이트 검사를 모두 통과했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
