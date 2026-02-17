"""
Validación de pestañas Historial y Reporte Histórico
"""
import dashboard_unified
import json

def validate_history_tab():
    """Valida la pestaña de Historial (GET /api/history)"""
    print("=" * 80)
    print("VALIDACIÓN PESTAÑA: HISTORIAL")
    print("=" * 80)
    
    client = dashboard_unified.app.test_client()
    response = client.get('/api/history')
    
    if response.status_code != 200:
        print(f"❌ ERROR: Status {response.status_code}")
        return False
    
    data = json.loads(response.data)
    print(f"✅ Status: {response.status_code} OK")
    print(f"✅ Total trades cerrados: {len(data)}")
    
    if len(data) == 0:
        print("⚠️  Sin trades en historial")
        return True
    
    # Verificar estructura de datos
    required_fields = ['ticker', 'plan_type', 'pnl', 'exit_reason', 'fecha', 
                      'entrada', 'salida', 'tp_price', 'sl_price', 'pnl_pct']
    first_trade = data[0]
    missing = [f for f in required_fields if f not in first_trade]
    
    if missing:
        print(f"❌ Campos faltantes: {missing}")
        return False
    else:
        print(f"✅ Estructura correcta: Todos los campos presentes")
    
    # Mostrar primeros 5 trades
    print(f"\n📊 Primeros 5 trades:")
    for i, t in enumerate(data[:5], 1):
        pnl_sign = "🟢" if t['pnl'] > 0 else "🔴"
        print(f"  {i}. {pnl_sign} {t['ticker']:6s} | {t['plan_type']:12s} | "
              f"PnL: ${t['pnl']:7.2f} ({t['pnl_pct']:+6.2f}%) | "
              f"{t['exit_reason']:2s} | {t['fecha']}")
    
    # Estadísticas
    total_pnl = sum(t['pnl'] for t in data)
    winners = sum(1 for t in data if t['pnl'] > 0)
    losers = sum(1 for t in data if t['pnl'] <= 0)
    win_rate = (winners / len(data) * 100) if len(data) > 0 else 0
    
    print(f"\n📈 ESTADÍSTICAS GENERALES:")
    print(f"  • PnL Total: ${total_pnl:.2f}")
    print(f"  • Ganadores: {winners} trades")
    print(f"  • Perdedores: {losers} trades")
    print(f"  • Win Rate: {win_rate:.1f}%")
    
    # Desglose por plan
    standard_trades = [t for t in data if t['plan_type'] == 'STANDARD']
    probwin_trades = [t for t in data if t['plan_type'] == 'PROBWIN_55']
    
    if standard_trades:
        std_pnl = sum(t['pnl'] for t in standard_trades)
        std_win = sum(1 for t in standard_trades if t['pnl'] > 0)
        print(f"\n  📌 STANDARD: {len(standard_trades)} trades, PnL: ${std_pnl:.2f}, "
              f"Win: {std_win}/{len(standard_trades)} ({std_win/len(standard_trades)*100:.1f}%)")
    
    if probwin_trades:
        pw_pnl = sum(t['pnl'] for t in probwin_trades)
        pw_win = sum(1 for t in probwin_trades if t['pnl'] > 0)
        print(f"  📌 PROBWIN_55: {len(probwin_trades)} trades, PnL: ${pw_pnl:.2f}, "
              f"Win: {pw_win}/{len(probwin_trades)} ({pw_win/len(probwin_trades)*100:.1f}%)")
    
    return True

def validate_report_tab():
    """Valida el Reporte Histórico (página HTML principal)"""
    print("\n" + "=" * 80)
    print("VALIDACIÓN PESTAÑA: REPORTE HISTÓRICO (HTML)")
    print("=" * 80)
    
    client = dashboard_unified.app.test_client()
    response = client.get('/')
    
    if response.status_code != 200:
        print(f"❌ ERROR: Status {response.status_code}")
        return False
    
    html = response.get_data(as_text=True)
    print(f"✅ Status: {response.status_code} OK")
    print(f"✅ Tamaño HTML: {len(html)} caracteres")
    
    # Verificar elementos clave del HTML
    checks = [
        ('Título Dashboard', 'TRADE DASHBOARD' in html or 'Dashboard' in html),
        ('Script JS', '<script>' in html),
        ('Tabs/Pestañas', 'tab' in html.lower() or 'pestaña' in html.lower()),
        ('Historial', 'historial' in html.lower() or 'history' in html.lower()),
        ('Chart.js', 'chart' in html.lower()),
        ('Tabla', '<table' in html.lower() or 'datatable' in html.lower())
    ]
    
    for name, passed in checks:
        status = "✅" if passed else "⚠️ "
        print(f"  {status} {name}: {'OK' if passed else 'No encontrado'}")
    
    # Verificar endpoints API en el HTML
    api_endpoints = ['/api/trades', '/api/history', '/api/comparison']
    found_apis = [ep for ep in api_endpoints if ep in html]
    
    print(f"\n📡 APIs referenciadas en HTML: {len(found_apis)}/{len(api_endpoints)}")
    for ep in found_apis:
        print(f"  ✅ {ep}")
    
    return True

def main():
    print("\n" + "🔍 " * 20)
    print("VALIDACIÓN COMPLETA DE PESTAÑAS DEL DASHBOARD")
    print("🔍 " * 20 + "\n")
    
    # Validar ambas pestañas
    hist_ok = validate_history_tab()
    report_ok = validate_report_tab()
    
    # Resumen final
    print("\n" + "=" * 80)
    print("RESUMEN FINAL")
    print("=" * 80)
    print(f"  {'✅' if hist_ok else '❌'} Pestaña HISTORIAL: {'FUNCIONAL' if hist_ok else 'CON ERRORES'}")
    print(f"  {'✅' if report_ok else '❌'} Pestaña REPORTE HISTÓRICO: {'FUNCIONAL' if report_ok else 'CON ERRORES'}")
    
    if hist_ok and report_ok:
        print("\n🎉 TODAS LAS PESTAÑAS VALIDADAS CORRECTAMENTE")
    else:
        print("\n⚠️  Algunas pestañas requieren atención")
    
    print("=" * 80)

if __name__ == "__main__":
    main()
