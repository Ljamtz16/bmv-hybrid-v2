"""Test para verificar que no hay NaN en el JSON"""
import sys
sys.path.insert(0, '.')
from dashboard_unified import app
import json

print("="*70)
print("🔍 VALIDACIÓN: JSON sin NaN")
print("="*70)
print()

client = app.test_client()

# Test /api/history
print("📋 Testing /api/history...")
response = client.get('/api/history')
if response.status_code == 200:
    text = response.get_data(as_text=True)
    
    # Verificar que no haya NaN en el texto
    if 'NaN' in text:
        print("❌ ERROR: El JSON contiene NaN")
        print("Ubicaciones de NaN:")
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if 'NaN' in line:
                print(f"  Línea {i+1}: {line[:100]}")
    else:
        print("✅ JSON válido sin NaN")
        
        # Intentar parsear
        try:
            data = json.loads(text)
            print(f"✅ JSON parseado correctamente")
            print(f"✅ Trades en historial: {len(data)}")
            
            # Verificar algunos valores
            if len(data) > 0:
                first = data[0]
                print(f"\nPrimer trade:")
                print(f"  • Ticker: {first.get('ticker')}")
                print(f"  • PnL: ${first.get('pnl', 0):.2f}")
                print(f"  • Win Rate: {first.get('win_rate', 0):.1f}%")
                print(f"  • Plan: {first.get('plan_type')}")
        except json.JSONDecodeError as e:
            print(f"❌ Error parseando JSON: {e}")
else:
    print(f"❌ Error {response.status_code}")

print()

# Test /api/trades
print("📊 Testing /api/trades...")
response = client.get('/api/trades')
if response.status_code == 200:
    text = response.get_data(as_text=True)
    if 'NaN' in text:
        print("❌ ERROR: El JSON contiene NaN")
    else:
        print("✅ JSON válido sin NaN")
        try:
            data = json.loads(text)
            print(f"✅ Trades activos: {len(data.get('trades', []))}")
        except json.JSONDecodeError as e:
            print(f"❌ Error parseando JSON: {e}")
else:
    print(f"❌ Error {response.status_code}")

print()
print("="*70)
print("✅ VALIDACIÓN COMPLETA")
print("="*70)
