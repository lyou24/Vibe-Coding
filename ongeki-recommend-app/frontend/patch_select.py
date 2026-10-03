import os

filepath = r"C:\Users\lyoul\.gemini\antigravity\brain\3fb083d6-f272-4146-8ed2-afcef3e4dba7\scratch\OngekiRecommendApp\frontend\src\App.tsx"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 置換前後のマッピング
replacements = {
    '<option value="pm025">±0.25 (厳密)</option>': '<option value="pm025">±0.25</option>',
    '<option value="pm050">±0.50 (広範)</option>': '<option value="pm050">±0.5</option>',
    '<option value="p050">0 から +0.50 (格上)</option>': '<option value="p050">+0.5</option>'
}

for old, new in replacements.items():
    content = content.replace(old, new)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("App.tsx select options updated.")
