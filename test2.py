import urllib.request
req = urllib.request.Request('https://namozvaqti.uz/shahar/toshkent', headers={'User-Agent': 'Mozilla/5.0'})
try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    with open('namozvaqti.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("Downloaded")
except Exception as e:
    print(e)
