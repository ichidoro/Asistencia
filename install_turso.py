import urllib.request
import json

url = "https://api.github.com/repos/tursodatabase/turso-cli/releases/latest"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
response = urllib.request.urlopen(req)
data = json.loads(response.read().decode('utf-8'))

for asset in data['assets']:
    print(asset['name'], asset['browser_download_url'])
