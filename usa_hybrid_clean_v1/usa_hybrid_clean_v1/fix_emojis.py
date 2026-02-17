#!/usr/bin/env python3
"""Remove emojis from logger calls"""
import re

with open('dashboard_unified.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove emojis from logger calls
replacements = {
    'logger.debug("📊 Tracking cycle start")': 'logger.debug("[TRACKING] Cycle start")',
    'logger.info(f"✅ Tracking cycle completed in {duration:.2f}s")': 'logger.info(f"[TRACKING] Cycle completed in {duration:.2f}s")',
    'logger.exception(f"❌ Tracking cycle FAILED after {duration:.2f}s: {e}")': 'logger.exception(f"[TRACKING] Cycle FAILED after {duration:.2f}s: {e}")',
    'logger.debug(f"💾 Snapshot async rebuild in {duration:.2f}s")': 'logger.debug(f"[SNAPSHOT] Async rebuild in {duration:.2f}s")',
    'logger.exception(f"❌ Snapshot async rebuild failed: {e}")': 'logger.exception(f"[SNAPSHOT] Async rebuild failed: {e}")',
    'logger.info(f"🚀 Background tracking started (interval: {TRACKING_INTERVAL}s)")': 'logger.info(f"[TRACKING] Background tracking started (interval: {TRACKING_INTERVAL}s)")',
    'logger.debug(f"📍 Tracking cycle #{cycle_count} starting")': 'logger.debug(f"[TRACKING] Cycle #{cycle_count} starting")',
    'logger.exception(f"❌ Tracking loop error (cycle #{cycle_count}): {e}")': 'logger.exception(f"[TRACKING] Loop error (cycle #{cycle_count}): {e}")',
    'status_icon = "✅" if response.status_code < 300 else "⚠️" if response.status_code < 400 else "❌"': 'status_icon = "[OK]" if response.status_code < 300 else "[WARN]" if response.status_code < 400 else "[ERR]"',
    'logger.warning("⚠️ Werkzeug reloader error (ignorado), reiniciando sin reloader...")': 'logger.warning("[WERKZEUG] Reloader error")',
}

for old, new in replacements.items():
    if old in content:
        content = content.replace(old, new)
        print(f"✓ Fixed: {old[:50]}...")
    else:
        print(f"✗ Not found: {old[:50]}...")

# Also fix main() prints
content = content.replace(
    'logger.info("="*80)',
    'logger.info("[STARTUP] Dashboard starting")'
)
content = content.replace(
    'logger.info(f"📍 LOCAL ACCESS: http://localhost:{PORT}/")',
    'logger.info(f"[STARTUP] LOCAL: http://localhost:{PORT}/")'
)
content = content.replace(
    'logger.info(f"📍 LAN ACCESS: http://{local_ip}:{PORT}/")',
    'logger.info(f"[STARTUP] LAN: http://{local_ip}:{PORT}/")'
)
content = content.replace(
    'logger.info(f"✅ Servidor escuchando en 0.0.0.0:{PORT}")',
    'logger.info(f"[STARTUP] Listening on 0.0.0.0:{PORT}")'
)
content = content.replace(
    'logger.info(f"✅ Background tracking cada {TRACKING_INTERVAL}s")',
    'logger.info(f"[STARTUP] Tracking interval: {TRACKING_INTERVAL}s")'
)
content = content.replace(
    'logger.info(f"✅ Snapshot cache TTL: {SNAPSHOT_CACHE_TTL}s")',
    'logger.info(f"[STARTUP] Cache TTL: {SNAPSHOT_CACHE_TTL}s")'
)

with open('dashboard_unified.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✅ All emojis fixed!")
