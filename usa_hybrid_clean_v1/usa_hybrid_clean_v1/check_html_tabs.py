"""Verificar que las pestañas están en el HTML"""
import sys
sys.path.insert(0, '.')
from dashboard_unified import app

client = app.test_client()
response = client.get('/')
html = response.get_data(as_text=True)

print("="*60)
print("VERIFICACIÓN DE PESTAÑAS EN HTML")
print("="*60)
print(f"HTML Length: {len(html)} caracteres")
print(f"Botones tab-btn encontrados: {html.count('tab-btn')}")
print()
print("Pestañas presentes:")
print(f"  ✓ Tab0 (Trade Monitor): {'tab0' in html.lower()}")
print(f"  ✓ Tab1 (Plan Comparison): {'tab1' in html.lower()}")
print(f"  ✓ Tab2 (Historial): {'tab2' in html.lower()}")
print(f"  ✓ Tab3 (Reporte Historico): {'tab3' in html.lower()}")
print()
print("Botones visibles:")
print(f"  ✓ '📊 Trade Monitor': {'Trade Monitor' in html}")
print(f"  ✓ '⚖️ Plan Comparison': {'Plan Comparison' in html}")  
print(f"  ✓ '📋 Historial': {'Historial' in html}")
print(f"  ✓ '📈 Reporte Historico': {'Reporte Historico' in html}")
print()

# Buscar la sección de tabs
import re
tabs_section = re.search(r'<div class="tabs">(.*?)</div>', html, re.DOTALL)
if tabs_section:
    print("✅ Sección <div class='tabs'> encontrada")
    tabs_html = tabs_section.group(1)
    buttons = re.findall(r'<button[^>]*>(.*?)</button>', tabs_html, re.DOTALL)
    print(f"✅ {len(buttons)} botones encontrados:")
    for i, btn in enumerate(buttons):
        # Limpiar el contenido del botón
        btn_text = re.sub(r'<[^>]+>', '', btn).strip()
        print(f"     {i+1}. {btn_text}")
else:
    print("❌ NO se encontró la sección <div class='tabs'>")
    
print("="*60)
