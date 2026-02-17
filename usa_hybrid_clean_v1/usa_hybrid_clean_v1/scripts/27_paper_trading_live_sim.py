# =============================================
# 27_paper_trading_live_sim.py
# =============================================
import time, pandas as pd, requests, os

API="https://paper-api.alpaca.markets/v2"
HEADERS={"APCA-API-KEY-ID":"<your_key>","APCA-API-SECRET-KEY":"<your_secret>"}

def send_order(symbol,qty,side):
    data={"symbol":symbol,"qty":qty,"side":side,"type":"market","time_in_force":"day"}
    r=requests.post(API+"/orders",json=data,headers=HEADERS)
    print(r.json())

def main():
    f="reports/forecast/2025-10/forecast_with_patterns.csv"
    df=pd.read_csv(f)
    for _,r in df.iterrows():
        if r.get("gate_pattern_ok",0)==1:
            side="buy" if r["y_hat"]>0 else "sell"
            send_order(r["ticker"],1,side)
            time.sleep(1)

if __name__=="__main__":
    main()