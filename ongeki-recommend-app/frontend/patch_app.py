import os

filepath = r"C:\Users\lyoul\.gemini\antigravity\brain\3fb083d6-f272-4146-8ed2-afcef3e4dba7\scratch\OngekiRecommendApp\frontend\src\App.tsx"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 比較対象ラベルの取得ロジック
old_export = """              <ExportControls items={sortedItems} activeTab={activeTab} tableId="recommend-table" />"""

new_export = """              <ExportControls 
                items={sortedItems} 
                activeTab={activeTab} 
                tableId="recommend-table" 
                groupLabel={group === "pm025" ? "±0.25" : group === "pm050" ? "±0.5" : "+0.5"}
              />"""

content = content.replace(old_export, new_export)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("App.tsx ExportControls patch applied.")
