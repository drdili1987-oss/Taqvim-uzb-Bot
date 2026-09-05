import re
try:
    with open('islom.html', 'r', encoding='utf-8') as f:
        html = f.read()
    times = re.findall(r'class="p_time">(.*?)</p>', html)
    print("ISLOM.UZ TIMES:", times)
except Exception as e:
    print(e)
