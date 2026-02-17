import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import telegram_utils as tu

# Prepare a temp .env to simulate runtime job without env preloaded
with open('.env', 'w', encoding='utf-8') as f:
    f.write('TELEGRAM_BOT_TOKEN=TEST_TOKEN\n')
    f.write('TELEGRAM_CHAT_ID=123456\n')

# Mock requests to avoid real network
class FakeResp:
    def raise_for_status(self):
        return None
    def json(self):
        return {"ok": True}

def fake_post(url, data):
    assert 'botTEST_TOKEN' in url
    assert data['chat_id'] == '123456'
    return FakeResp()

tu.requests.post = fake_post

# Clear env to ensure autoload is required
os.environ.pop('TELEGRAM_BOT_TOKEN', None)
os.environ.pop('TELEGRAM_CHAT_ID', None)

# Call without preloading env: send_telegram should autoload .env and succeed
out = tu.send_telegram('ping test')
print('send_ok', out['ok'])
