import urllib.request
regions = ['toshkent', 'samarqand', 'fargona']
for r in regions:
    req = urllib.request.Request(f'https://namozvaqti.uz/shahar/{r}', headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8')
    if 'Bomdod' in html:
        print(f'{r} OK')
    else:
        print(f'{r} FAIL')
