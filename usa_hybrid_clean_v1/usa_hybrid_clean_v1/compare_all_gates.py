import json

print("\n" + "="*70)
print("📊 COMPARACIÓN: 3 GATES EN MARZO 2025")
print("="*70)

# Load all three gates
with open('evidence/ticker_gate_mar2025/ticker_gate.json') as f:
    static = json.load(f)

with open('evidence/dynamic_gate_mar2025/dynamic_gate.json') as f:
    dynamic = json.load(f)

with open('evidence/hybrid_gate_mar2025/hybrid_gate.json') as f:
    hybrid = json.load(f)

# Extract ticker lists
static_tickers = static['selected_tickers']
dynamic_tickers = dynamic['final_portfolio']
hybrid_tickers = hybrid['selected_tickers']

print("\n" + "="*70)
print("🎯 SELECCIÓN DE TICKERS")
print("="*70)

print(f"\n1. STATIC GATE (fijo mensual):")
print(f"   {' | '.join(static_tickers)}")

print(f"\n2. DYNAMIC GATE (rebalance semanal):")
print(f"   {' | '.join(dynamic_tickers)}")
print(f"   Rotaciones: {sum(len(rb['changes']['added']) for rb in dynamic['rebalance_history'][1:])} entradas / {sum(len(rb['changes']['dropped']) for rb in dynamic['rebalance_history'][1:])} salidas")

print(f"\n3. HYBRID GATE (MC 60% + Signal 40%):")
print(f"   {' | '.join(hybrid_tickers)}")
print(f"   Nota: Sin señales históricas, degrada a MC puro")

# Venn diagram analysis
all_tickers = set(static_tickers) | set(dynamic_tickers) | set(hybrid_tickers)

print("\n" + "="*70)
print("🔍 ANÁLISIS VENN")
print("="*70)

for ticker in sorted(all_tickers):
    in_static = "✅" if ticker in static_tickers else "❌"
    in_dynamic = "✅" if ticker in dynamic_tickers else "❌"
    in_hybrid = "✅" if ticker in hybrid_tickers else "❌"
    
    count = sum([ticker in static_tickers, ticker in dynamic_tickers, ticker in hybrid_tickers])
    
    if count == 3:
        consensus = "🟢 CONSENSO (3/3)"
    elif count == 2:
        consensus = "🟡 MAYORÍA (2/3)"
    else:
        consensus = "🔴 MINORITARIO (1/3)"
    
    print(f"\n{ticker:6s} | Static: {in_static} | Dynamic: {in_dynamic} | Hybrid: {in_hybrid} | {consensus}")

# Consensus tickers
consensus = set(static_tickers) & set(dynamic_tickers) & set(hybrid_tickers)

print("\n" + "="*70)
print("🏆 CONSENSO (aparecen en los 3 gates):")
print("="*70)
if consensus:
    print(f"\n   {' | '.join(sorted(consensus))}")
else:
    print("\n   ⚠️ No hay consenso total")

# Show MC scores for consensus
print("\n" + "="*70)
print("📊 SCORES MC DE CONSENSO")
print("="*70)

for ticker in sorted(consensus):
    # Find in static ranking
    static_data = next((r for r in static['ranking'] if r['ticker'] == ticker), None)
    if static_data:
        score = static_data['metrics']['score']
        ev = static_data['metrics']['ev']
        tp_rate = static_data['metrics']['tp_rate']
        print(f"\n{ticker}: Score {score:.4f} | EV ${ev:.4f} | TP {tp_rate:.1%}")

print("\n" + "="*70)
print("💡 RECOMENDACIÓN FINAL")
print("="*70)

print(f"\nPara operar marzo 2025:")
print(f"  🎯 CONSENSO: {', '.join(sorted(consensus)) if consensus else 'N/A'}")
print(f"  ⚡ Si mercado volátil: usar Dynamic Gate")
print(f"  📊 Si hay señales actuales: usar Hybrid Gate")
print(f"  🔒 Conservador: usar Static Gate (menor rotación)")
