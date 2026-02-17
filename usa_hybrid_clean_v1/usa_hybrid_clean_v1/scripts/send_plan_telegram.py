"""
Enviar plan de trading a Telegram
"""
import sys
sys.path.insert(0, 'utils')
import telegram_utils as tu

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python send_plan_telegram.py <ruta_archivo_telegram.txt>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            msg = f.read()
        tu.send_telegram(msg)
        print("OK")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
