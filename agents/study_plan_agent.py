from openai import OpenAI
import os, json

def generate_study_plan(summary, key_points, days_until_exam=7):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_key_here":
        # Return mock plan
        plan = {}
        for d in range(1, days_until_exam + 1):
            plan[f"day_{d}"] = {
                "topics": [f"Topic Overview {d}", f"Deep Dive Chapter {d}"],
                "tasks": [f"Review chunk summaries for section {d}", f"Take the adaptive mock quiz"],
                "est_hours": 2
            }
        return plan

    client = OpenAI(api_key=api_key)
    prompt = f"""Create a {days_until_exam}-day study plan based on this
material summary and key concepts. Distribute topics logically (harder
topics earlier). IMPORTANT: Incorporate "spaced repetition" scheduling — 
ensure that difficult topics reviewed on Day 1 are briefly revisited on Day 3 and Day 7 to reinforce memory.

Return ONLY valid JSON:
{{"day_1": {{"topics": [...], "tasks": [...], "est_hours": 2}}, ...}}

Summary: {summary}
Key points: {key_points}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        raw = response.choices[0].message.content.strip().replace("```json", "").replace("```", "")
        return json.loads(raw)
    except Exception as e:
        print(f"OpenAI Study Plan generation failed, falling back to mock: {e}")
        plan = {}
        for d in range(1, days_until_exam + 1):
            plan[f"day_{d}"] = {
                "topics": [f"Topic Overview {d}", f"Deep Dive Chapter {d}"],
                "tasks": [f"Review chunk summaries for section {d}", f"Take the adaptive mock quiz"],
                "est_hours": 2
            }
        return plan
