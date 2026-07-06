"""
ChatStore 单元测试
==================
覆盖多会话聊天记录的持久化、线程安全、容错读、原子写。
"""
import json
import threading
from loci.chat_store import ChatStore


def test_create_session_returns_uuid(tmp_data_dir):
    """创建会话应返回字符串 UUID,且文件落盘"""
    store_path = tmp_data_dir / "chat.json"
    store = ChatStore(str(store_path))

    sid = store.create_session(title="test")

    # 1. 返回值是字符串
    assert isinstance(sid, str)
    # 2. 长度符合 UUID 格式
    assert len(sid) >= 32
    # 3. 文件已落盘
    assert store_path.exists()
    # 4. 落盘内容可被解析
    data = json.loads(store_path.read_text(encoding="utf-8"))
    assert sid in data["sessions"]
    assert data["sessions"][sid]["title"] == "test"


def test_default_title(tmp_data_dir):
    """不传 title 时,默认标题为 '新会话'"""
    store = ChatStore(str(tmp_data_dir / "chat.json"))
    sid = store.create_session()

    msgs = store.get_messages(sid)
    summary = next(s for s in store.list_sessions() if s["session_id"] == sid)
    assert summary["title"] == "新会话"


def test_append_and_get_messages(tmp_data_dir):
    """追加消息 + 读取消息,顺序与内容应一致"""
    store = ChatStore(str(tmp_data_dir / "chat.json"))
    sid = store.create_session()

    store.append_message(sid, "user", "你好")
    store.append_message(sid, "assistant", "你好,我是 Loci")

    msgs = store.get_messages(sid)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "你好"
    assert msgs[1]["role"] == "assistant"
    assert "Loci" in msgs[1]["content"]


def test_list_sessions_sorted_by_updated_at(tmp_data_dir):
    """list_sessions 应按 updated_at 倒序"""
    import time
    store = ChatStore(str(tmp_data_dir / "chat.json"))

    sid1 = store.create_session(title="first")
    time.sleep(0.01)
    sid2 = store.create_session(title="second")
    time.sleep(0.01)
    store.append_message(sid1, "user", "bump first")  # 触发 updated_at 更新

    sessions = store.list_sessions()
    # sid1 因为被追加消息,updated_at 应该是最新的,排第一
    assert sessions[0]["session_id"] == sid1
    assert sessions[1]["session_id"] == sid2


def test_delete_session(tmp_data_dir):
    """删除会话后再读取应返回空 messages"""
    store = ChatStore(str(tmp_data_dir / "chat.json"))
    sid = store.create_session()
    store.append_message(sid, "user", "hi")

    assert store.delete_session(sid) is True
    assert store.get_messages(sid) == []
    # 二次删除应返回 False
    assert store.delete_session(sid) is False


def test_corrupted_json_recovers_gracefully(tmp_data_dir):
    """JSON 文件损坏时,加载应返回空结构而非抛异常"""
    bad_path = tmp_data_dir / "chat.json"
    bad_path.write_text("{ this is not valid json", encoding="utf-8")

    # 不应抛异常
    store = ChatStore(str(bad_path))
    assert store.list_sessions() == []
    # 仍能正常创建新会话
    sid = store.create_session(title="recovered")
    assert sid in [s["session_id"] for s in store.list_sessions()]


def test_concurrent_writes_no_data_loss(tmp_data_dir):
    """多线程并发追加消息,不应丢失数据"""
    store = ChatStore(str(tmp_data_dir / "chat.json"))
    sid = store.create_session()

    n_threads = 5
    n_per_thread = 10
    barrier = threading.Barrier(n_threads)

    def worker(idx: int):
        barrier.wait()  # 同步起跑
        for i in range(n_per_thread):
            store.append_message(sid, "user", f"t{idx}-m{i}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    msgs = store.get_messages(sid)
    assert len(msgs) == n_threads * n_per_thread, (
        f"expected {n_threads * n_per_thread} msgs, got {len(msgs)}"
    )


def test_export_session(tmp_data_dir):
    """导出应返回 title + messages"""
    store = ChatStore(str(tmp_data_dir / "chat.json"))
    sid = store.create_session(title="export me")
    store.append_message(sid, "user", "q")
    store.append_message(sid, "assistant", "a")

    exported = store.export_session(sid)
    assert exported["title"] == "export me"
    assert len(exported["messages"]) == 2
