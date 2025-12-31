import sys
import json
import datetime
import os
import requests  # Requires: pip install requests

class CostCircuitBreaker:
    def __init__(self, limit_yen=300, webhook_url=None):
        self.limit_yen = limit_yen
        self.webhook_url = webhook_url
        self.data_file = "/var/lib/airband_ai/daily_cost.json"
        
        # Current date string (e.g., "2023-10-27")
        self.current_date_str = datetime.date.today().isoformat()
        
        # Load previous state on startup
        self.current_yen = self._load_state()
        
        # ==========================================
        # Gemini 2.5 Flash pricing (per 1M tokens)
        # Input: $1.00 / Output: $2.50 (USD 1 = JPY 155)
        # ==========================================
        usd_jpy_rate = 155.0
        self.INPUT_PRICE_PER_1M = 1.00 * usd_jpy_rate
        self.OUTPUT_PRICE_PER_1M = 2.5 * usd_jpy_rate

    def _load_state(self):
        """Load cost from file. Reset to 0 when the date changes."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r") as f:
                    data = json.load(f)
                    
                    # Continue if the file date matches today
                    if data.get("date") == self.current_date_str:
                        print(f"▼ [CostGuard] 前回の続きから開始します: 現在 {data['cost']:.2f}円")
                        return data["cost"]
            except Exception as e:
                print(f"⚠️ [CostGuard] データ読み込みエラー（初期化します）: {e}")
        
        # No file or old date: start from 0
        print("▼ [CostGuard] 新しい日（または初回）のため、コストを0円にリセットしました。")
        return 0.0

    def _save_state(self):
        """Save current cost to file."""
        data = {"date": self.current_date_str, "cost": self.current_yen}
        try:
            with open(self.data_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"⚠️ [CostGuard] データ保存エラー: {e}")

    def add_cost(self, input_tok, output_tok):
        """
        Add cost and check the threshold.
        Also handles auto-reset across midnight.
        """
        # 1. Date change check
        today_str = datetime.date.today().isoformat()
        if today_str != self.current_date_str:
            print(f"📅 [CostGuard] 日付が変わりました ({self.current_date_str} -> {today_str})。コストをリセットします。")
            self.current_date_str = today_str
            self.current_yen = 0.0

        # 2. Cost calculation
        cost = (input_tok / 1_000_000 * self.INPUT_PRICE_PER_1M) + \
               (output_tok / 1_000_000 * self.OUTPUT_PRICE_PER_1M)
        self.current_yen += cost
        
        # 3. Save to file (protection against sudden power loss)
        self._save_state()
        
        # 4. Status output
        #print(f"💰 [CostGuard] This run: {cost:.4f} JPY | Today total: {self.current_yen:.4f} JPY / Limit: {self.limit_yen} JPY")
        pass
        # 5. Threshold check
        if self.current_yen > self.limit_yen:
            self.emergency_stop()

    def emergency_stop(self):
        """Emergency stop."""
        msg = f"🚫【緊急停止】本日の課金リミット({self.limit_yen}円)を超過しました！ 確定額: {self.current_yen:.2f}円"
        print("\n" + "="*60)
        print(msg)
        print("="*60 + "\n")
        
        # Discord notification
        if self.webhook_url:
            try:
                requests.post(self.webhook_url, json={"content": msg})
                print(">> Discordに通知を送信しました。")
            except Exception as e:
                print(f"x Discord送信エラー: {e}")
        
        print("システムを安全に終了します...")
        sys.exit(42)

    # Extra: compatibility for calls from main.py
    def can_proceed(self):
        """
        Check if the cost limit is reached. Call emergency_stop on overflow.
        """
        if self.current_yen > self.limit_yen:
            self.emergency_stop()
            return False
        return True

    @property
    def total_cost(self):
        return self.current_yen
