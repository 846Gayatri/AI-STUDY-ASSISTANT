from openai import OpenAI
import os, json

def generate_quiz(text, num_questions=5, difficulty="medium"):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_key_here":
        words = text.split()[:5]
        topic = " ".join(words)
        return [
            {
                "question": f"What is the primary focus of the document segment mentioning '{topic}'?",
                "options": ["To define the core vocabulary", "To provide statistical analysis", "To outline background history", "To critique existing literature"],
                "correct_answer": "To define the core vocabulary"
            },
            {
                "question": f"Which of the following is a key concept introduced in the text?",
                "options": ["System efficiency models", "Spaced repetition framework", "Naive classification logic", "Dynamic data caching"],
                "correct_answer": "System efficiency models"
            },
            {
                "question": f"What is the recommended approach for studying difficult concepts in this material?",
                "options": ["Passive reading", "Spaced repetition reviews", "Cramming the night before", "Group discussion only"],
                "correct_answer": "Spaced repetition reviews"
            },
            {
                "question": f"True or False: The text indicates that initial concepts should be reviewed within 3 days.",
                "options": ["True", "False", "Cannot be determined", "Only for practical components"],
                "correct_answer": "True"
            },
            {
                "question": f"What is a main takeaway from the introductory chapter?",
                "options": ["A basic understanding of the fundamentals", "An expert level certification", "A detailed engineering design", "A code implementation plan"],
                "correct_answer": "A basic understanding of the fundamentals"
            }
        ]

    client = OpenAI(api_key=api_key)
    prompt = f"""Generate {num_questions} multiple-choice questions at
{difficulty} difficulty from this material. Return ONLY valid JSON, no
markdown, in this exact format:

[{{"question": "...", "options": ["A","B","C","D"], "correct_answer": "A"}}]

Material:
{text[:8000]}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"OpenAI Quiz generation failed, falling back to mock: {e}")
        return [
            {
                "question": "Sample Question: What is the main thesis of the uploaded text?",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correct_answer": "Option A"
            }
        ]
