"""
网页内容加载器 v1.0
====================
基于 trafilatura 抽取正文，自动回退到 requests + BeautifulSoup。

兼容 LangChain Document 对象，可直接接入 RAGEngine。
"""

import re
import warnings
from datetime import datetime
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

from langchain_core.documents import Document

warnings.filterwarnings("ignore")

# 浏览器风格的 User-Agent，避免被反爬
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# =============================================================================
# 1. URL 校验与域名工具
# =============================================================================

def is_valid_url(url: str) -> bool:
    """
    校验 URL 格式是否合法（要求 http/https 开头且含域名）。

    Args:
        url: 待校验的 URL 字符串

    Returns:
        True 表示合法，False 表示不合法
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    return True


def extract_domain(url: str) -> str:
    """
    从 URL 中提取主域名（去除 www. 前缀）。

    Args:
        url: 完整 URL，如 https://www.zhihu.com/xxx

    Returns:
        主域名，如 zhihu.com；解析失败返回空字符串
    """
    if not url or not isinstance(url, str):
        return ""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return ""
    host = parsed.netloc
    if not host:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


# =============================================================================
# 2. 网页加载器主类
# =============================================================================

class WebLoader:
    """
    网页内容加载器（trafilatura 抽取正文，回退 requests + BeautifulSoup）。

    用法：
        loader = WebLoader("https://example.com/article")
        docs = loader.load()
    """

    def __init__(self, url: str, timeout: int = 30):
        """
        初始化网页加载器。

        Args:
            url: 目标网页 URL
            timeout: 网络请求超时（秒），默认 30
        """
        self.url = url
        self.timeout = timeout

    def load(self) -> List[Document]:
        """
        抓取并解析 URL，返回 Document 列表（无内容时为空列表）。

        流程：
            1. 优先用 trafilatura.fetch_url + extract 抓取正文
            2. trafilatura 不可用或失败时回退 requests + BeautifulSoup
            3. 抽取失败时打印警告并返回 []

        Returns:
            包含单条网页正文的 Document 列表
        """
        content, title = self._fetch_content()
        if not content or not content.strip():
            print(f"[WebLoader] ⚠️ 未提取到有效内容: {self.url}")
            return []
        metadata = self._build_metadata(self.url, title)
        return [Document(page_content=content.strip(), metadata=metadata)]

    # ------------------------- 内部方法（私有） -------------------------

    def _fetch_content(self) -> tuple:
        """
        调度抓取策略：trafilatura 优先，失败回退 requests。

        Returns:
            (正文文本, 页面标题)；任一失败对应字段为 None
        """
        # 任何抓取方法的内部异常都应被其自身捕获，这里再做一层防御
        try:
            result = self._fetch_with_trafilatura()
            if result is not None:
                text, title = result
                if text and text.strip():
                    return text, title
        except Exception as e:
            print(f"[WebLoader] ⚠️ trafilatura 抓取异常: {e}")
        try:
            return self._fetch_with_requests() or (None, None)
        except Exception as e:
            print(f"[WebLoader] ⚠️ requests 抓取异常: {e}")
            return None, None

    def _fetch_with_trafilatura(self) -> Optional[tuple]:
        """
        使用 trafilatura 抓取并抽取正文（最优方案）。

        Returns:
            (text, title) 元组；不可用或失败时返回 None
        """
        trafilatura = self._import_trafilatura()
        if trafilatura is None:
            return None
        try:
            html = trafilatura.fetch_url(self.url, no_ssl=True)
            if not html:
                return None
            text = self._extract_with_trafilatura(trafilatura, html)
            if not text:
                return None
            # 解析 metadata 行以获取 title
            title = self._parse_traf_title(text) or self._extract_title_from_html(html)
            return text.strip(), title
        except Exception as e:
            print(f"[WebLoader] ⚠️ trafilatura 抓取失败: {e}")
            return None

    @staticmethod
    def _import_trafilatura():
        """导入 trafilatura，失败时打印提示并返回 None。"""
        try:
            import trafilatura
            return trafilatura
        except ImportError:
            print("[WebLoader] ℹ️ trafilatura 未安装，将使用 requests 回退")
            return None

    @staticmethod
    def _extract_with_trafilatura(trafilatura_module, html: str) -> Optional[str]:
        """调用 trafilatura.extract 抽取 markdown 正文，失败返回 None。"""
        try:
            return trafilatura_module.extract(
                html,
                include_comments=False,
                include_tables=True,
                output_format="markdown",
                with_metadata=True,
            )
        except Exception as e:
            print(f"[WebLoader] ⚠️ trafilatura 抽取失败: {e}")
            return None

    def _fetch_with_requests(self) -> Optional[tuple]:
        """
        回退方案：requests + BeautifulSoup 抓取（无正文提取能力，仅取全文本）。

        Returns:
            (text, title) 元组；不可用或失败时返回 None
        """
        deps = self._import_requests_bs4()
        if deps is None:
            return None
        requests, BeautifulSoup = deps
        try:
            response = self._http_get(requests)
            if response is None:
                return None
            soup = BeautifulSoup(response.text, "html.parser")
            # 移除干扰标签，避免把脚本/样式塞进 RAG 上下文
            for tag in soup(["script", "style", "noscript", "iframe"]):
                tag.decompose()
            title = self._extract_title_from_soup(soup) or "未知标题"
            text = soup.get_text(separator="\n", strip=True)
            return text, title
        except Exception as e:
            print(f"[WebLoader] ⚠️ requests 抓取失败: {e}")
            return None

    @staticmethod
    def _import_requests_bs4():
        """导入 requests + bs4，失败时打印提示并返回 None。"""
        try:
            import requests
            from bs4 import BeautifulSoup
            return requests, BeautifulSoup
        except ImportError:
            print("[WebLoader] ❌ requests/bs4 未安装，无法抓取网页")
            return None

    def _http_get(self, requests_module):
        """用 requests 发起 GET 请求，失败返回 None。"""
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            response = requests_module.get(
                self.url,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
            )
            response.raise_for_status()
            return response
        except Exception as e:
            print(f"[WebLoader] ⚠️ HTTP 请求失败: {e}")
            return None

    @staticmethod
    def _build_metadata(url: str, title: str) -> Dict[str, Any]:
        """
        构造 Document 的 metadata 字段。

        Args:
            url: 原始 URL（作为 source，便于追溯）
            title: 网页标题

        Returns:
            包含 source / page / file_type / title / domain / fetched_at 的字典
        """
        return {
            "source": url,
            "page": 0,
            "file_type": ".html",
            "title": title or "未知标题",
            "domain": extract_domain(url),
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        }

    # ------------------------- 标题解析辅助 -------------------------

    @staticmethod
    def _parse_traf_title(text: str) -> str:
        """
        从 trafilatura with_metadata 输出中解析 title 行。

        trafilatura 输出首部形如：
            <title>示例页面</title>
            <author>...</author>
        """
        match = re.search(r"<title>\s*(.+?)\s*</title>", text)
        if match:
            return match.group(1).strip()
        return ""

    @staticmethod
    def _extract_title_from_html(html: str) -> str:
        """从原始 HTML 字符串中提取 <title> 或 og:title。"""
        match = re.search(
            r'<meta\s+[^>]*property=["\']og:title["\']\s+[^>]*content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    @staticmethod
    def _extract_title_from_soup(soup) -> str:
        """从 BeautifulSoup 对象中提取 title。"""
        try:
            tag = soup.find("title")
        except Exception:
            return ""
        if tag and tag.string:
            return tag.string.strip()
        # 回退到 og:title
        meta = soup.find("meta", attrs={"property": "og:title"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return ""
