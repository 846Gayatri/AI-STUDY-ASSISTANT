import requests
url_base = 'https://ai-study-assistant-m997.onrender.com'
print("Summarize:", requests.get(f'{url_base}/api/summarize/2').status_code)
print("Quiz:", requests.get(f'{url_base}/api/quiz/2').status_code)
print("Study Plan:", requests.get(f'{url_base}/api/study-plan/2').status_code)
print("Ask:", requests.post(f'{url_base}/api/ask/2', json={'question': 'test'}).status_code)
print("Ask-All:", requests.post(f'{url_base}/api/ask-all', json={'question': 'test'}).status_code)
print("Route:", requests.post(f'{url_base}/api/route', json={'query': 'test'}).status_code)
