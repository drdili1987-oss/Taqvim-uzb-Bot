import urllib.request, re
req = urllib.request.Request('https://namozvaqti.uz/shahar/toshkent', headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read().decode('utf-8')
for k in ['bomdod', 'quyosh', 'peshin', 'asr', 'shom', 'xufton']:
    m = re.search(f'id="{k}">(\d{{2}}:\d{{2}})</p>', html, re.IGNORECASE)
    if m:
        print(f'{k}: {m.group(1)}')
