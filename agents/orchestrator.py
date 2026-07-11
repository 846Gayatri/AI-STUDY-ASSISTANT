from openai import OpenAI
import os, json

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

INTENTS = ["summarize", "quiz", "question_answer", "study_plan"]

def classify_intent(user_input):
    """Routes free-form user requests to the right agent — this is the
    decision layer, not a hardcoded if/else on keywords."""
    prompt = f"""Classify this student request into exactly one category:
{INTENTS}. Return ONLY the category name, nothing else.

Request: "{user_input}"
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    intent = response.choices[0].message.content.strip().lower()
    return intent if intent in INTENTS else "question_answer"

def route(user_input, document_context):
    intent = classify_intent(user_input)
    # app.py calls the matching agent based on this return value
    return intent
