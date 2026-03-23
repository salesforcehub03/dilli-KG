import json
with open('user_query_results.json', 'rb') as f:
    content = f.read()

text_content = content.decode('utf-16le') if b'\xff\xfe' in content[:2] or b'\xfe\xff' in content[:2] else content.decode('utf-8')

with open('user_query_utf8.json', 'w', encoding='utf-8') as f:
    f.write(text_content)
