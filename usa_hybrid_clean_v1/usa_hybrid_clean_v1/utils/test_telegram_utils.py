import os
import sys
import time

# Ensure local import from the same folder
sys.path.insert(0, os.path.dirname(__file__))
import telegram_utils as tu


def run():
    # 1) Test load_env_file with a temp env file
    env_path = ".env.test.tmp"
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("FOO=BAR\n")
        f.write("# comment\n")
        f.write("TELEGRAM_BOT_TOKEN=TEST_TOKEN\n")
        f.write("TELEGRAM_CHAT_ID=123456\n")

    ok = tu.load_env_file(env_path)
    assert ok, "load_env_file should return True"
    assert os.getenv("FOO") == "BAR", "FOO var missing after load_env_file"
    assert os.getenv("TELEGRAM_BOT_TOKEN") == "TEST_TOKEN", "Token not loaded"
    assert os.getenv("TELEGRAM_CHAT_ID") == "123456", "Chat id not loaded"

    # 2) Test throttle_keeper behavior
    throttle_path = ".tg_throttle_test.json"
    guard = tu.throttle_keeper(throttle_path)
    key = "unit:test"
    assert guard(key, 1) is True, "First call should pass"
    assert guard(key, 1) is False, "Second call within cooldown should be blocked"
    time.sleep(1.1)
    assert guard(key, 1) is True, "After cooldown it should pass again"

    # 3) Mock requests.post to test send_telegram without network
    class FakeResp:
        def __init__(self):
            self._json = {"ok": True, "result": {"message_id": 1}}
        def raise_for_status(self):
            return None
        def json(self):
            return self._json

    def fake_post(url, data):
        assert "botTEST_TOKEN" in url, "Token not used in URL"
        assert data["chat_id"] == "123456", "Chat id not propagated"
        assert "text" in data, "Message text missing"
        assert data.get("parse_mode") == "HTML", "parse_mode should be HTML"
        return FakeResp()

    tu.requests.post = fake_post
    out = tu.send_telegram("hello world (dry-run)")
    assert out.get("ok") is True, "send_telegram should return ok=True"

    print("ALL TESTS PASSED: telegram_utils")

    # Cleanup temp files
    try:
        os.remove(env_path)
    except Exception:
        pass
    try:
        os.remove(throttle_path)
    except Exception:
        pass


if __name__ == "__main__":
    run()
