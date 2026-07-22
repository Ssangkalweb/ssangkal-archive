#!/usr/bin/env python3
"""쌍칼 아카이브 정적 배포 파일의 기본 품질을 검사한다."""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_URL = "https://ssangkalweb.github.io/ssangkal-archive/"
REQUIRED_FILES = (
    "index.html",
    "style.css",
    "script.js",
    "404.html",
    "robots.txt",
    "sitemap.xml",
    "favicon.svg",
    ".gitattributes",
    ".nojekyll",
    ".github/scripts/validate_static_site.py",
    ".github/workflows/quality-checks.yml",
)


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
        self.skip_links: list[str] = []
        self.json_ld_parts: list[str] = []
        self.in_json_ld = False

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
                self.in_json_ld = True
        elif tag == "img":
            self.images.append(values)
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "main":
            self.main_count += 1
        elif tag == "a":
            href = values.get("href", "")
            classes = values.get("class", "").split()
            self.links.append(values)
            if "skip-link" in classes:
                self.skip_links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "script" and self.in_json_ld:
            self.in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.in_json_ld:
            self.json_ld_parts.append(data)

    @property
    def title(self) -> str:
        return "".join(self.title_parts).strip()


def parse_page(path: Path) -> PageParser:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def meta_value(page: PageParser, key: str, value: str, content_key: str = "content") -> str:
    for item in page.meta:
        if item.get(key, "").lower() == value.lower():
            return item.get(content_key, "").strip()
    return ""


def canonical_value(page: PageParser) -> str:
    for item in page.links:
        if item.get("rel", "").lower() == "canonical":
            return item.get("href", "").strip()
    return ""


def has_svg_favicon(page: PageParser) -> bool:
    return any(
        "icon" in item.get("rel", "").lower().split()
        and item.get("href", "").strip() == "favicon.svg"
        and item.get("type", "").lower() == "image/svg+xml"
        for item in page.links
    )


def check_links(page: PageParser, label: str, errors: list[str], check_anchors: bool) -> None:
    for link in page.links:
        if "href" not in link:
            continue
        href = link["href"].strip()
        if not href:
            errors.append(f"{label}: 빈 href가 있습니다.")
        if href.lower().startswith("javascript:"):
            errors.append(f"{label}: javascript: 링크가 있습니다: {href}")
        if link.get("target", "").lower() == "_blank":
            rel = set(link.get("rel", "").lower().split())
            if not {"noopener", "noreferrer"}.issubset(rel):
                errors.append(f"{label}: 새 탭 링크에 noopener noreferrer가 없습니다: {href}")
        if check_anchors and href.startswith("#") and href[1:] not in page.ids:
            errors.append(f"{label}: 내부 앵커 대상이 없습니다: {href}")


def main() -> int:
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"필수 파일이 없습니다: {relative}")

    if errors:
        return report(errors)

    index = parse_page(ROOT / "index.html")
    not_found = parse_page(ROOT / "404.html")

    if index.html_lang != "ko":
        errors.append('index.html의 lang 속성은 "ko"여야 합니다.')
    if not index.title:
        errors.append("index.html에 title이 없습니다.")
    if not meta_value(index, "name", "description"):
        errors.append("index.html에 meta description이 없습니다.")
    if not meta_value(index, "name", "viewport"):
        errors.append("index.html에 viewport가 없습니다.")
    if canonical_value(index) != PUBLIC_URL:
        errors.append("index.html canonical 주소가 예정 공개 주소와 다릅니다.")
    if index.h1_count != 1:
        errors.append(f"index.html의 h1은 정확히 하나여야 합니다. 현재: {index.h1_count}")
    if index.main_count != 1:
        errors.append("index.html에 main 요소가 정확히 하나 있어야 합니다.")
    if not index.skip_links or not all(link.startswith("#") for link in index.skip_links):
        errors.append("index.html에 유효한 skip link가 없습니다.")
    if not has_svg_favicon(index):
        errors.append("index.html에 favicon.svg 링크가 없습니다.")
    if not has_svg_favicon(not_found):
        errors.append("404.html에 favicon.svg 링크가 없습니다.")
    for image in index.images + not_found.images:
        if "alt" not in image:
            errors.append(f"이미지에 alt 속성이 없습니다: {image.get('src', '(src 없음)')}")
    for script in index.scripts:
        if script.get("src") and "defer" not in script:
            errors.append(f"외부 script에 defer가 없습니다: {script['src']}")

    check_links(index, "index.html", errors, True)
    check_links(not_found, "404.html", errors, True)

    expected_404_path = urlparse(PUBLIC_URL).path
    not_found_hrefs = {link.get("href", "") for link in not_found.links}
    if expected_404_path not in not_found_hrefs:
        errors.append(f"404.html에 아카이브 루트 링크({expected_404_path})가 없습니다.")

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

    try:
        sitemap_root = ET.parse(ROOT / "sitemap.xml").getroot()
        namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = [node.text or "" for node in sitemap_root.findall("sm:url/sm:loc", namespace)]
        if locations != [PUBLIC_URL]:
            errors.append("sitemap.xml에는 예정 공개 홈페이지 주소 하나만 있어야 합니다.")
    except ET.ParseError as exc:
        errors.append(f"sitemap.xml XML 형식이 올바르지 않습니다: {exc}")

    source_files = [
        ROOT / "index.html",
        ROOT / "404.html",
        ROOT / "style.css",
        ROOT / "script.js",
        ROOT / "robots.txt",
        ROOT / "sitemap.xml",
    ]
    for path in source_files:
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?:https?://)?(?:localhost|127\.0\.0\.1)(?::\d+)?", text, re.IGNORECASE):
            errors.append(f"금지된 localhost 링크가 있습니다: {path.name}")

    if meta_value(index, "property", "og:url") != PUBLIC_URL:
        errors.append("Open Graph URL이 예정 공개 주소와 다릅니다.")
    try:
        structured = json.loads("".join(index.json_ld_parts))
        if structured.get("url") != PUBLIC_URL or structured.get("mainEntity", {}).get("url") != PUBLIC_URL:
            errors.append("JSON-LD의 공개 주소가 예정 공개 주소와 다릅니다.")
    except (json.JSONDecodeError, AttributeError) as exc:
        errors.append(f"JSON-LD 형식이 올바르지 않습니다: {exc}")

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
