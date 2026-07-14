import requests
r = requests.post('https://ai-study-assistant-m997.onrender.com/upload', files={'file': open('test.txt', 'rb')})
with open('output.html', 'w', encoding='utf-8') as f:
    f.write(r.text)
print(r.status_code)
