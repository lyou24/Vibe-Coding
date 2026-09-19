import os
index_path = r'C:\Users\lyoul\.gemini\antigravity\brain\3fb083d6-f272-4146-8ed2-afcef3e4dba7\scratch\ongeki-app\frontend\src\index.css'
with open(index_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('@tailwind base;\n@tailwind components;\n@tailwind utilities;', '@import \"tailwindcss\";')
with open(index_path, 'w', encoding='utf-8') as f:
    f.write(content)

app_path = r'C:\Users\lyoul\.gemini\antigravity\brain\3fb083d6-f272-4146-8ed2-afcef3e4dba7\scratch\ongeki-app\frontend\src\App.tsx'
with open(app_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

app_content = app_content.replace('overflow-hidden\">\n              <table', 'overflow-x-auto\">\n              <table')

with open(app_path, 'w', encoding='utf-8') as f:
    f.write(app_content)

print('Patched successfully')
