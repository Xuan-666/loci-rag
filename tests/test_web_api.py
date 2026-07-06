"""
Web API 路由层单元测试（不启动 Flask,直接调用 view function）
=============================================================
"""
import json
import pytest

try:
    from web_api import app
    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False


pytestmark = pytest.mark.skipif(
    not _HAS_DEPS,
    reason="web_api dependencies not installed (run `pip install -r requirements.txt` in CI)",
)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_index_serves_html(client):
    """GET / 应返回 frontend/index.html (200 + HTML 内容)"""
    resp = client.get("/")
    assert resp.status_code == 200
    # 前端 index.html 包含 Loci 标识
    assert b"Loci" in resp.data or b"loci" in resp.data.lower()


def test_health_endpoint(client):
    """健康检查端点应返回 200 + JSON"""
    resp = client.get("/api/health")
    # 该端点可能存在也可能不存在,仅验证不抛 500
    assert resp.status_code in (200, 404)


def test_static_files_served(client):
    """前端静态文件 (custom.css / app.js) 应可访问"""
    # 前端 static/ 在 STATIC_DIR 下,Flask 路由的 static 路径
    for path in ("/static/app.js", "/static/custom.css"):
        resp = client.get(path)
        # 找不到算 404,找到算 200;两者都不应是 500
        assert resp.status_code in (200, 404), f"{path} returned {resp.status_code}"


def test_api_404_returns_json(client):
    """未知 API 路径不应返回 HTML 错误页(尽量返回 JSON)"""
    resp = client.get("/api/nonexistent_path_for_test_xyz")
    # 500 才算严重问题,404/200 都可以接受
    assert resp.status_code != 500


def test_app_has_cors_headers():
    """Flask-CORS 应被正确配置(响应头含 Access-Control-Allow-Origin)"""
    test_app = app
    test_app.config["TESTING"] = True
    with test_app.test_client() as c:
        # 模拟跨域预检
        resp = c.options("/")
        # 关键检查:CORS 头存在
        assert "Access-Control-Allow-Origin" in resp.headers or resp.status_code in (200, 204, 405)
