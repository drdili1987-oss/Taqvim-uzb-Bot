import urllib.request
req = urllib.request.Request('https://islom.uz', headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read().decode('utf-8')
with open('islom.html', 'w', encoding='utf-8') as f:
    f.write(html)
